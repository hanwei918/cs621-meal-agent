# Meal Agent — CS621 Agentic AI group project

Plans meals within a user's diet, allergies, budget and cooking time; shops in a synthetic
store; and re-plans when stock, prices or user preferences change. Three autonomy modes:
① plan only (no purchase), ② confirm each order (human approval), and ③ delegated within
standing authorization limits (with human escalation where required). Shopping and
approval checks run in code; natural-language understanding still relies on the model.

## Project map

```
meal/schema.py       Contracts: Ingredient, Recipe, StoreItem, Case, Outcome
meal/agent.py        Claude tool loop: tool selection, observations and termination
meal/env.py          Simulated store, 19 tools, state, approvals, events and order gates
meal/checks.py       Shared deterministic constraints for gates, scoring and solver
meal/solver.py       Bounded reference solver to cross-check authored gold cases
meal/runner.py       Per-case execution, tool trace, usage and latency
meal/scoring.py      Pass/fail and named failure checks
meal/baselines.py    Fixed-rule planner and single-call baseline
meal/fakes.py        Oracle/Reckless agents for checking the grader, not model results
eval/harness.py      Evaluation runs, mean ± SD, failures, cost, traces and code fingerprint
eval/pricing.py      Estimated API cost from recorded token usage
data/                Synthetic catalogue: 24 ingredients, 12 recipes, 25 store SKUs
data_wm/             Weight-management catalogue: 29 ingredients, 15 recipes, 30 SKUs
cases*/              Frozen synthetic evaluation case sets (130 cases in seven sets)
tests/               Offline regression tests (257 passing as of C12)
demo/                Local web demo with user approval and presenter controls
deploy/              Firebase Hosting / Cloud Run deployment instructions
```

## Evaluation and autonomy

Case sets: `v1` (30), `autonomy` (12), `nl` (16), `nl_events` (8), `ops` (8),
`wm` (11), and `stress` (45). Each formal run records its dataset fingerprint;
new results in `runs/` include `results.jsonl` (per-case outcome, `tool_trace`,
`latency_s`, usage and cost), `summary.json` (aggregate metrics and code version),
and a row in `runs/ledger.csv`. A SHA-256 source fingerprint is used when Git
metadata is unavailable. Historical results are not automatically recalculated
when the code or estimated pricing changes.

Autonomy modes: ① plan only · ② confirm each order · ③ delegated within limits.
Delegated orders with nonempty user notes or mid-run user messages require human
approval; standing authorization also checks limits and expiry. See
`docs/MEAL_PLANNING_POLICY.md` for policy details. These are synthetic tests,
not proof of safety for real purchases or medical/nutrition guidance.

## Set up and run locally

From the project root on macOS/Linux (Python 3.11 is used by the Dockerfile):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q                 # 257 tests after C01–C12
.venv/bin/python run.py --system oracle       # offline grader check; no API key
.venv/bin/python run.py --system reckless     # offline grader check; no API key
.venv/bin/python demo/server.py               # http://127.0.0.1:8621
```

The local demo's `fixed` planner works without an API key. Real Claude agent
runs need `ANTHROPIC_API_KEY` in the environment and may incur charges. For an
explicit paid evaluation (first check budget and model access):

```bash
.venv/bin/python run.py --system agent --model claude-haiku-5-5 --cases c01 --runs 1 --yes
```

For repeated evaluation, select the case set with `--set` and repetitions with
`--runs` (for example `--runs 3`); do not assume the CLI defaults to three.

For shared deployment see `deploy/README.md` (Firebase Hosting → Cloud Run,
passcode and spend caps). The protocol for a human study is in
`docs/USER-STUDY.md`; local sessions are saved under `user-study/sessions/`.

**Scope:** Synthetic store and test personas; no real payments. Human study
results are not established here. Not nutrition or medical advice.
