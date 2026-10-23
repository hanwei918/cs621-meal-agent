# NL events case set changelog

- 2026-10-23 — 8 cases (e01–e08; 3 boundary) built by `scripts/build_nl_events_cases.py`, all mode ②. The user
  speaks mid-run (`user_message` event, after N tool calls or at approval): e01 eggs at home make a S$8 budget
  feasible (no plan at step 0), e02 no egg at approval, e03 first dinner <= 10 min, e04 flatmate's peanut allergy
  at approval, e05 "Looks good, thanks!" (control: re-approve and order), e06 "throw in some chicken" against a
  vegetarian profile (a message never relaxes the profile), e07 weight-loss kcal target mid-run (decline),
  e08 two messages that must accumulate. Gold reading = note + every message, written by hand. Witnesses valid,
  solver agrees; e01–e04 and e08 bite against the cheapest step-0 plan. Every message revokes approval.
  Code-only systems: oracle 8/8, fixed planner 1/8 (e06 only), reckless 0/8.
  Prompt: one paragraph added on mid-run messages (agent only). **Not frozen.** No LLM run yet.

- 2026-10-23 — **FROZEN (nl_events v1), cases unchanged.** Debug runs on code `1610e56` (1 run each, not for
  reporting): Haiku agent `20261023T025001Z_agent_claude-haiku-5-5_nl_events` 8/8 ($0.04), read case by case
  (re-declared and re-approved after every message; e08 accumulated both; e07 declined). Haiku single call
  `20261023T035812Z_single_call_claude-haiku-5-5_nl_events` 2/8 ($0.01): e06 (control by design) and e03 **by
  luck** (it happened to put a 10-minute salad at day 1 dinner); e01 hit max_tokens on the step-0-infeasible
  budget (as v1 c16), counted as a failure; e02/e04/e05/e08 stopped when the message revoked approval; e07
  ordered instead of declining. Fingerprint `cdc92aead1e51fe5e9a8664eb6b1a89cb84e7ff56c92ef5451ce463ab12959e6`.
