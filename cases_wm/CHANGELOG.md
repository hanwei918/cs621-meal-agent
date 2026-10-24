# WM case set changelog

- 2026-10-24 — 11 cases (w01–w11; 5 boundary) built by `scripts/build_wm_cases.py`, catalogue `data_wm/`, mode ②.
  Plannable: persona A (the proposal's own fixture, 1,888.65 kcal) loss (w01), A + rice sold out at approval (w07),
  A + "no egg" note (w09), B vegetarian maintenance (w02), B vegetarian + peanut allergy (w10), E loss on S$31 (w08).
  Review: below the 1,500 floor (w03), target BMI 17.3 (w04), pregnancy (w05), age 17 (w06), target = current (w11).
  Witness days written by hand from the per-serving kcal table; every one passed the energy band and the solver
  agreed. A first build marked review cases as infeasible/diet — wrong, the gold of a review case is its status;
  fixed before any run. Code-only systems: oracle 11/11, fixed planner 0/11, reckless 0/11.
  **Not frozen.** No LLM run yet.
