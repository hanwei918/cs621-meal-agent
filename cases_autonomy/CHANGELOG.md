# Autonomy case set changelog

- 2026-10-22 — 12 cases (a01–a12; 5 boundary) built by `scripts/build_autonomy_cases.py`: ① plan only ×3,
  ② confirm ×1, ③ pre-authorized ×8 (inside scope, per-order limit, declared allergy, expired, period limit,
  revoked at approval, stock-out at approval inside scope, tight limit). All hand-written judgements,
  including `within_scope`, agreed with the code checks and the solver on the first build.
  Code-only systems: oracle 12/12, fixed planner 10/12 (no re-planning: a10, a11), reckless 0/12.
  **Not frozen.** No LLM run yet.
