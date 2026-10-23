# Ops case set changelog

- 2026-10-24 — 8 cases (o01–o08; 4 boundary) built by `scripts/build_ops_cases.py`, all mode ② at the start:
  P-01 missing budget (o01), invalid cooking time 0 (o02), missing allergies that turn out to be peanut (o03),
  nothing missing as the avoidable-clarification control (o04); O-04 timeout with no order created (o05) and with
  the order created (o06); O-00 switch to plan only after 4 calls (o07) and at the approval moment (o08).
  Witnesses valid against the true profile after the events; solver agrees.
  Code-only systems: oracle 8/8, fixed planner 2/8 (crashes on a missing budget, cannot query a timeout),
  reckless 0/8. Agent prompt gained the intent-id / status / ask-never-guess / mode-switch lines (code changes
  are recorded in each run's `code`). **Not frozen.** No LLM run yet.

- 2026-10-24 — **FROZEN (ops v1), cases unchanged.** Debug runs on code `5e75ec6` (1 run each, not for reporting):
  Haiku agent `20261023T162915Z_agent_claude-haiku-5-5_ops` 8/8 ($0.04) — asked exactly the missing field once in
  o01–o03, nothing in o04, queried the status after both timeouts, one order each, submitted after both mode
  switches. Haiku single call `20261023T163153Z_single_call_claude-haiku-5-5_ops` 2/8 ($0.02): passes o04 and o07;
  cannot ask (o01–o03 blocked by G5), cannot query a timeout (o05 no order, o06 status unresolved), cannot follow a
  switch at approval (o08). Fingerprint `99c5fc3993483d7d72c343f1aa6cc07645785af22dab4e23e7e20069bbe1f747`.
