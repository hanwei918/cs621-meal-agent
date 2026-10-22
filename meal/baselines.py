"""Baselines (owner: ⑤). TODO — same runner.Agent interface, same cases, same model.

SingleCallBaseline — recipes + store + profile in ONE prompt → one JSON answer (plan + cart), then
                     set_plan / add_to_cart / request_approval / place_order are applied by code. It
                     cannot react to events; its final cart is judged against the post-event state.
FixedPlanner       — rule-based: filter recipes by profile, pick the cheapest combination, buy packs,
                     request approval, order. No LLM, no re-planning after events.
"""
from __future__ import annotations


class SingleCallBaseline:  # TODO(⑤)
    def __init__(self, model: str, client=None):
        raise NotImplementedError


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
