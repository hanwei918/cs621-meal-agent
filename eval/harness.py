"""run_eval, report and cost ledger (owner: ②). Adapted from the RentProof harness.

run_eval(make_agent, cases, n_runs=3) → Report: pass rate mean ± sample sd over runs, failures
clustered by check and by case tag, flaky cases, tokens and USD; written runs go to
runs/<UTC>_<name>_<model>/ (results.jsonl, summary.json) plus one row in runs/ledger.csv.
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from eval.pricing import cost_usd
from meal.runner import CaseResult, run_case
from meal.schema import Case, Outcome
from meal.scoring import Score

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"                     # case set v1 (frozen): mode ② only
CASE_SETS = {"v1": ("cases", "c[0-9]*.json"), "autonomy": ("cases_autonomy", "a[0-9]*.json")}
RUNS = ROOT / "runs"


def _canonical(folder: Path, pattern: str):
    return [f for f in sorted(folder.glob(pattern)) if f.stem.isalnum()]   # skips "c01 2.json"


def load_cases(ids: list[str] | None = None, case_set: str = "v1") -> list[Case]:
    folder, pattern = (CASES, "c[0-9]*.json") if case_set == "v1" else (ROOT / CASE_SETS[case_set][0], CASE_SETS[case_set][1])
    cs = [Case.model_validate_json(f.read_text(encoding="utf-8")) for f in _canonical(folder, pattern)]
    return [c for c in cs if ids is None or c.case_id in ids]


def eval_fingerprint(case_set: str = "v1") -> str:
    """v1 keeps its original definition (cases/ + data/), so the frozen v1 fingerprint is unchanged."""
    h = hashlib.sha256()
    first = (CASES, "c[0-9]*.json") if case_set == "v1" else (ROOT / CASE_SETS[case_set][0], CASE_SETS[case_set][1])
    for folder, pat in (first, (ROOT / "data", "*.json")):
        for f in _canonical(folder, pat):
            h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


@dataclass
class Row:
    case: Case
    run: int
    result: CaseResult


@dataclass
class Report:
    name: str
    model: str
    n_runs: int
    rows: list[Row]
    run_dir: Path | None = None

    def summary(self) -> dict:
        per_run = []
        for k in range(self.n_runs):
            rs = [r for r in self.rows if r.run == k]
            per_run.append(sum(r.result.score.passed for r in rs) / max(1, len(rs)))
        checks, by_tag, by_case = Counter(), Counter(), defaultdict(list)
        asks_by_mode = defaultdict(list)
        for r in self.rows:
            asks_by_mode[r.case.autonomy].append(r.result.outcome.user_asks)
        for r in self.rows:
            by_case[r.case.case_id].append(r.result.score.passed)
            for c in r.result.score.failed:
                checks[c] += 1
                for t in r.case.tags:
                    by_tag[f"{t}:{c}"] += 1
        res = [r.result for r in self.rows]
        return {
            "system": self.name, "model": self.model, "n_cases": len(by_case), "n_runs": self.n_runs,
            "pass_mean": round(statistics.mean(per_run), 4),
            "pass_sd": round(statistics.stdev(per_run), 4) if len(per_run) > 1 else 0.0, "per_run": per_run,
            "failed_checks": dict(checks.most_common()), "failures_by_tag": dict(by_tag.most_common()),
            "flaky": sorted(c for c, v in by_case.items() if 0 < sum(v) < len(v)),
            "always_fail": sorted(c for c, v in by_case.items() if not any(v)),
            "unauthorized_attempts": sum(x.outcome.unauthorized_attempts for x in res),
            "user_asks_per_case_by_mode": {m: round(statistics.mean(v), 2) for m, v in sorted(asks_by_mode.items())},
            "errors": sum(1 for x in res if x.error),
            "steps_per_case": round(statistics.mean(x.outcome.steps for x in res), 2) if res else 0,
            "input_tokens": sum(x.usage.input_tokens for x in res), "output_tokens": sum(x.usage.output_tokens for x in res),
            "cost_usd": round(sum(x.cost_usd for x in res), 4),
        }

    def render(self) -> str:
        s = self.summary()
        return "\n".join([
            f"== {s['system']} · {s['model']}  ({s['n_cases']} cases × {s['n_runs']} runs)",
            f"pass {s['pass_mean']:.3f} ± {s['pass_sd']:.3f}   per run {s['per_run']}",
            f"failed checks: {s['failed_checks'] or 'none'}   unauthorized order attempts: {s['unauthorized_attempts']}",
            f"flaky: {s['flaky'] or 'none'}   always fail: {s['always_fail'] or 'none'}",
            f"cost ${s['cost_usd']:.4f}   steps/case {s['steps_per_case']}   errors {s['errors']}"])


def run_eval(make_agent: Callable, cases: list[Case], n_runs: int = 3, name: str = "agent",
             model: str = "-", write: bool = True, meta: dict | None = None, workers: int = 1,
             case_set: str = "v1") -> Report:
    from concurrent.futures import ThreadPoolExecutor

    def one(c: Case) -> CaseResult:              # each case gets its own agent and its own StoreEnv
        try:
            r = run_case(make_agent(c), c)
        except Exception as e:  # noqa: BLE001 — an error is a failed case, not a crash
            r = CaseResult(c.case_id, Outcome(), Score(c.case_id, False, ["error"]), error=f"{type(e).__name__}: {e}")
        u = r.usage
        r.cost_usd = cost_usd(model, u.input_tokens, u.output_tokens, u.cache_write_tokens, u.cache_read_tokens)
        return r

    rows = []
    for k in range(n_runs):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for c, r in zip(cases, ex.map(one, cases)):           # map keeps case order
                rows.append(Row(c, k, r))
    rep = Report(name, model, n_runs, rows)
    if write:
        rep.run_dir = _write(rep, (meta or {}) | {"case_set": case_set})
    return rep


def _write(rep: Report, meta: dict) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = "" if meta.get("case_set", "v1") == "v1" else f"_{meta['case_set']}"
    d = RUNS / f"{ts}_{rep.name}_{rep.model}{tag}"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in rep.rows:
            x = r.result
            f.write(json.dumps({"case": r.case.case_id, "run": r.run, "score": x.score.as_dict(),
                                "outcome": x.outcome.model_dump(), "events": x.log, "usage": asdict(x.usage),
                                "cost_usd": x.cost_usd, "error": x.error}, ensure_ascii=False) + "\n")
    s = rep.summary() | {"meta": meta | {"eval_sha256": eval_fingerprint(meta.get("case_set", "v1"))}, "utc": ts}
    (d / "summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    ledger, prev = RUNS / "ledger.csv", 0.0
    if ledger.exists():
        old = list(csv.DictReader(ledger.open(encoding="utf-8")))
        prev = float(old[-1]["cumulative_cost_usd"]) if old else 0.0
    new = not ledger.exists()
    with ledger.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "run_dir", "system", "model", "n_cases", "n_runs", "input_tokens", "output_tokens",
                        "cost_usd", "cumulative_cost_usd", "pass_mean", "pass_sd"])
        w.writerow([ts, d.name, s["system"], s["model"], s["n_cases"], s["n_runs"], s["input_tokens"],
                    s["output_tokens"], s["cost_usd"], round(prev + s["cost_usd"], 4), s["pass_mean"], s["pass_sd"]])
    return d
