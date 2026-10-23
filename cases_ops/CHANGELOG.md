# Ops case set changelog

- 2026-10-24 — 8 cases (o01–o08; 4 boundary) built by `scripts/build_ops_cases.py`, all mode ② at the start:
  P-01 missing budget (o01), invalid cooking time 0 (o02), missing allergies that turn out to be peanut (o03),
  nothing missing as the avoidable-clarification control (o04); O-04 timeout with no order created (o05) and with
  the order created (o06); O-00 switch to plan only after 4 calls (o07) and at the approval moment (o08).
  Witnesses valid against the true profile after the events; solver agrees.
  Code-only systems: oracle 8/8, fixed planner 2/8 (crashes on a missing budget, cannot query a timeout),
  reckless 0/8. Agent prompt gained the intent-id / status / ask-never-guess / mode-switch lines (code changes
  are recorded in each run's `code`). **Not frozen.** No LLM run yet.
