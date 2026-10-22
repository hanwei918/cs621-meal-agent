# Case changelog

Gold changes only when the plan changes. A debug run may expose an ambiguous case INPUT; it never
justifies a new answer. Record every change here.

## 2026-10-22 — v1 FROZEN: 30 cases, no gold change

Debug runs (Haiku, 1 run each, not for reporting): agent `20261022T030932Z` 29/30, single call
`20261022T083102Z` 20/30. Two problems were in the SPEC, not the cases:

- **Binding constraint was undefined (c13).** With chickpeas sold out, "stock" and "time" (risotto
  takes 40 min) could both be argued; the single call said time. Rule now stated in the tool
  description and both prompts, and the solver follows it: apply diet + allergies, then cooking
  time, then stock, then budget; the first after which no valid plan is left is the binding one.
  Rebuilding the 30 cases under the rule changed no gold.
- **The approval gate did not check the reported total (c02).** The single call asked for approval
  with S$12.80 computed from pre-event prices; the real cart was S$18.60, and it was approved. G1 now
  refuses approval when the reported total differs from the real total, so a user can never approve
  a wrong price. Code check, not model behaviour.
- Agent failure c30 (gave up after a price shock instead of re-planning) is a genuine model error;
  the case stays as is.
- Prompts changed after the debug runs, so those runs are not comparable with formal runs.
- **Frozen.** Formal runs must report `meta.eval_sha256` = `cb1a1bdc0034f63f6a8264dfb406e18bab346f0a4596737543f254c98c75ffd9`.

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
