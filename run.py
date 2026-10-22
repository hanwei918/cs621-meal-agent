"""Run an evaluation.

  .venv/bin/python run.py --system oracle      # grader check: must be 1.000 (never reported)
  .venv/bin/python run.py --system reckless    # grader check: must be 0.000
  .venv/bin/python run.py --system agent --model claude-haiku-5-5 --cases c01 --runs 1 --yes   # once ③ lands
"""
from __future__ import annotations

import argparse
import os
import sys

from eval.harness import RUNS, load_cases, run_eval
from meal.fakes import OracleAgent, RecklessAgent


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--system", required=True, choices=["oracle", "reckless", "agent", "single_call", "fixed"])
    a.add_argument("--model", default="claude-haiku-5-5")
    a.add_argument("--cases", default=None)
    a.add_argument("--set", default="v1", choices=["v1", "autonomy"], help="case set (v1 is frozen, mode ② only)")
    a.add_argument("--runs", type=int, default=1)
    a.add_argument("--workers", type=int, default=4, help="cases run in parallel")
    a.add_argument("--yes", action="store_true")
    x = a.parse_args(argv)
    cs = load_cases(x.cases.split(",") if x.cases else None, case_set=x.set)
    if x.system in ("oracle", "reckless"):
        cls = OracleAgent if x.system == "oracle" else RecklessAgent
        make, model, write = (lambda c: cls()), "none", False
    elif x.system == "fixed":
        from meal.baselines import FixedPlanner
        make, model, write = (lambda c: FixedPlanner()), "none", True
    else:
        if not x.yes:
            sys.exit("paid run: add --yes after checking the cost of a 3-case run first")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY is not set in this shell")
        from meal.agent import MealAgent
        from meal.baselines import SingleCallBaseline
        cls = MealAgent if x.system == "agent" else SingleCallBaseline
        make, model, write = (lambda c: cls(x.model)), x.model, True
    rep = run_eval(make, cs, n_runs=x.runs, name=x.system, model=model, write=write, workers=x.workers, case_set=x.set)
    print(rep.render())
    if rep.run_dir:
        print(f"→ {rep.run_dir.relative_to(RUNS.parent)}")


if __name__ == "__main__":
    main()
