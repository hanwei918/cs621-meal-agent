"""C03: a subsequent model declaration cannot silently relax previously declared user restrictions.

All cases use the local simulated environment. No LLM or external services are called.
"""
from eval.harness import load_cases
from meal.checks import recipe_violations
from meal.env import StoreEnv


NL = {case.case_id: case for case in load_cases(case_set="nl")}
EVENTS = {case.case_id: case for case in load_cases(case_set="nl_events")}


def env_for(case_id="n03"):
    return StoreEnv(NL[case_id])


def test_later_empty_declaration_cannot_remove_earlier_ingredient_exclusion():
    env = env_for()
    assert "error" not in env.call("declare_constraints", exclude_ingredients=["peanut_butter"])
    before = env.out.declared.copy()
    rejected = env.call("declare_constraints")
    assert "error" in rejected
    assert "peanut_butter" in rejected["error"]
    assert env.out.declared == before
    assert env.w.note.exclude_ingredients == ["peanut_butter"]
    assert any(kind == "note" for kind, _ in recipe_violations(env.w.recipes["r04"], env.w))


def test_second_message_cannot_drop_first_message_exclusion():
    env = StoreEnv(EVENTS["e08"])
    assert "error" not in env.call("declare_constraints", exclude_ingredients=["cucumber"])
    result = env.call("declare_constraints", exclude_ingredients=["egg"])
    assert "error" in result
    assert env.w.note.exclude_ingredients == ["cucumber"]
    assert "error" not in env.call("declare_constraints", exclude_ingredients=["cucumber", "egg"])
    assert set(env.w.note.exclude_ingredients) == {"cucumber", "egg"}


def test_previous_recipe_exclusion_cannot_be_dropped():
    env = env_for()
    assert "error" not in env.call("declare_constraints", exclude_recipes=["r04"])
    result = env.call("declare_constraints", exclude_recipes=[])
    assert "error" in result and "r04" in result["error"]
    assert env.w.note.exclude_recipes == ["r04"]


def test_slot_limit_cannot_be_removed():
    env = env_for()
    limits = [{"day": 1, "slot": 1, "minutes": 12}]
    assert "error" not in env.call("declare_constraints", slot_max_minutes=limits)
    result = env.call("declare_constraints")
    assert "error" in result
    assert "day 1" in result["error"]
    assert env.w.note.slot_max_minutes[0].minutes == 12


def test_slot_limit_cannot_be_relaxed():
    env = env_for()
    env.call("declare_constraints", slot_max_minutes=[{"day": 1, "slot": 1, "minutes": 10}])
    result = env.call("declare_constraints", slot_max_minutes=[{"day": 1, "slot": 1, "minutes": 15}])
    assert "error" in result
    assert env.w.note.slot_max_minutes[0].minutes == 10


def test_tighter_slot_limit_is_allowed():
    env = env_for()
    env.call("declare_constraints", slot_max_minutes=[{"day": 1, "slot": 1, "minutes": 15}])
    result = env.call("declare_constraints", slot_max_minutes=[{"day": 1, "slot": 1, "minutes": 10}])
    assert "error" not in result
    assert env.w.note.slot_max_minutes[0].minutes == 10


def test_duplicate_slot_limits_cannot_hide_a_relaxation():
    env = env_for()
    env.call("declare_constraints", slot_max_minutes=[{"day": 1, "slot": 1, "minutes": 10}])
    result = env.call("declare_constraints", slot_max_minutes=[
        {"day": 1, "slot": 1, "minutes": 20},
        {"day": 1, "slot": 1, "minutes": 30},
    ])
    assert "error" in result
    assert env.w.note.slot_max_minutes[0].minutes == 10


def test_adding_restrictions_and_resubmitting_all_old_ones_is_allowed():
    env = env_for()
    env.call("declare_constraints", exclude_ingredients=["peanut_butter"], exclude_recipes=["r04"])
    result = env.call("declare_constraints", exclude_ingredients=["peanut_butter", "egg"],
                      exclude_recipes=["r04", "r01"])
    assert "error" not in result
    assert set(env.out.declared["exclude_ingredients"]) == {"peanut_butter", "egg"}
    assert set(env.out.declared["exclude_recipes"]) == {"r04", "r01"}


def test_invalid_update_is_atomic_and_does_not_revoke_approval():
    from meal.checks import cart_total
    case = NL["n03"]
    env = StoreEnv(case)
    env.call("declare_constraints", exclude_ingredients=["peanut_butter"])
    env.call("set_plan", meals=[{"day": d, "slot": s, "recipe_id": "r07"}
                                 for d in range(1, 4) for s in range(1, 3)])
    # Build a valid cart using the normal deterministic helper.
    from meal.checks import cheapest_cart, needs
    cart = cheapest_cart(needs(env.out.plan, env.w), env.w)
    for sku, packs in cart.items():
        env.call("add_to_cart", sku=sku, packs=packs)
    approved = env.call("request_approval", reported_total_sgd=cart_total(env.out.cart, env.w))
    assert approved.get("approved")
    original_hash, original_token = env.out.approved_hash, env._token
    result = env.call("declare_constraints", exclude_ingredients=[])
    assert "error" in result
    assert env.out.approved_hash == original_hash
    assert env._token == original_token
    assert env.w.note.exclude_ingredients == ["peanut_butter"]


def test_pantry_quantity_can_still_be_corrected_when_restrictions_are_preserved():
    env = env_for()
    env.call("declare_constraints", exclude_ingredients=["peanut_butter"], pantry_add={"rice": 500})
    result = env.call("declare_constraints", exclude_ingredients=["peanut_butter"], pantry_add={"rice": 300})
    assert "error" not in result
    assert env.w.note.pantry_add == {"rice": 300}


def test_initial_empty_declaration_and_unknown_ids_behave_as_before():
    env = env_for()
    assert "error" not in env.call("declare_constraints")
    assert "error" in env.call("declare_constraints", exclude_ingredients=["not_an_ingredient"])
    assert env.w.note.exclude_ingredients == []
