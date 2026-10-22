"""② / ④ hard-constraint checks — one definition used by the gate, the grade and the solver."""
from eval.harness import load_cases
from meal.checks import World, cart_total, violations
from meal.env import StoreEnv
from meal.schema import Meal, Plan
from meal.solver import solve

C = {c.case_id: c for c in load_cases()}


def plan(*ids, days=3, per_day=2):
    slots = [(d, s) for d in range(1, days + 1) for s in range(1, per_day + 1)]
    return Plan(meals=[Meal(day=d, slot=s, recipe_id=ids[k % len(ids)]) for k, (d, s) in enumerate(slots)])


C01_CART = {"rice_1kg": 1, "egg_10pk": 2, "spring_onion_100g": 2, "soy_sauce_300ml": 1, "tomato_500g": 1}


def test_hand_derivation_of_c01_matches_code():
    w = World.for_case(C["c01"])
    p = plan("r01", "r07")                         # r01 x3 + r07 x3, as in the case derivation
    assert violations(p, C01_CART, w) == []
    assert cart_total(C01_CART, w) == 16.10


def kinds(p, cart, w):
    return {k for k, _ in violations(p, cart, w)}


def test_each_constraint_is_caught():
    w = World.for_case(C["c01"])                   # peanut allergy, <= 30 min, S$40
    assert "allergy" in kinds(plan("r04"), {}, w)                    # peanut noodles
    assert "time" in kinds(plan("r05"), {}, w)                       # 35-minute dumpling soup
    assert "coverage" in kinds(plan("r01", "r07"), {"rice_1kg": 1}, w)
    assert "meals" in kinds(Plan(meals=plan("r01").meals[:5]), C01_CART, w)
    assert "stock" in kinds(plan("r01", "r07"), dict(C01_CART, rice_1kg=11), w)
    assert "budget" in kinds(plan("r01", "r07"), dict(C01_CART, salmon_300g=4), w)
    w2 = World.for_case(C["c02"])                  # vegetarian, no egg
    assert {"diet", "allergy"} <= kinds(plan("r02", "r01"), {}, w2)


def final_world(case):
    return StoreEnv(case).fire_all()


def test_every_witness_passes_every_constraint_after_the_events():
    from meal.solver import _plan
    for c in load_cases():
        if c.gold.feasible:
            w = final_world(c)
            assert violations(_plan(tuple(c.gold.witness.recipes), w), c.gold.witness.cart, w) == [], c.case_id


def test_solver_agrees_with_hand_written_gold_on_every_case():
    for c in load_cases():
        assert (solve(final_world(c)) is not None) == c.gold.feasible, c.case_id
