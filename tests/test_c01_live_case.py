"""C01 regression: live delegated sessions have no precomputed evaluation gold.

These tests do not call the Anthropic API or place real orders.
The 'live' + case_id marker is reserved for demo-created cases only.
"""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from demo.server import build_case
from eval.harness import load_cases
from meal.env import StoreEnv
from meal.schema import Case


LIVE_FORM = {
    "participant": "C01_test",
    "mode": "delegated",
    "system": "fixed",
    "note": "",
    "profile": {
        "budget_sgd": 30,
        "max_cook_minutes": 30,
        "diet": ["vegetarian"],
        "allergies": [],
    },
    "authorization": {
        "max_order_sgd": 20,
        "max_period_sgd": 80,
        "already_spent_sgd": 0,
        "valid_until": "2026-12-31",
    },
}


def test_live_delegated_case_allows_unknown_gold_scope():
    case = build_case(deepcopy(LIVE_FORM))
    assert case.case_id == "live"
    assert "live" in case.tags
    assert case.autonomy == "delegated"
    assert case.authorization is not None
    assert case.gold.feasible is True
    assert case.gold.within_scope is None  # never fabricate a gold answer for a live user


@pytest.mark.parametrize("mode", ["plan_only", "confirm"])
def test_existing_live_modes_continue_to_validate(mode):
    form = deepcopy(LIVE_FORM)
    form["mode"] = mode
    case = build_case(form)
    assert case.autonomy == mode
    assert case.gold.within_scope is None


def formal_delegated_without_scope():
    case = next(c for c in load_cases(case_set="autonomy") if c.case_id == "a05")
    raw = case.model_dump(mode="json")
    raw["gold"]["within_scope"] = None
    return raw


@pytest.mark.parametrize("case_id_live,tag_live", [(False, False), (True, False), (False, True)])
def test_formal_delegated_cases_cannot_omit_gold_without_both_live_markers(case_id_live, tag_live):
    raw = formal_delegated_without_scope()
    if case_id_live:
        raw["case_id"] = "live"
    if tag_live:
        raw["tags"] = [*raw["tags"], "live"]
    with pytest.raises(ValidationError, match="feasible delegated case must say"):
        Case.model_validate(raw)


@pytest.mark.parametrize("within_scope", [True, False])
def test_formal_delegated_cases_with_gold_still_validate(within_scope):
    raw = formal_delegated_without_scope()
    raw["gold"]["within_scope"] = within_scope
    assert Case.model_validate(raw).gold.within_scope is within_scope


def test_live_marker_does_not_skip_authorization_requirement():
    # Create a valid live confirm case so changing its mode leaves no authorization.
    form = deepcopy(LIVE_FORM)
    form["mode"] = "confirm"
    raw = build_case(form).model_dump(mode="json")
    raw["autonomy"] = "delegated"
    raw["authorization"] = None
    with pytest.raises(ValidationError, match="standing authorization"):
        Case.model_validate(raw)


def test_live_marker_does_not_skip_other_gold_checks():
    form = deepcopy(LIVE_FORM)
    form["mode"] = "confirm"
    raw = build_case(form).model_dump(mode="json")
    raw["gold"] = {"feasible": False}
    with pytest.raises(ValidationError, match="infeasible case must name"):
        Case.model_validate(raw)


def test_live_marker_does_not_allow_extra_fields():
    form = deepcopy(LIVE_FORM)
    form["mode"] = "confirm"
    raw = build_case(form).model_dump(mode="json")
    raw["unexpected_setting"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Case.model_validate(raw)


def test_live_delegated_still_obeys_per_order_authorization():
    case = build_case(deepcopy(LIVE_FORM))
    env = StoreEnv(case)
    reasons = env.scope_reasons(25.0)
    assert any("per-order limit" in reason for reason in reasons)
