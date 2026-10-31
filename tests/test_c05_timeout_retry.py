"""C05: an ambiguous order timeout requires status for the *same* intent before retry.

Synthetic StoreEnv only: no Anthropic calls, network calls, or real purchases.
"""
from meal.env import StoreEnv
from tests.test_ops import O, approved


def _timeout(case_id="o05", intent="intent-c05"):
    env, token = approved(O[case_id])
    first = env.call("place_order", token=token, intent_id=intent)
    assert first["ordered"] == "unknown"
    assert env._awaiting_status == intent
    return env, token, intent


def test_blind_retry_same_intent_not_placed_is_hard_blocked():
    env, token, intent = _timeout()
    retry = env.call("place_order", token=token, intent_id=intent)
    assert retry["ordered"] is False
    assert "get_order_status" in retry["error"]
    assert env.out.orders_placed == 0
    assert env._awaiting_status == intent
    assert env.out.blind_retries == 1


def test_blind_retry_other_intent_not_placed_is_hard_blocked():
    env, token, intent = _timeout()
    retry = env.call("place_order", token=token, intent_id="wrong-intent")
    assert retry["ordered"] is False
    assert env.out.orders_placed == 0
    assert env._awaiting_status == intent
    assert env.out.blind_retries == 1


def test_blind_retry_same_intent_placed_is_hard_blocked_even_if_idempotent():
    env, token, intent = _timeout("o06")
    assert env.out.orders_placed == 1
    retry = env.call("place_order", token=token, intent_id=intent)
    assert retry["ordered"] is False
    assert env.out.orders_placed == 1
    assert env.out.blind_retries == 1
    assert env.out.order_confirmed is False


def test_blind_retry_other_intent_placed_is_hard_blocked():
    env, token, intent = _timeout("o06")
    retry = env.call("place_order", token=token, intent_id="other")
    assert retry["ordered"] is False
    assert env._awaiting_status == intent
    assert env.out.orders_placed == 1


def test_query_unrelated_intent_does_not_clear_awaiting_status():
    env, _, intent = _timeout()
    result = env.call("get_order_status", intent_id="unrelated")
    assert result["status"] == "not_found"
    assert env._awaiting_status == intent


def test_unrelated_query_does_not_authorize_a_retry():
    env, token, intent = _timeout()
    env.call("get_order_status", intent_id="unrelated")
    retry = env.call("place_order", token=token, intent_id=intent)
    assert retry["ordered"] is False
    assert env.out.orders_placed == 0
    assert env.out.blind_retries == 1


def test_correct_not_found_status_allows_retry_of_same_intent():
    env, token, intent = _timeout()
    assert env.call("get_order_status", intent_id=intent)["status"] == "not_found"
    assert env._awaiting_status is None
    retry = env.call("place_order", token=token, intent_id=intent)
    assert retry["ordered"] is True
    assert env.out.orders_placed == 1
    assert env.out.blind_retries == 0


def test_correct_placed_status_confirms_without_creating_another_order():
    env, _, intent = _timeout("o06")
    result = env.call("get_order_status", intent_id=intent)
    assert result["status"] == "placed"
    assert env.out.order_confirmed is True
    assert env.out.orders_placed == 1
    assert env._awaiting_status is None


def test_wrong_id_after_not_found_status_is_refused():
    env, token, intent = _timeout()
    env.call("get_order_status", intent_id=intent)
    retry = env.call("place_order", token=token, intent_id="new-id")
    assert retry["ordered"] is False
    assert env.out.orders_placed == 0
    assert env.call("place_order", token=token, intent_id=intent)["ordered"] is True
    assert env.out.orders_placed == 1


def test_status_query_without_timeout_does_not_break_normal_order():
    env, token = approved(O["o04"])
    assert env.call("get_order_status", intent_id="unknown")["status"] == "not_found"
    assert env.call("place_order", token=token, intent_id="normal")['ordered'] is True
    assert env.out.orders_placed == 1


def test_replay_of_confirmed_order_does_not_duplicate():
    env, token, intent = _timeout("o06")
    env.call("get_order_status", intent_id=intent)
    replay = env.call("place_order", token=token, intent_id=intent)
    assert replay["ordered"] is True
    assert env.out.orders_placed == 1
    assert env.out.blind_retries == 0


def test_gate_ablation_can_still_expose_blind_retry_for_comparison():
    env, token, intent = _timeout()
    env.gates = False
    result = env.call("place_order", token=token, intent_id=intent)
    assert result["ordered"] is True
    assert env.out.blind_retries == 1
    assert env.out.orders_placed == 1
