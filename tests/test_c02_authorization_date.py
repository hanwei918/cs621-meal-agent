"""C02: Live-demo authorization expiry uses Singapore's current calendar date.

Tests run offline with a frozen clock and no Anthropic API or real purchases.
Formal evaluation cases keep their original simulated date.
"""

from datetime import date, datetime, timezone

import pytest

from demo import server
from eval.harness import load_cases
from meal.env import StoreEnv


def live_form(mode="delegated", valid_until="2026-11-01"):
    return {
        "participant": "C02_test", "mode": mode, "system": "fixed", "note": "",
        "profile": {"budget_sgd": 30, "max_cook_minutes": 30,
                    "diet": ["vegetarian"], "allergies": []},
        "authorization": {
            "max_order_sgd": 30, "max_period_sgd": 80,
            "already_spent_sgd": 0, "valid_until": valid_until,
        },
    }


def freeze_utc(monkeypatch, timestamp):
    """Control the exact time without changing the host clock or dependencies."""
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert moment.tzinfo is not None

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is not None, "Live authorization dates must have explicit timezone"
            return moment.astimezone(tz)

    monkeypatch.setattr(server, "datetime", FrozenDateTime)


@pytest.mark.parametrize("timestamp,expected", [
    ("2026-10-31T15:59:00Z", date(2026, 10, 31)),  # 23:59 in Singapore
    ("2026-10-31T16:00:00Z", date(2026, 11, 1)),   # 00:00 in Singapore
    ("2026-11-01T02:00:00Z", date(2026, 11, 1)),
])
def test_singapore_calendar_day_is_used_for_live_case(monkeypatch, timestamp, expected):
    freeze_utc(monkeypatch, timestamp)
    case = server.build_case(live_form())
    assert case.today == expected
    assert StoreEnv(case).t_get_profile()["today"] == expected.isoformat()


@pytest.mark.parametrize("mode", ["plan_only", "confirm", "delegated"])
def test_all_live_modes_use_current_singapore_date(monkeypatch, mode):
    freeze_utc(monkeypatch, "2026-11-01T01:00:00Z")
    assert server.build_case(live_form(mode)).today == date(2026, 11, 1)


def test_past_authorization_is_not_accepted_as_standing(monkeypatch):
    freeze_utc(monkeypatch, "2026-10-31T02:00:00Z")
    env = StoreEnv(server.build_case(live_form(valid_until="2026-10-26")))
    assert any("authorization expired" in msg for msg in env.scope_reasons(12.0))


def test_authorization_expiring_today_is_still_valid(monkeypatch):
    freeze_utc(monkeypatch, "2026-10-31T02:00:00Z")
    env = StoreEnv(server.build_case(live_form(valid_until="2026-10-31")))
    assert env.scope_reasons(12.0) == []


def test_frozen_formal_evaluation_dates_stay_unchanged(monkeypatch):
    freeze_utc(monkeypatch, "2026-11-01T02:00:00Z")
    cases = load_cases(case_set="autonomy")
    assert cases
    assert all(case.today == date(2026, 10, 25) for case in cases)


def test_expired_standing_authorization_requires_approval_in_demo(monkeypatch, tmp_path):
    """End-to-end fixed-planner smoke test; no paid model or external store."""
    import time

    freeze_utc(monkeypatch, "2026-10-31T02:00:00Z")
    monkeypatch.setattr(server, "STORE", server.FileStore(tmp_path))
    session = server.Session(live_form(valid_until="2026-10-26"))
    deadline = time.monotonic() + 5
    while session.status == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert session.status == "awaiting_approval", session.error
        assert session.pending_approval is not None
        assert session.pending_approval["asked_because"]
        assert any("expired" in reason for reason in session.pending_approval["asked_because"])
        assert session.env.out.orders_placed == 0
    finally:
        session.answer(False, "declined in offline test")
        while session.live and time.monotonic() < deadline + 1:
            time.sleep(0.01)
    assert session.status == "done", session.error
    assert session.env.out.orders_placed == 0
