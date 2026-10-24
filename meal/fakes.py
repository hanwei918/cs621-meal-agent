"""Fake agents that check the GRADER, not the agent. Never reported as results.

OracleAgent   — cheats: waits until every event has fired, then uses the reference solver on the
                true state. Must pass every case.
RecklessAgent — ignores the profile (diet, allergies, time), orders without approval, then asks.
                Must fail, for the right reasons.
"""
from __future__ import annotations

from .checks import cart_total
from .env import StoreEnv
from .runner import AgentUsage
from .solver import diagnose, scope_cap, solve, solve_within


class OracleAgent:
    def run(self, env: StoreEnv) -> AgentUsage:
        if env.case.gold.out_of_scope:
            env.call("decline_request", reason="out of scope (oracle)")
            return AgentUsage()
        if env.case.gold.review:                           # wm: the calculator says stop
            env.call("calculate_targets")
            env.call("stop_for_review", status=env.case.gold.review, explanation="oracle")
            return AgentUsage()
        if env.withheld:                                   # P-01: ask, never guess
            env.call("request_input", fields=sorted(env.withheld), question="missing or invalid")
        if env.case.gold.note is not None:                 # the author's reading of the note
            n = env.case.gold.note
            env.call("declare_constraints", exclude_ingredients=n.exclude_ingredients, exclude_recipes=n.exclude_recipes,
                     slot_max_minutes=[s.model_dump() for s in n.slot_max_minutes], pantry_add=n.pantry_add)
        for _ in range(50):                                # let every step event fire before deciding
            if not env.pending:
                break
            env.call("view_cart")
        for _ in range(4):                                 # approval may trigger events: re-solve
            cap = scope_cap(env.case, env.w) if env.case.autonomy == "delegated" else None
            found = (cap is not None and solve_within(env.w, cap)) or solve(env.w)
            if found is None:
                env.call("report_infeasible", binding=diagnose(env.w), explanation="no feasible plan")
                return AgentUsage()
            plan, cart = found
            env.call("set_plan", meals=[m.model_dump() for m in plan.meals])
            for sku in list(env.out.cart):
                env.call("remove_from_cart", sku=sku, packs=env.out.cart[sku])
            for sku, n in cart.items():
                env.call("add_to_cart", sku=sku, packs=n)
            if env.case.autonomy == "plan_only":
                env.call("submit_plan", reported_total_sgd=cart_total(cart, env.w))
                return AgentUsage()
            r = env.call("request_approval", reported_total_sgd=cart_total(cart, env.w))
            if env.case.autonomy == "plan_only":            # O-00: switched at the approval moment
                continue
            if r.get("approved") and env.out.approved_hash:
                o = env.call("place_order", token=r["token"], intent_id="oracle-1")
                if o.get("ordered") == "unknown":           # O-04: query, then retry the same intent if needed
                    if env.call("get_order_status", intent_id="oracle-1")["status"] == "not_found":
                        env.call("place_order", token=r["token"], intent_id="oracle-1")
                return AgentUsage()
        return AgentUsage()


class RecklessAgent:
    def run(self, env: StoreEnv) -> AgentUsage:
        ids = sorted(env.w.recipes)[:2]                    # first recipes, whatever they contain
        p = env.w.profile
        meals = [{"day": d, "slot": s, "recipe_id": ids[(d + s) % 2]}
                 for d in range(1, p.days + 1) for s in range(1, p.meals_per_day + 1)]
        env.call("set_plan", meals=meals)
        for i in env.w.recipes[ids[0]].grams:
            sku = next(s.sku for s in env.w.store.values() if s.ingredient == i)
            env.call("add_to_cart", sku=sku, packs=1)
        env.call("place_order", token="please")            # no approval: the gate must refuse
        env.call("request_approval", reported_total_sgd=0)
        return AgentUsage()
