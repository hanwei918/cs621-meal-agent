"""Demo server: a real person approves; a decline goes back to the agent; messages arrive mid-run; sessions save."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from demo import server
from meal.env import StoreEnv
from tests.test_nl import N, order


def test_without_an_approver_the_scripted_user_approves():
    assert order(N["n08"], ["r07", "r10"]).out.order is not None


def test_a_person_who_declines_blocks_the_order_and_the_comment_reaches_the_agent():
    env = StoreEnv(N["n08"], approver=lambda req: (False, "too much salad"))
    from tests.test_checks import plan
    from meal.checks import cart_total, cheapest_cart, needs
    p = plan("r07", "r10")
    env.call("set_plan", meals=[m.model_dump() for m in p.meals])
    for s, n in cheapest_cart(needs(p, env.w), env.w).items():
        env.call("add_to_cart", sku=s, packs=n)
    r = env.call("request_approval", reported_total_sgd=cart_total(env.out.cart, env.w))
    assert r == {"approved": False, "refused_by": "user", "comment": "too much salad"}
    assert env.out.approved_hash is None and env.out.user_asks == 1
    assert env.call("place_order", token="anything")["ordered"] is False


def test_say_delivers_on_the_next_call():
    env = StoreEnv(N["n08"])
    env.say("no eggs please")
    assert any("no eggs please" in n for n in env.call("view_cart")["notices"])


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", tmp_path)
    server.CURRENT["s"] = None
    srv = server.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        except urllib.error.HTTPError as e:                              # 4xx bodies are JSON too
            return json.loads(e.read())
    yield call, tmp_path
    srv.shutdown()


def wait(call, *statuses):
    for _ in range(100):
        s = call("/api/state")
        if s["status"] in statuses:
            return s
        time.sleep(0.05)
    raise AssertionError(s["status"])


FORM = {"participant": "T01", "mode": "confirm", "system": "fixed", "note": "",
        "profile": {"budget_sgd": 30, "max_cook_minutes": 30, "diet": ["vegetarian"], "allergies": []}}


def test_end_to_end_decline_then_approve_then_save(live):
    call, sessions = live
    assert call("/api/start", FORM)["ok"]
    s = wait(call, "awaiting_approval")
    assert s["pending_approval"]["total_sgd"] > 0 and s["result"]["ordered"] is False
    assert call("/api/start", FORM).get("error")                         # one session at a time
    call("/api/approve", {"approve": True})
    s = wait(call, "done")
    assert s["result"]["ordered"] and s["result"]["approved_by"] == "user"
    assert s["result"]["violations_against_profile_and_declared"] == []
    saved = call("/api/survey", {"understood": 4})["saved_to"]
    rec = json.loads(next(sessions.glob("T01_confirm_*.json")).read_text())
    assert rec["survey"]["understood"] == 4 and rec["approvals"][0]["approved"] is True and saved


def test_declining_in_the_ui_stops_a_planner_that_cannot_replan(live):
    call, _ = live
    call("/api/start", FORM)
    wait(call, "awaiting_approval")
    call("/api/approve", {"approve": False, "comment": "no"})
    s = wait(call, "done")
    assert not s["result"]["ordered"] and s["result"]["user_asks"] == 1


def test_study_summary_counts_only_what_was_recorded(live):
    from scripts.study_summary import load, summary
    call, sessions = live
    call("/api/start", FORM)
    wait(call, "awaiting_approval")
    call("/api/approve", {"approve": False, "comment": "too dear"})
    wait(call, "done")
    call("/api/survey", {"understood": 2, "trust_mode": 4, "preferred_mode": "confirm", "minutes_per_week_now": 90})
    s = summary(load(sessions))
    m = s["by_mode"]["confirm"]
    assert s["sessions"] == 1 and m["ordered"] == 0 and m["carts_declined_by_person"] == 1
    assert m["understood"] == "2 (n=1)" and m["knew_cart"] == "—"
    assert s["preferred_mode"] == {"confirm": 1} and s["self_reported_minutes_per_week_now"] == {"median": 90, "n": 1}
