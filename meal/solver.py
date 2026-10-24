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
    limits = {(l.day, l.slot): l.minutes for l in w.note.slot_max_minutes} if w.note is not None else {}
    meals = []
    for k, (d, s) in enumerate(slots):
        rid = ids[k % len(ids)]
        if (d, s) in limits and w.recipes[rid].minutes > limits[(d, s)]:
            fast = [i for i in ids if w.recipes[i].minutes <= limits[(d, s)]]
            rid = fast[0] if fast else rid             # none fast enough: the plan fails its check
        meals.append(Meal(day=d, slot=s, recipe_id=rid))
    return Plan(meals=meals)


def day_plan(day: list[tuple[str, float]], w: World) -> Plan:
    """Catalogue wm: one day's (recipe, portion) per slot, repeated for every day."""
    return Plan(meals=[Meal(day=d, slot=s + 1, recipe_id=r, portion=p)
                       for d in range(1, w.profile.days + 1) for s, (r, p) in enumerate(day)])


def solve_wm(w: World):
    """Catalogue wm: search one day template (breakfast + two mains, each at a documented portion) repeated
    every day. A stated simplification, like ≤3 recipes in v1: it proves feasibility, not optimal variety."""
    from itertools import combinations_with_replacement, product
    from .energy import recipe_nutrients
    from .schema import PORTIONS
    t = w.targets
    if t is None or t["status"] != "ok":
        return None
    ok = allowed_recipes(w)
    kcal = {r: recipe_nutrients(w.recipes[r], w.ingredients)["kcal"] * w.profile.servings for r in ok}
    bks = [(r, p) for r in ok if w.recipes[r].meal_type == "breakfast" for p in PORTIONS]
    mains = [(r, p) for r in ok if w.recipes[r].meal_type == "main" for p in PORTIONS]
    best = None
    for b, (m1, m2) in product(bks, combinations_with_replacement(mains, 2)):
        e = kcal[b[0]] * b[1] + kcal[m1[0]] * m1[1] + kcal[m2[0]] * m2[1]
        if not t["low"] - 1e-6 <= e <= t["high"] + 1e-6:
            continue
        plan = day_plan([b, m1, m2], w)
        cart = cheapest_cart(needs(plan, w), w)
        if cart is None or violations(plan, cart, w):
            continue
        if best is None or cart_total(cart, w) < cart_total(best[1], w):
            best = (plan, cart)
    return best


def solve(w: World) -> tuple[Plan, dict[str, int]] | None:
    """Cheapest valid (plan, cart) found, or None."""
    if w.targets is not None:
        return solve_wm(w)
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
                   if not [v for v in recipe_violations(r, w) if v[0] in ("diet", "allergy", "note")]]
        return "diet" if not by_diet else "time"
    any_stocked = any(cheapest_cart(needs(_plan(ids, w), w), w) is not None
                      for k in (1, 2, 3) for ids in combinations(ok, k))
    return "budget" if any_stocked else "stock"


def scope_cap(case, w: World) -> float | None:
    """Mode ③: the most one order may cost without asking the user, or None if the authorization cannot
    be used at all (revoked, expired, declared allergy — policy O-03)."""
    a = case.authorization
    if a is None or a.revoked or case.today > a.valid_until or w.profile.allergies:
        return None
    return min(a.max_order_sgd, a.max_period_sgd - a.already_spent_sgd)


def solve_within(w: World, cap: float):
    """solve() with the budget tightened to the authorization cap."""
    tight = World(w.ingredients, w.recipes, w.store,
                  w.profile.model_copy(update={"budget_sgd": min(w.profile.budget_sgd, cap)}), note=w.note)
    return solve(tight)
