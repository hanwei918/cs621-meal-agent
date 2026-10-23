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
    monkeypatch.setattr(server, "STORE", server.FileStore(tmp_path))
    monkeypatch.setattr(server, "PASSCODE", "")
    server.SESSIONS_LIVE.clear()
    srv = server.serve(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None, passcode=""):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "X-Passcode": passcode})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        except urllib.error.HTTPError as e:                              # 4xx bodies are JSON too
            return json.loads(e.read())
    yield call, tmp_path
    srv.shutdown()


def wait(call, sid, *statuses):
    for _ in range(100):
        s = call(f"/api/state?sid={sid}")
        if s["status"] in statuses:
            return s
        time.sleep(0.05)
    raise AssertionError(s["status"])


FORM = {"participant": "T01", "mode": "confirm", "system": "fixed", "note": "",
        "profile": {"budget_sgd": 30, "max_cook_minutes": 30, "diet": ["vegetarian"], "allergies": []}}


def test_end_to_end_approve_then_save(live):
    call, sessions = live
    sid = call("/api/start", FORM)["sid"]
    s = wait(call, sid, "awaiting_approval")
    assert s["pending_approval"]["total_sgd"] > 0 and s["result"]["ordered"] is False
    call("/api/approve", {"sid": sid, "approve": True})
    s = wait(call, sid, "done")
    assert s["result"]["ordered"] and s["result"]["approved_by"] == "user"
    assert s["result"]["violations_against_profile_and_declared"] == []
    assert call("/api/survey", {"sid": sid, "survey": {"understood": 4}})["saved_to"]
    rec = json.loads(next(sessions.glob("T01_confirm_*.json")).read_text())
    assert rec["survey"]["understood"] == 4 and rec["approvals"][0]["approved"] is True


def test_two_participants_do_not_see_each_other(live):
    call, _ = live
    a = call("/api/start", FORM)["sid"]
    b = call("/api/start", dict(FORM, participant="T02"))["sid"]
    wait(call, a, "awaiting_approval"); wait(call, b, "awaiting_approval")
    call("/api/approve", {"sid": a, "approve": False, "comment": "no"})
    assert wait(call, a, "done")["result"]["ordered"] is False
    assert call(f"/api/state?sid={b}")["status"] == "awaiting_approval"      # b untouched by a's decline
    assert call("/api/state?sid=guess")["status"] == "idle"


def test_passcode_is_required_when_set(live, monkeypatch):
    call, _ = live
    monkeypatch.setattr(server, "PASSCODE", "pear42")
    assert call("/api/config")["passcode_required"] is True
    assert call("/api/start", FORM)["error"] == "wrong passcode"
    assert call("/api/catalog")["error"] == "wrong passcode"
    assert "sid" in call("/api/start", FORM, passcode="pear42")


def test_too_many_live_runs_are_refused(live, monkeypatch):
    call, _ = live
    monkeypatch.setattr(server, "MAX_LIVE", 1)
    call("/api/start", FORM)
    assert "busy" in call("/api/start", FORM)["error"]


def test_total_spend_cap_refuses_new_agent_runs_but_not_the_free_planner(live, monkeypatch):
    call, sessions = live
    server.STORE.add_spend(2.5)
    monkeypatch.setattr(server, "TOTAL_CAP", 2.0)
    assert "spending limit" in call("/api/start", dict(FORM, system="agent"))["error"]
    assert "sid" in call("/api/start", FORM)


def test_agent_stops_at_its_spend_cap():
    from meal.agent import MealAgent
    from tests.test_agent import FakeClient, resp, use
    client = FakeClient([lambda m, i=i: resp([use("get_profile", {}, i)]) for i in range(10)])
    a = MealAgent("claude-haiku-5-5", client=client, max_cost_usd=0.0)
    a.run(StoreEnv(N["n08"]))
    assert a.stopped_for_cost and len(client.sent) == 1


def test_declining_in_the_ui_stops_a_planner_that_cannot_replan(live):
    call, _ = live
    sid = call("/api/start", FORM)["sid"]
    wait(call, sid, "awaiting_approval")
    call("/api/approve", {"sid": sid, "approve": False, "comment": "no"})
    s = wait(call, sid, "done")
    assert not s["result"]["ordered"] and s["result"]["user_asks"] == 1


def test_study_summary_counts_only_what_was_recorded(live):
    from scripts.study_summary import load, summary
    call, sessions = live
    sid = call("/api/start", FORM)["sid"]
    wait(call, sid, "awaiting_approval")
    call("/api/approve", {"sid": sid, "approve": False, "comment": "too dear"})
    wait(call, sid, "done")
    call("/api/survey", {"sid": sid, "survey": {"understood": 2, "trust_mode": 4, "preferred_mode": "confirm",
                                                "minutes_per_week_now": 90}})
    s = summary(load(sessions))
    m = s["by_mode"]["confirm"]
    assert s["sessions"] == 1 and m["ordered"] == 0 and m["carts_declined_by_person"] == 1
    assert m["understood"] == "2 (n=1)" and m["knew_cart"] == "—"
    assert s["preferred_mode"] == {"confirm": 1} and s["self_reported_minutes_per_week_now"] == {"median": 90, "n": 1}


# ---- a real person answers request_input; presenter controls
def test_person_answer_is_validated_and_a_bad_answer_keeps_the_field_missing():
    from meal.env import StoreEnv
    from eval.harness import load_cases
    o01 = {c.case_id: c for c in load_cases(case_set="ops")}["o01"]
    env = StoreEnv(o01, answerer=lambda f, q: {"budget_sgd": -5})
    r = env.call("request_input", fields=["budget_sgd"], question="budget?")
    assert r["unanswered"] == ["budget_sgd"] and env.withheld == {"budget_sgd": None}
    env = StoreEnv(o01, answerer=lambda f, q: {"budget_sgd": "25"})
    assert env.call("request_input", fields=["budget_sgd"], question="budget?")["answers"] == {"budget_sgd": 25.0}
    assert env.withheld == {} and env.w.profile.budget_sgd == 25.0


def test_blank_budget_reaches_the_person_as_a_question(live):
    call, sessions = live
    form = dict(FORM, profile=dict(FORM["profile"], budget_sgd=None))
    sid = call("/api/start", form)["sid"]
    s = server.SESSIONS_LIVE[sid]
    assert s.env.withheld == {"budget_sgd": None}
    t = threading.Thread(target=lambda: s.env.call("request_input", fields=["budget_sgd"], question="What is your budget?"))
    t.start()
    q = wait(call, sid, "awaiting_input")["pending_question"]
    assert q == {"fields": ["budget_sgd"], "question": "What is your budget?"}
    call("/api/answer", {"sid": sid, "answers": {"budget_sgd": 22}})
    t.join(2)
    assert s.env.w.profile.budget_sgd == 22.0 and s.questions[0]["answers"] == {"budget_sgd": 22}


def test_presenter_controls_hit_the_current_cart_and_mark_the_session(live):
    call, sessions = live
    sid = call("/api/start", FORM)["sid"]
    wait(call, sid, "awaiting_approval")
    s = server.SESSIONS_LIVE[sid]
    biggest = max(s.env.out.cart, key=lambda k: s.env.out.cart[k] * s.env.w.store[k].price_sgd)
    assert biggest in call("/api/inject", {"sid": sid, "what": "sell_out"})["detail"]
    assert "plan only" in call("/api/inject", {"sid": sid, "what": "plan_only"})["detail"]
    call("/api/approve", {"sid": sid, "approve": False, "comment": "x"})
    wait(call, sid, "done")
    assert s.env.w.store[biggest].stock == 0 and s.env.case.autonomy == "plan_only"
    call("/api/survey", {"sid": sid, "survey": {}})
    from scripts.study_summary import load, summary
    assert summary(load(sessions))["sessions"] == 0 and summary(load(sessions))["excluded_presenter_sessions"] == 1


def test_fixed_rules_with_a_blank_field_stop_with_a_plain_reason(live):
    call, _ = live
    sid = call("/api/start", dict(FORM, profile=dict(FORM["profile"], budget_sgd=None)))["sid"]
    s = wait(call, sid, "error")
    assert "cannot ask" in s["error"] and "budget_sgd" in s["error"] and not s["result"]["ordered"]
