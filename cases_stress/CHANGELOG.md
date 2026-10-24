# Stress set changelog

- 2026-10-24 — 42 cases built by `scripts/build_stress_cases.py`: events k = 0–5 (3 each), days 3/5/7 with one
  event (3 each), note constraints 1–4 (3 each), mixed k3·d7·n3 (3). Gold by construction: one witness
  (omelette + chickpea salad) that no event and no note touches; budget = witness × 1.25; checked against every
  rule after all events and by the solver. A first build used ids like `se0_0`, which the canonical-file filter
  (made to skip iCloud copies) silently dropped: renamed `se0a`. Oracle 42/42. 

- 2026-10-24 — **FROZEN (stress v1)** before any LLM run (gold is by construction; nothing to tune). Runs on code
  `a34208b`: Haiku agent 3 runs 0.960 ± 0.014 (5 silent give-ups: sd7c ×1, sxb ×2, sxc ×2), single call 0.548,
  fixed 0.476. Fingerprint `b9a4cd72f25a39d91116448de4cac3b11525248dd518708e756c9fa61a458f91`.
