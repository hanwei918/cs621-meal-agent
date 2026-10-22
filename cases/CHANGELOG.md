# Case changelog

Gold changes only when the plan changes. A debug run may expose an ambiguous case INPUT; it never
justifies a new answer. Record every change here.

## 2026-10-22 — 30 cases (14 boundary, 47%), not yet frozen

- Built by `scripts/build_cases.py` from hand-written specs: profile, overrides, events, feasible or
  not, binding constraint, witness recipes, derivation. The script computes each witness cart and
  checks it passes every constraint in the post-event world; for infeasible cases it checks the solver
  finds nothing and names the same binding. All 30 author judgements agreed on the first build.
- New event trigger `on: approval` (fires the moment the user first approves a cart, revoking it).
  Step-count events fired too early (c02's at steps 3 and 5) to test re-planning, and late ones
  could never fire if an agent finished first while the gold assumed they had. 8 cases use it.
- Gold now carries a `witness` for every feasible case, so feasibility does not rest on the solver.
- Code-only systems on the 30 cases: oracle 30/30, fixed planner 21/30 (fails 7 of 8 approval-event
  cases — it does not re-plan — and names the wrong binding on c08, c13), reckless 0/30.
- Building these cases exposed a real env bug: an event firing on a list-returning tool
  (search_recipes, find_items) crashed `env.call`. Fixed; list results now come back as
  `{"results": [...], "notices": [...]}` when there are notices. Regression test seen red first.
