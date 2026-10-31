"""C08: validate remove_from_cart inputs before any state or approval mutation.

All checks are offline and use the frozen simulated store only.
"""

import pytest

from eval.harness import load_cases
from meal.env import StoreEnv
from tests.test_checks import C01_CART, plan


CASE = next(c for c in load_cases() if c.case_id == "c01")
SKU = next(iter(C01_CART))


def prepared():
    env = StoreEnv(CASE)
    env.call("set_plan", meals=[m.model_dump() for m in plan("r01", "r07").meals])
    for sku, packs in C01_CART.items():
        assert "error" not in env.call("add_to_cart", sku=sku, packs=packs)
    return env


@pytest.mark.parametrize("packs", [-1, -2, -25, 0])
def test_invalid_remove_quantities_do_not_change_cart_or_approval(packs):
    env = prepared()
    token = env.call("request_approval", reported_total_sgd=16.10)["token"]
    cart_before = dict(env.out.cart)
    result = env.call("remove_from_cart", sku=SKU, packs=packs)
    assert "error" in result
    assert env.out.cart == cart_before
    assert env.out.approved_hash == token
    assert env._token == token


def test_unknown_sku_is_rejected_without_state_change():
    env = prepared()
    cart_before = dict(env.out.cart)
    result = env.call("remove_from_cart", sku="not_in_store", packs=1)
    assert "error" in result
    assert env.out.cart == cart_before


def test_invalid_remove_returns_normal_tool_error_and_loop_can_continue():
    env = prepared()
    result = env.call("remove_from_cart", sku=SKU, packs=-1)
    assert result["error"].startswith("ValueError:")
    assert "error" not in env.call("view_cart")


def test_direct_method_rejects_negative_packs():
    env = prepared()
    with pytest.raises(ValueError):
        env.t_remove_from_cart(SKU, -1)


def test_valid_partial_removal_keeps_other_items():
    env = prepared()
    original = env.out.cart.get(SKU, 0)
    # Ensure more than one pack so partial removal exists, even if the witness only needs one.
    env.call("add_to_cart", sku=SKU, packs=2)
    result = env.call("remove_from_cart", sku=SKU, packs=1)
    assert "error" not in result
    assert env.out.cart[SKU] == original + 1
    assert all(env.out.cart.get(k) == v for k, v in C01_CART.items() if k != SKU)


def test_valid_full_removal_deletes_cart_line():
    env = prepared()
    amount = env.out.cart[SKU]
    result = env.call("remove_from_cart", sku=SKU, packs=amount)
    assert "error" not in result
    assert SKU not in env.out.cart


def test_valid_over_removal_deletes_cart_line_without_negative_quantity():
    env = prepared()
    amount = env.out.cart[SKU]
    result = env.call("remove_from_cart", sku=SKU, packs=amount + 3)
    assert "error" not in result
    assert SKU not in env.out.cart


def test_valid_removal_still_revokes_current_approval():
    env = prepared()
    env.call("request_approval", reported_total_sgd=16.10)
    assert env.out.approved_hash is not None
    result = env.call("remove_from_cart", sku=SKU, packs=1)
    assert "error" not in result
    assert env.out.approved_hash is None
