"""Baselines (owner: ⑤) — same runner.Agent interface, same cases, same model.

SingleCallBaseline — recipes + store + profile in ONE prompt → one JSON answer (plan + cart), then
                     set_plan / add_to_cart / request_approval / place_order are applied by code. It
                     cannot react to events; its final cart is judged against the post-event state.
FixedPlanner       — rule-based: filter recipes by profile, pick the cheapest combination, buy packs,
                     request approval, order. No LLM, no re-planning after events.
"""
from __future__ import annotations

import json


SINGLE_SYSTEM = """You plan three days of home cooking and the grocery order for one user in a simulated store. \
You get the whole situation in one message and have no tools. Hard constraints you must never relax: diet \
(vegetarian excludes chicken, pork, beef, fish, shellfish; no_pork; no_beef), allergies (check every ingredient's \
allergens), maximum cooking minutes per meal, exactly one recipe per day × meal slot, enough whole packs of \
in-stock items to cover recipe grams × servings minus the pantry, and the cart total within budget. \
If no plan can satisfy every constraint, set feasible=false and name the binding constraint: apply the \
constraints in this order (diet and allergies, then cooking time, then stock, then budget); the binding one is \
the first after which no valid plan is left. \
Return JSON only, matching the schema; total_sgd must be the exact sum of price × packs."""

SINGLE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["feasible", "binding", "meals", "cart", "total_sgd"],
    "properties": {
        "feasible": {"type": "boolean"},
        "binding": {"type": "string", "enum": ["none", "budget", "diet", "time", "stock"]},
        "meals": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["day", "slot", "recipe_id"],
                                             "properties": {"day": {"type": "integer"}, "slot": {"type": "integer"},
                                                            "recipe_id": {"type": "string"}}}},
        "cart": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["sku", "packs"],
                                            "properties": {"sku": {"type": "string"}, "packs": {"type": "integer"}}}},
        "total_sgd": {"type": "number"},
    },
}


def situation(env) -> str:
    """The whole situation as the agent could have read it at step 0 (profile, recipes with
    ingredient allergens/animal, store). Events later in the run are NOT in it."""
    w = env.w
    recipes = [{"id": r.id, "name": r.name, "minutes": r.minutes,
                "ingredients": [{"id": i, "grams": g, "allergens": w.ingredients[i].allergens,
                                 "animal": w.ingredients[i].animal} for i, g in r.grams.items()]}
               for r in w.recipes.values()]
    store = [s.model_dump() for s in w.store.values()]
    return json.dumps({"profile": w.profile.model_dump(), "recipes": recipes, "store": store}, ensure_ascii=False)


class SingleCallBaseline:
    """Baseline 1 (⑤): ONE model call with the whole situation, structured JSON out; code then applies
    it through the same tools (set_plan, add_to_cart, request_approval, place_order). It cannot react
    to events: if approval is refused or revoked, it stops without ordering."""

    def __init__(self, model: str, client=None, effort: str | None = None):
        self.model, self.effort, self._client = model, effort, client

    def run(self, env):
        from .runner import AgentUsage
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        oc = {"format": {"type": "json_schema", "schema": SINGLE_SCHEMA}}
        if self.effort:
            oc["effort"] = self.effort
        resp = self._client.messages.create(
            model=self.model, max_tokens=8000,
            system=[{"type": "text", "text": SINGLE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Situation:\n{situation(env)}\n\nPlan and order."}],
            output_config=oc)
        us = resp.usage
        u = AgentUsage(us.input_tokens, us.output_tokens, getattr(us, "cache_read_input_tokens", 0) or 0,
                       getattr(us, "cache_creation_input_tokens", 0) or 0)
        if resp.stop_reason != "end_turn":
            raise RuntimeError(f"single call stopped: {resp.stop_reason}")
        out = json.loads(next(b.text for b in resp.content if b.type == "text"))
        if not out["feasible"]:
            env.call("report_infeasible", binding=out["binding"], explanation="single call")
            return u
        env.call("set_plan", meals=out["meals"])
        for line in out["cart"]:
            if line["packs"] > 0:
                env.call("add_to_cart", sku=line["sku"], packs=line["packs"])
        r = env.call("request_approval", reported_total_sgd=out["total_sgd"])
        if r.get("approved") and not r.get("notices"):
            env.call("place_order", token=r["token"])
        return u


class FixedPlanner:
    """Baseline 2 (⑤): a fixed, rule-based workflow through the SAME tools as the agent, no LLM.
    Filters recipes by the profile it read at the start, prices the cheapest 1–3-recipe plan from the
    store as it looked then, buys, asks for approval and orders. It never re-plans: if approval is
    refused or revoked, it stops without ordering."""

    def __init__(self, *_):
        pass

    def run(self, env):
        import math
        from itertools import combinations

        from .runner import AgentUsage
        prof = env.call("get_profile")
        banned = {"vegetarian": {"chicken", "pork", "beef", "fish", "shellfish"}, "no_pork": {"pork"},
                  "no_beef": {"beef"}}
        bad_animals = set().union(*(banned[d] for d in prof["diet"])) if prof["diet"] else set()
        ok, grams = [], {}
        rows = lambda res: res["results"] if isinstance(res, dict) else res   # list, or list + notices
        for r in rows(env.call("search_recipes", max_minutes=prof["max_cook_minutes"])):
            rec = env.call("get_recipe", recipe_id=r["id"])
            if all(i["animal"] not in bad_animals and not set(i["allergens"]) & set(prof["allergies"])
                   for i in rec["ingredients"]):
                ok.append(r["id"])
                grams[r["id"]] = {i["id"]: i["grams"] for i in rec["ingredients"]}
        items = {}
        slots = [(d, s) for d in range(1, prof["days"] + 1) for s in range(1, prof["meals_per_day"] + 1)]

        def price(ids):
            need = {}
            for k, _ in enumerate(slots):
                for i, g in grams[ids[k % len(ids)]].items():
                    need[i] = need.get(i, 0) + g * prof["servings"]
            cart, total = {}, 0.0
            for i, g in need.items():
                g -= prof["pantry"].get(i, 0)
                if g <= 0:
                    continue
                if i not in items:
                    items[i] = [x for x in rows(env.call("find_items", ingredient=i)) if x["stock"] > 0]
                if not items[i]:
                    return None
                best = min(items[i], key=lambda x: x["price_sgd"] / x["pack_g"])
                n = math.ceil(g / best["pack_g"])
                if n > best["stock"]:
                    return None
                cart[best["sku"]] = n
                total += n * best["price_sgd"]
            return round(total, 2), cart

        options = [(price(ids), ids) for k in (1, 2, 3) for ids in combinations(ok, k)]
        options = [(p, ids) for p, ids in options if p and p[0] <= prof["budget_sgd"] + 1e-9]
        if not options:
            env.call("report_infeasible", binding="budget" if ok else "diet", explanation="fixed planner found none")
            return AgentUsage()
        (total, cart), ids = min(options, key=lambda o: o[0][0])
        env.call("set_plan", meals=[{"day": d, "slot": s, "recipe_id": ids[k % len(ids)]} for k, (d, s) in enumerate(slots)])
        for sku, n in cart.items():
            env.call("add_to_cart", sku=sku, packs=n)
        r = env.call("request_approval", reported_total_sgd=total)
        if r.get("approved") and not r.get("notices"):
            env.call("place_order", token=r["token"])
        return AgentUsage()
