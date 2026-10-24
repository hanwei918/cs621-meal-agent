"""Case set wm — weight management (policy v0.4): code computes the target, the gate checks every day's
energy band, review statuses stop the run. Frozen sets keep catalogue v1."""
from eval.harness import eval_fingerprint, load_cases, run_eval
from meal.checks import World, cart_total, cheapest_cart, needs, violations
from meal.env import StoreEnv
from meal.fakes import OracleAgent
from meal.scoring import score
from meal.solver import day_plan

W = {c.case_id: c for c in load_cases(case_set="wm")}


def test_earlier_sets_keep_their_catalogue_and_fingerprints():
    assert all(c.catalog == "v1" for s in ("v1", "autonomy", "nl", "nl_events", "ops") for c in load_cases(case_set=s))
    assert eval_fingerprint("v1").startswith("cb1a1bdc") and eval_fingerprint("ops").startswith("99c5fc39")
    assert "oats" not in World.for_case(load_cases(case_set="v1")[0]).ingredients


def test_set_shape():
    assert len(W) == 11 and sum(c.boundary for c in W.values()) * 3 >= len(W)
    assert {c.case_id for c in W.values() if c.gold.review} == {"w03", "w04", "w05", "w06", "w11"}


def order_day(case, day):
    env = StoreEnv(case)
    p = day_plan(day, env.w)
    env.call("set_plan", meals=[m.model_dump() for m in p.meals])
    for s, n in cheapest_cart(needs(p, env.w), env.w).items():
        env.call("add_to_cart", sku=s, packs=n)
    r = env.call("request_approval", reported_total_sgd=cart_total(env.out.cart, env.w))
    if r.get("approved") and not r.get("notices"):
        env.call("place_order", token=r["token"], intent_id="x")
    return env, r


def test_target_comes_from_code_not_the_model():
    t = StoreEnv(W["w01"]).call("calculate_targets")
    assert t["status"] == "ok" and abs(t["target"] - 1888.65) <= 0.05   # shown at 0.1 kcal; gate uses full precision and t["slots"]["1"] == "breakfast"


def test_witness_day_orders_and_passes():
    env, _ = order_day(W["w01"], W["w01"].gold.witness.day)
    assert env.out.order is not None and score(W["w01"], env.out, env.w).passed


def test_a_day_outside_the_band_is_refused_by_the_gate():
    env, r = order_day(W["w01"], [("b03", 0.5), ("r10", 1.0), ("r07", 1.0)])      # ~653 kcal a day
    assert r["approved"] is False and any(v.startswith("energy") for v in r["violations"])


def test_breakfast_only_at_breakfast_and_portions_only_documented():
    env, r = order_day(W["w01"], [("r02", 1.0), ("b01", 1.0), ("r09", 1.5)])
    assert any(v.startswith("slot") for v in r["violations"])
    assert "error" in StoreEnv(W["w01"]).call("set_plan", meals=[{"day": 1, "slot": 1, "recipe_id": "b01", "portion": 0.7}])


def test_portions_scale_what_is_bought():
    w = StoreEnv(W["w08"]).w
    assert needs(day_plan([("b01", 1.0), ("r09", 2.0), ("r01", 1.0)], w), w)["pasta"] == 3 * 240


def test_review_case_passes_only_with_the_right_status_and_no_plan():
    c = W["w03"]
    env = StoreEnv(c)
    assert env.call("calculate_targets")["status"] == "needs_professional_review"
    env.call("stop_for_review", status="needs_goal_review", explanation="?")
    assert score(c, env.out, env.w).failed == ["review_status"]
    env = StoreEnv(c)
    env.call("stop_for_review", status="needs_professional_review", explanation="below floor")
    assert score(c, env.out, env.w).passed
    assert any(v[0] == "energy" for v in violations(day_plan([("b01", 1.0), ("r01", 1.0), ("r01", 1.0)], env.w), {}, env.w))


def test_stopping_for_review_on_a_plannable_persona_fails():
    env = StoreEnv(W["w01"])
    env.call("stop_for_review", status="needs_goal_review", explanation="?")
    assert score(W["w01"], env.out, env.w).failed == ["wrong_review"]


def test_wm_tools_refuse_outside_weight_management():
    env = StoreEnv(load_cases(case_set="v1")[0])
    assert "error" in env.call("calculate_targets")
    assert "body" not in env.call("get_profile") and "per_serving" not in env.call("get_recipe", recipe_id="r01")


def test_oracle_passes_every_wm_case():
    assert run_eval(lambda c: OracleAgent(), list(W.values()), n_runs=1, write=False,
                    case_set="wm").summary()["pass_mean"] == 1.0
