# Meal-planning & grocery agent — CS621 group project (candidate topic)

Plans three days of meals within a user's diet, allergies, budget and cooking time; shops in a
simulated store; re-plans when items go out of stock, prices change or preferences change; orders
only after the user approves the exact cart. Every check is code — no LLM judge.

```
meal/schema.py      ① contracts: Ingredient, Recipe, StoreItem, Case (profile, events, gold), Outcome
data/*.json         ① synthetic ingredients (24), recipes (12), store (25 SKUs)
cases/c01..c30      ① 30 cases (14 boundary) built by scripts/build_cases.py, each with a checked witness
meal/solver.py      ① reference solver: is any valid plan possible? (cross-checks the hand-written gold)
meal/checks.py      ②④ the hard constraints, one definition for gate, grade and solver
meal/scoring.py     ② pass/fail per case + which checks failed
eval/harness.py     ② run_eval: 3 runs, mean ± sd, failures by check and tag, cost ledger
meal/env.py         ④ simulated store + tools; approval and order gates; event injection
meal/agent.py       ③ the agent: Claude tool loop (fake-client tested; no live run yet)
meal/baselines.py   ⑤ fixed planner · single call (one structured call, applied through the same tools)
meal/fakes.py       Oracle / Reckless fake agents — check the grader, never reported
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                 # 31 tests, each seen failing first
.venv/bin/python run.py --system oracle       # must be 1.000
.venv/bin/python run.py --system reckless     # must be 0.000
```

Synthetic data only. No real payments. Not nutrition or medical advice.
