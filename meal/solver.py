"""Reference solver (owner: ①). Answers "is there ANY plan that satisfies every hard constraint?"
for a world state, by exhaustive search over plans built from 1–3 distinct allowed recipes.

It does not set the gold. The case author writes `gold.feasible` by hand; a test checks that the
solver agrees on every case. Disagreement means the case or the solver is wrong — find out which.
The search space (≤3 distinct recipes, used as evenly as possible) is a stated simplification.
"""
from __future__ import annotations

from itertools import combinations

from .checks import World, cart_total, cheapest_cart, needs, recipe_violations, violations
from .schema import Meal, Plan


def allowed_recipes(w: World) -> list[str]:
    return sorted(r.id for r in w.recipes.values() if not recipe_violations(r, w))


def _plan(ids: tuple[str, ...], w: World) -> Plan:
    slots = [(d, s) for d in range(1, w.profile.days + 1) for s in range(1, w.profile.meals_per_day + 1)]
    return Plan(meals=[Meal(day=d, slot=s, recipe_id=ids[k % len(ids)]) for k, (d, s) in enumerate(slots)])


def solve(w: World) -> tuple[Plan, dict[str, int]] | None:
    """Cheapest valid (plan, cart) found, or None."""
    ok = allowed_recipes(w)
    best = None
    for k in (1, 2, 3):
        for ids in combinations(ok, k):
            plan = _plan(ids, w)
            cart = cheapest_cart(needs(plan, w), w)
            if cart is None or violations(plan, cart, w):
                continue
            if best is None or cart_total(cart, w) < cart_total(best[1], w):
                best = (plan, cart)
    return best


BINDING_RULE = ("apply the constraints in this order: diet and allergies, then cooking time, then stock, then "
                "budget; the binding constraint is the first one after which no valid plan is left")


def diagnose(w: World) -> str:
    """Which constraint binds when solve() finds nothing, by BINDING_RULE."""
    ok = allowed_recipes(w)
    if not ok:
        by_diet = [r for r in w.recipes.values()
                   if not [v for v in recipe_violations(r, w) if v[0] in ("diet", "allergy")]]
        return "diet" if not by_diet else "time"
    any_stocked = any(cheapest_cart(needs(_plan(ids, w), w), w) is not None
                      for k in (1, 2, 3) for ids in combinations(ok, k))
    return "budget" if any_stocked else "stock"
