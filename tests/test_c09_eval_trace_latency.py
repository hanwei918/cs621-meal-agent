"""C09: offline trajectory and per-case latency regression tests (no paid API)."""
from __future__ import annotations

import json
from dataclasses import fields

import pytest

from eval import harness
from eval.harness import load_cases, run_eval
from meal.runner import AgentUsage, CaseResult, run_case
from meal.schema import Outcome
from meal.scoring import Score


CASE = load_cases(["c01"])[0]


class TwoTools:
    def run(self, env):
        env.call("get_profile")
        env.call("view_cart")
        return AgentUsage()


class BadTool:
    def run(self, env):
        env.call("not_a_tool")
        return AgentUsage()


class ExplodingAgent:
    def run(self, env):
        env.call("get_profile")
        raise RuntimeError("offline simulated failure")


def test_run_case_captures_tool_order_arguments_and_outputs():
    r = run_case(TwoTools(), CASE)
    assert [t["tool"] for t in r.tool_trace] == ["get_profile", "view_cart"]
    assert r.tool_trace[0]["arguments"] == {}
    assert r.tool_trace[0]["result"]["autonomy"] == "confirm"
    assert "total_sgd" in r.tool_trace[1]["result"]


def test_trace_tool_error_as_a_return_value():
    r = run_case(BadTool(), CASE)
    assert r.tool_trace[0]["tool"] == "not_a_tool"
    assert "unknown tool" in r.tool_trace[0]["result"]["error"]


def test_direct_run_returns_latency_and_original_environment_event_log():
    r = run_case(TwoTools(), CASE)
    assert isinstance(r.latency_s, float) and r.latency_s >= 0.0
    assert isinstance(r.log, list)
    assert r.outcome.steps == 2


def test_run_case_supports_external_trace_sink():
    sink = []
    r = run_case(TwoTools(), CASE, trace_sink=sink)
    assert sink is r.tool_trace and len(sink) == 2


def test_exception_retains_partial_trace_and_elapsed_time_in_harness():
    rep = run_eval(lambda c: ExplodingAgent(), [CASE], n_runs=1, write=False)
    r = rep.rows[0].result
    assert r.score.passed is False
    assert r.error and "offline simulated failure" in r.error
    assert [x["tool"] for x in r.tool_trace] == ["get_profile"]
    assert isinstance(r.latency_s, float) and r.latency_s >= 0.0


def test_normal_and_failed_cases_are_saved_with_trace_and_latency(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    rep = run_eval(lambda c: TwoTools(), [CASE], n_runs=1, write=True, model="-", name="offline")
    row = json.loads((rep.run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["case"] == "c01" and row["run"] == 0
    assert row["events"] == rep.rows[0].result.log
    assert row["tool_trace"] == rep.rows[0].result.tool_trace
    assert row["latency_s"] == rep.rows[0].result.latency_s
    assert isinstance(row["latency_s"], float)
    assert "outcome" in row and "score" in row and "cost_usd" in row and "usage" in row


def test_error_case_is_saved_with_partial_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "RUNS", tmp_path)
    rep = run_eval(lambda c: ExplodingAgent(), [CASE], n_runs=1, write=True, model="-", name="offline-error")
    row = json.loads((rep.run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["error"].startswith("RuntimeError:")
    assert len(row["tool_trace"]) == 1
    assert row["latency_s"] >= 0


def test_multi_run_and_parallel_cases_have_separate_traces():
    cases = load_cases(["c01", "c02"])
    rep = run_eval(lambda c: TwoTools(), cases, n_runs=2, workers=2, write=False)
    assert len(rep.rows) == 4
    assert all(len(r.result.tool_trace) == 2 for r in rep.rows)
    assert len({id(r.result.tool_trace) for r in rep.rows}) == 4


def test_old_caseresult_positional_construction_is_compatible():
    x = CaseResult("c", Outcome(), Score("c", False, ["error"]))
    assert x.tool_trace == [] and x.latency_s == 0.0


def test_trace_preserves_tool_arguments_exactly():
    class Cart:
        def run(self, env):
            env.call("add_to_cart", sku="rice_1kg", packs=2)
            return AgentUsage()
    r = run_case(Cart(), CASE)
    assert r.tool_trace[0]["arguments"] == {"sku": "rice_1kg", "packs": 2}
    assert "result" in r.tool_trace[0]
