"""Gate ablation: the same agent with and without the code gates, side by side.

For each case set, picks the latest `<set>_nogates` run and the latest gated run made AFTER the ablation
switch existed (so both carry critical-error counts), and prints pass rate and critical errors per run.
Run: .venv/bin/python scripts/ablation_table.py [set ...]   (default: v1 nl ops wm)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
KINDS = ["order_breaks_constraints", "order_with_allergen", "order_without_valid_approval", "order_on_stale_approval",
         "order_on_guessed_input", "misreported_total", "duplicate_order"]


def latest(case_set: str, gates: bool):
    tag = "" if case_set == "v1" else f"_{case_set}"
    pat = f"*_agent_claude-haiku-5-5{tag}{'' if gates else '_nogates'}"
    for d in sorted(RUNS.glob(pat), reverse=True):
        s = json.loads((d / "summary.json").read_text())
        if "critical_errors" in s and s["meta"].get("gates", True) == gates:
            return d.name, s
    return None, None


def main(sets):
    print("| set | gates | runs | pass rate | cases with a critical error | " + " | ".join(KINDS) + " |")
    print("|---|---|---|---|---|" + "---|" * len(KINDS))
    for cs in sets:
        for gates in (True, False):
            name, s = latest(cs, gates)
            if s is None:
                print(f"| {cs} | {'on' if gates else 'off'} | — | — | — |" + " — |" * len(KINDS))
                continue
            n = s["n_cases"] * s["n_runs"]
            crit = s["critical_errors"]
            print(f"| {cs} | {'on' if gates else 'off'} | {s['n_runs']} | {s['pass_mean']:.3f} ± {s['pass_sd']:.3f} | "
                  f"{s['cases_with_critical_error']}/{n} | " + " | ".join(str(crit.get(k, 0)) for k in KINDS) + " |")
    print("\nCritical errors are counted when an order (or plan-only submission) is created, against the truth: "
          "true profile, gold reading of the note, store after events.")


if __name__ == "__main__":
    main(sys.argv[1:] or ["v1", "nl", "ops", "wm"])
