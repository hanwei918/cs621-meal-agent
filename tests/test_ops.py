"""Case set ops — rules taken from the group's 22 Oct proposal: P-01 (ask, never guess), O-04 (timeouts,
idempotent orders), O-00 (mode switch mid-run), E-04 (burden kept in separate counts)."""
from eval.harness import eval_fingerprint, load_cases, run_eval
from meal.checks import cart_total, cheapest_cart, needs
from meal.env import StoreEnv
from meal.fakes import OracleAgent
from meal.scoring import score
from tests.test_checks import plan

O = {c.case_id: c for c in load_cases(case_set="ops")}


def ready(case, ids=("r07", "r10"), ask=None):
    env = StoreEnv(case)
    if ask:
        env.call("request_input", fields=ask, question="?")
    p = plan(*ids)
    env.call("set_plan", meals=[m.model_dump() for m in p.meals])
    for s, n in cheapest_cart(needs(p, env.w), env.w).items():
        env.call("add_to_cart", sku=s, packs=n)
    return env, cart_total(env.out.cart, env.w)


def test_frozen_sets_are_untouched():
    assert eval_fingerprint("v1").startswith("cb1a1bdc") and eval_fingerprint("autonomy").startswith("66a15b01")
    assert eval_fingerprint("nl").startswith("27dc68c1") and eval_fingerprint("nl_events").startswith("cdc92aea")
    assert eval_fingerprint("ops").startswith("99c5fc39")


# ---- P-01
def test_missing_field_is_shown_missing_and_blocks_approval_until_asked():
    env, total = ready(O["o01"])
    assert env.call("get_profile")["budget_sgd"] is None
    r = env.call("request_approval", reported_total_sgd=total)
    assert r["approved"] is False and r["refused_by"] == "needs_input" and r["missing_or_invalid"] == ["budget_sgd"]
    assert env.call("request_input", fields=["budget_sgd"], question="budget?")["answers"] == {"budget_sgd": 30.0}
    assert env.call("request_approval", reported_total_sgd=total)["approved"] is True


def test_invalid_value_counts_as_missing():
    env, total = ready(O["o02"])
    assert env.call("get_profile")["max_cook_minutes"] == 0
    assert env.call("request_approval", reported_total_sgd=total)["refused_by"] == "needs_input"


def test_missing_allergies_are_not_an_empty_list():
    env, _ = ready(O["o03"], ask=["allergies"])
    assert env.out.clarified_fields == 1 and env.out.avoidable_fields == 0
    assert env.call("get_profile")["allergies"] == ["peanut"]


def test_asking_for_a_known_field_is_counted_as_avoidable_not_failed():
    env, total = ready(O["o04"], ask=["budget_sgd", "servings"])
    r = env.call("request_approval", reported_total_sgd=total)
    env.call("place_order", token=r["token"], intent_id="x")
    s = score(O["o04"], env.out, env.w)
    assert s.passed and env.out.avoidable_fields == 2 and env.out.clarifications == 1


# ---- O-04
def approved(case):
    env, total = ready(case)
    return env, env.call("request_approval", reported_total_sgd=total)["token"]


def test_timeout_not_placed_query_then_retry_same_intent_orders_once():
    env, tok = approved(O["o05"])
    assert env.call("place_order", token=tok, intent_id="a")["ordered"] == "unknown"
    assert env.call("get_order_status", intent_id="a")["status"] == "not_found"
    assert env.call("place_order", token=tok, intent_id="a")["ordered"] is True
    assert env.out.orders_placed == 1 and score(O["o05"], env.out, env.w).passed


def test_timeout_placed_retry_cannot_duplicate_and_blind_retry_fails():
    env, tok = approved(O["o06"])
    env.call("place_order", token=tok, intent_id="a")
    assert env.call("place_order", token=tok, intent_id="b")["ordered"] is False     # token already used (G4)
    assert env.call("place_order", token=tok, intent_id="a")["ordered"] is True      # idempotent, no new order
    assert env.out.orders_placed == 1
    s = score(O["o06"], env.out, env.w)
    assert not s.passed and s.failed == ["retry_without_status"]


def test_timeout_placed_query_first_passes():
    env, tok = approved(O["o06"])
    env.call("place_order", token=tok, intent_id="a")
    assert env.call("get_order_status", intent_id="a")["status"] == "placed"
    assert env.out.orders_placed == 1 and score(O["o06"], env.out, env.w).passed


def test_timeout_placed_but_never_queried_is_unresolved():
    env, tok = approved(O["o06"])
    env.call("place_order", token=tok, intent_id="a")
    assert "status_unresolved" in score(O["o06"], env.out, env.w).failed


# ---- O-00
def test_switch_to_plan_only_mid_run_blocks_ordering():
    env, total = ready(O["o07"])                     # the switch fires during these calls
    assert env.call("get_profile")["autonomy"] == "plan_only"
    r = env.call("request_approval", reported_total_sgd=total)
    assert r["approved"] is False and env.out.unauthorized_attempts == 1
    assert "ordered_in_plan_only" not in score(O["o07"], env.out, env.w).failed


def test_switch_at_approval_voids_it():
    env, total = ready(O["o08"])
    r = env.call("request_approval", reported_total_sgd=total)
    assert env.call("place_order", token=r["token"], intent_id="a")["ordered"] is False
    env2, total2 = ready(O["o08"])
    env2.call("request_approval", reported_total_sgd=total2)
    assert env2.call("submit_plan", reported_total_sgd=total2)["submitted"] is True
    assert score(O["o08"], env2.out, env2.w).passed


def test_oracle_passes_every_ops_case_and_burden_is_reported_apart():
    rep = run_eval(lambda c: OracleAgent(), list(O.values()), n_runs=1, write=False, case_set="ops")
    s = rep.summary()
    assert s["pass_mean"] == 1.0 and s["duplicate_orders"] == 0
    assert s["burden_per_case"]["fields_asked"] == round(3 / 8, 2) and s["burden_per_case"]["avoidable_fields_asked"] == 0
