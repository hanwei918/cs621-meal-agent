# NL case set changelog

- 2026-10-22 — 16 cases (n01–n16; 9 boundary) built by `scripts/build_nl_cases.py`, all mode ②:
  note → ingredient exclusion ×5 (n01 eggs, n02 cucumber, n03 flatmate's peanut allergy, n07 no meat but
  seafood, n09 Singlish "no spicy"), recipe exclusion (n04 fried rice), slot time limits (n05, n10),
  pantry (n06), controls (n08 "anything works", n13 "eat a bit healthier" — in scope), out of scope
  (n11 weight loss / kcal, n12 pregnancy), injected store descriptions (n14 allergy, n15 token, n16 price).
  Gold readings written by hand from the policy. Every witness passed under the gold reading; the solver
  agreed on feasibility. Every non-control note **bites**: the cheapest plan that ignores it breaks the gold
  reading (n02/n03 needed a peanut-butter promo, S$2.00, to make that true; n06 has no plan at all without it).
  Code-only systems: oracle 16/16, fixed planner 5/16 (passes only the controls and the injections, since it
  reads no text), reckless 0/16.
  **Not frozen.** No LLM run yet.
