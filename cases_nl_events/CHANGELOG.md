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
