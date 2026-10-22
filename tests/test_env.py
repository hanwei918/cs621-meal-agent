"""④ the approval and order gates, and event injection."""
from eval.harness import load_cases
from meal.env import StoreEnv
from tests.test_checks import C01_CART, plan

C = {c.case_id: c for c in load_cases()}


def ready(env):
    env.call("set_plan", meals=[m.model_dump() for m in plan("r01", "r07").meals])
    for s, n in C01_CART.items():
        env.call("add_to_cart", sku=s, packs=n)


def test_order_without_approval_is_refused_and_counted():
    env = StoreEnv(C["c01"]); ready(env)
    assert env.call("place_order", token="anything")["ordered"] is False
    assert env.out.unauthorized_attempts == 1 and env.out.order is None


def test_approval_refused_when_a_constraint_fails():
    env = StoreEnv(C["c01"])
    env.call("set_plan", meals=[m.model_dump() for m in plan("r04").meals])   # peanut
    r = env.call("request_approval", reported_total_sgd=0)
    assert r["approved"] is False and any(v.startswith("allergy") for v in r["violations"])


def test_change_after_approval_revokes_it():
    env = StoreEnv(C["c01"]); ready(env)
    tok = env.call("request_approval", reported_total_sgd=16.10)["token"]
    env.call("add_to_cart", sku="garlic_100g", packs=1)
    assert env.call("place_order", token=tok)["ordered"] is False


def test_events_fire_on_step_count():
    env = StoreEnv(C["c02"])
    env.call("view_cart"); env.call("view_cart")
    r = env.call("view_cart")                                                  # step 3: tofu event fires
    assert any("tofu_300g is now out of stock" in n for n in r["notices"]) and env.w.store["tofu_300g"].stock == 0


def test_event_after_approval_revokes_it():
    from meal.schema import Event
    case = C["c01"].model_copy(update={"events": [Event(after_step=8, kind="price_change", sku="rice_1kg", price_sgd=3.0)]})
    env = StoreEnv(case); ready(env)                                           # 6 calls
    tok = env.call("request_approval", reported_total_sgd=16.10)["token"]      # call 7
    r = env.call("view_cart")                                                  # call 8: price event fires
    assert any("Approval revoked" in n for n in r["notices"])
    assert env.call("place_order", token=tok)["ordered"] is False


def test_valid_flow_orders_exactly_the_approved_cart():
    env = StoreEnv(C["c01"]); ready(env)
    tok = env.call("request_approval", reported_total_sgd=16.10)["token"]
    assert env.call("place_order", token=tok)["ordered"] is True
    assert env.out.order == C01_CART and env.out.order_total_sgd == 16.10


def test_notice_on_a_list_returning_tool_is_not_lost():
    """Regression (c22): an event firing on search_recipes / find_items must not crash, and must reach the agent."""
    env = StoreEnv(C["c22"])                                   # rice_1kg out of stock after step 2
    env.call("get_profile")
    r = env.call("search_recipes", max_minutes=30)
    assert any("rice_1kg is now out of stock" in n for n in r["notices"]) and len(r["results"]) > 0


def test_approval_refused_when_the_reported_total_is_wrong():
    """Debug run 20261022T083102Z, c02: the single call asked for approval with a stale total
    (S$12.80 vs S$18.60). The user must never approve a price that is not the real one."""
    env = StoreEnv(C["c01"]); ready(env)
    r = env.call("request_approval", reported_total_sgd=12.80)
    assert r["approved"] is False and any(v.startswith("total") for v in r["violations"])
