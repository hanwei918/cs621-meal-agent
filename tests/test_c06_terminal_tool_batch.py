"""C06: terminal actions must stop the current tool batch and the model loop.

Scripted Claude responses only: never calls Anthropic or a real payment service.
"""
import json

import pytest

from eval.harness import load_cases
from meal.agent import MealAgent, finished
from meal.env import StoreEnv
from tests.test_agent import C, C01_CART, FakeClient, GOOD, last_result, resp, use
from tests.test_modes import A, build_witness


def _run(env, blocks, prefix=None):
    script = list(prefix or []) + [lambda messages: resp(blocks),
                                   lambda messages: resp([], stop="end_turn")]
    client = FakeClient(script)
    agent = MealAgent("claude-haiku-5-5", client=client, max_nudges=0)
    usage = agent.run(env)
    return agent, usage, client


def _result(agent, uid):
    return last_result(agent.messages, uid)


def test_order_followed_by_cart_change_is_not_executed():
    env = StoreEnv(C["c01"])
    def final(messages):
        token = last_result(messages, "tu3")["token"]
        return resp([use("place_order", {"token": token, "intent_id": "c06-order"}, 4),
                     use("add_to_cart", {"sku": "egg_10pk", "packs": 1}, 5),
                     use("view_cart", {}, 6)])
    client = FakeClient(GOOD[:4] + [final])
    agent = MealAgent("claude-haiku-5-5", client=client, max_nudges=0)
    usage = agent.run(env)
    assert env.out.order_confirmed and env.out.orders_placed == 1
    assert env.out.cart == C01_CART
    assert env.out.steps == 9  # profile, plan, 5 cart operations, approval, order
    assert usage.stop_reason == "result" and usage.turns == 5
    assert len(agent.messages[-1]["content"]) == 3  # every tool_use gets a tool_result
    for uid in ("tu5", "tu6"):
        item = next(r for r in agent.messages[-1]["content"] if r["tool_use_id"] == uid)
        assert item["is_error"] is True
        assert "not executed" in json.loads(item["content"])["error"].lower()


def test_submit_plan_stops_following_tool_and_agent_loop():
    env = StoreEnv(A["a01"])
    total = build_witness(env, A["a01"])
    cart_before = dict(env.out.cart)
    agent, usage, client = _run(env, [use("submit_plan", {"reported_total_sgd": total}, 1),
                                       use("remove_from_cart", {"sku": next(iter(cart_before)), "packs": 1}, 2)])
    assert env.out.submitted and env.out.cart == cart_before
    assert usage.stop_reason == "result" and len(client.sent) == 1
    assert "not executed" in _result(agent, "tu2")["error"]


def test_review_stops_following_tools_and_agent_loop():
    env = StoreEnv(C["c03"])
    agent, usage, client = _run(env, [use("stop_for_review", {"status": "needs_professional_review", "explanation": "x"}, 1),
                                       use("set_plan", {"meals": []}, 2)])
    assert env.out.review_status == "needs_professional_review" and env.out.steps == 1
    assert usage.stop_reason == "result" and len(client.sent) == 1
    assert "not executed" in _result(agent, "tu2")["error"]


@pytest.mark.parametrize("name,args,flag", [
    ("decline_request", {"reason": "out of scope"}, "declined"),
    ("report_infeasible", {"binding": "budget", "explanation": "none"}, "declared_infeasible"),
])
def test_other_terminal_actions_stop_current_batch(name, args, flag):
    env = StoreEnv(C["c03"])
    agent, usage, client = _run(env, [use(name, args, 1), use("add_to_cart", {"sku": "egg_10pk", "packs": 1}, 2)])
    assert getattr(env.out, flag) and env.out.steps == 1 and not env.out.cart
    assert usage.stop_reason == "result" and len(client.sent) == 1
    assert "not executed" in _result(agent, "tu2")["error"]


def test_nonterminal_tool_errors_do_not_stop_batch():
    env = StoreEnv(C["c03"])
    agent, usage, client = _run(env, [use("add_to_cart", {"sku": "missing", "packs": 1}, 1),
                                       use("get_profile", {}, 2)])
    assert "error" in _result(agent, "tu1")
    assert _result(agent, "tu2")["autonomy"] == "confirm"
    assert env.out.steps == 2 and usage.stop_reason == "end_turn"


def test_valid_sequence_of_nonterminal_actions_all_execute():
    env = StoreEnv(C["c03"])
    agent, usage, client = _run(env, [use("get_profile", {}, 1), use("view_cart", {}, 2)], [])
    assert env.out.steps == 2 and _result(agent, "tu2")["total_sgd"] == 0.0


def test_all_terminal_outcomes_are_recognised_by_shared_finished():
    env = StoreEnv(C["c03"])
    assert not finished(env.out)
    for attr, val in [("order_confirmed", True), ("submitted", True), ("declared_infeasible", True),
                      ("declined", True), ("review_status", "needs_goal_review")]:
        new_env = StoreEnv(C["c03"])
        setattr(new_env.out, attr, val)
        assert finished(new_env.out)


def test_nonterminal_approval_rejection_does_not_stop_batch():
    env = StoreEnv(C["c03"])
    agent, usage, client = _run(env, [use("request_approval", {"reported_total_sgd": 999}, 1),
                                       use("view_cart", {}, 2)])
    assert _result(agent, "tu1")["approved"] is False
    assert _result(agent, "tu2")["cart"] == {}
    assert env.out.steps == 2
