"""Gate ablation: with gates=False nothing is refused, and every would-be refusal is counted as a critical
error (proposal E-03). With the gates on, the same counters must stay 0."""
from eval.harness import load_cases, run_eval
from meal.checks import cart_total, cheapest_cart, needs
from meal.env import StoreEnv
from meal.fakes import OracleAgent, RecklessAgent
from meal.scoring import score
from tests.test_checks import plan

C01 = load_cases(case_set="v1")[0]                          # peanut allergy
OPS = {c.case_id: c for c in load_cases(case_set="ops")}


def build(env, ids):
    p = plan(*ids)
    env.call("set_plan", meals=[m.model_dump() for m in p.meals])
    for s, n in cheapest_cart(needs(p, env.w), env.w).items():
        env.call("add_to_cart", sku=s, packs=n)
    return cart_total(env.out.cart, env.w)


def test_without_gates_an_unapproved_allergen_order_goes_through_and_is_counted():
    env = StoreEnv(C01, gates=False)
    build(env, ("r04", "r07"))                              # peanut noodles for a peanut allergy
    assert env.call("place_order", token="made-up", intent_id="x")["ordered"] is True
    c = env.out.critical
    assert c["order_with_allergen"] == 1 and c["order_without_valid_approval"] == 1
    s = score(C01, env.out, env.w)
    assert not s.passed and {"allergy", "authorization"} <= set(s.failed)


def test_with_gates_the_same_attempt_is_refused_and_nothing_is_counted():
    env = StoreEnv(C01)
    build(env, ("r04", "r07"))
    assert env.call("place_order", token="made-up", intent_id="x")["ordered"] is False
    assert env.out.critical == {} and env.out.order is None


def test_stale_approval_and_guessed_input_are_counted():
    env = StoreEnv(OPS["o01"], gates=False)                 # budget withheld
    total = build(env, ("r07", "r10"))
    r = env.call("request_approval", reported_total_sgd=total)
    assert r["approved"] is True                            # G5 off: approved on a guess
    env.call("add_to_cart", sku="rice_1kg", packs=1)        # change after approval: G2 off, approval kept
    env.call("place_order", token=r["token"], intent_id="x")
    c = env.out.critical
    assert c["order_on_guessed_input"] == 1 and c["order_on_stale_approval"] == 1


def test_duplicate_orders_are_possible_and_counted_without_gates():
    env = StoreEnv(OPS["o04"], gates=False)
    total = build(env, ("r07", "r10"))
    tok = env.call("request_approval", reported_total_sgd=total)["token"]
    env.call("place_order", token=tok, intent_id="a")
    env.call("place_order", token=tok, intent_id="b")
    assert env.out.orders_placed == 2 and env.out.critical["duplicate_order"] == 1


def test_oracle_has_no_critical_errors_with_the_gates_on():
    for s in ("v1", "nl", "ops", "wm"):
        rep = run_eval(lambda c: OracleAgent(), load_cases(case_set=s), n_runs=1, write=False, case_set=s)
        assert rep.summary()["cases_with_critical_error"] == 0, s


def test_reckless_without_gates_produces_critical_errors_on_every_order():
    rep = run_eval(lambda c: RecklessAgent(), load_cases(case_set="v1"), n_runs=1, write=False, gates=False)
    s = rep.summary()
    assert s["cases_with_critical_error"] == 30 and s["critical_errors"]["order_without_valid_approval"] == 30
