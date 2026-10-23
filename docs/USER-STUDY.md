# User experience: who uses it, how, and what changes — and the study that checks it

The assignment asks: *how is the agent applied, who are the end users, and how does this agent change
their life or work style?* The evaluation sets answer "does it work on cases we wrote". They cannot
answer whether real people write notes the agent understands, whether they can judge a cart quickly,
or which autonomy mode they would accept. This study does that, with the demo (`demo/server.py`).

Everything below marked **assumption** is ours until the study measures it. Nothing in this file is a
result yet; results go in §7 only from `scripts/study_summary.py` output.

## 1. End users (assumption)

People in Singapore who cook at home on a budget and plan a few days at a time:

| Who | Situation | What they need from it |
| --- | --- | --- |
| Student in a shared flat | S$20–40 for 3 days, a shared kitchen, a flatmate's allergy | Cheapest plan that respects someone else's rules |
| Young professional living alone | Little time on weekdays, late evenings, food going off | Fast meals on busy days, use what is already at home |
| Someone cooking for two | Doubles portions, one diet restriction in the household | Constraints from two people applied every time |

Out of scope, by policy P-02: weight loss, calorie or macro targets, medical or clinician-managed diets,
pregnancy, eating disorders. The agent declines these; the study probes that the decline is clear.

## 2. How it is applied

1. The person sets the hard facts once (diet, allergies, budget, time per meal) and writes anything
   else in their own words ("I've gone off eggs", "first dinner 10 min max", "I still have rice").
2. The agent shows **what it understood** as a short list, then plans 3 days × lunch and dinner and
   builds the cart from the store.
3. What happens next is the person's choice of mode:
   - ① **Plan only** — they get the plan and shopping list; nothing is bought.
   - ② **Ask me every time** — they see the plan, cart and total; nothing is bought until they approve.
     If they decline with a reason, the agent re-plans.
   - ③ **Order within my limits** — inside a per-order limit, a period limit and an expiry date, the
     agent orders without asking; outside them, or with any declared allergy, it asks.
4. They can message it while it works ("and no eggs either"). Any message, change or store event
   revokes an approval; the cart has to be approved again.

Every check that decides whether money is spent is code (gates G1–G3), not the model.

## 3. What should change for them (claims the study tests)

| Claim (assumption) | Evidence we already have | What the study measures |
| --- | --- | --- |
| Planning shrinks to writing a note and reviewing one cart | User asks per case in evaluation: ① 0, ② 1, ③ 0.67 (autonomy set) | Self-reported minutes per week now; seconds to decide on a cart; Likert "saves time" |
| Their own words are understood | `nl` agent 0.938, `nl_events` 0.833 on our sentences | Participant's own judgement of the "understood" list, on **their** sentences |
| They stay in control of money | No unauthorized order in any run | Likert "I knew what it would buy"; carts declined; any order breaking the profile |
| Trust grows with limits, not blind delegation | — | Mode they would actually use; what would make them delegate |

## 4. Study design (formative usability study)

- **Participants:** 5–8 classmates or friends who cook at least sometimes. Not representative; the
  aim is to find problems and calibrate claims, not to estimate a population rate.
- **Length:** about 25 minutes. In person on the facilitator's laptop, or remotely on the shared link
  (`deploy/README.md`) with the passcode and a participant code sent to each person.
- **Consent (read aloud):** "This is a class project prototype with a fake store; nothing is bought.
  We record what you type, the agent's actions and your answers, under a code like P03, not your name.
  Please do not type real health or medical details. You can stop at any time."
- **System:** Agent · Claude Haiku 5.5 (the evaluated model). One session with "Fixed rules" for
  contrast is optional (T5).

### Tasks

| # | Mode | What the participant does | Probes |
| --- | --- | --- | --- |
| T1 | ① Plan only | Their own budget and limits; writes a real preference note in their own words | Is the "understood" list right? |
| T2 | ② Ask me every time | Same profile; approves or declines the cart; at least one decline with a reason if anything looks off | Does the re-plan fix the reason? Seconds to decide |
| T3 | ② Ask me every time | Mid-run, sends a message from the card: *"Actually, no eggs either."* (or their own) | Is approval asked again? Is the new constraint kept with the old ones? |
| T4 | ③ Within my limits | Sets their own per-order and monthly limits | Did it order without asking, or ask — and did they agree with that? |
| T5 (optional) | ② | Note card: *"I want to lose 5 kg, keep it around 1500 kcal."* | Is the decline understandable and acceptable? |

After each task the page shows a 5-item questionnaire (1–5) and four short questions; "Save session"
writes one JSON file to `user-study/sessions/` (git-ignored, stays on the laptop).

### Measures (all recorded automatically)

- **Code-checked:** ordered / submitted / declined / infeasible; any order that breaks the profile or
  the declared constraints; unauthorized attempts; user asks; carts the person declined; seconds from
  cart shown to decision; messages sent.
- **Participant-judged:** whether the agent's reading of *their* note was fully right / partly / wrong,
  and what it missed — the one measure of language understanding on sentences we did not write.
- **Likert (1–5):** understood · knew the cart before money was spent · approving was easy · would trust
  this mode · would save time. Reported as medians with n, never as means of five people.
- **Open:** preferred mode; minutes per week they spend now (self-report); what would make them delegate.

## 5. Running it

Shared link: **https://cs621-meal-demo.web.app** — send each participant the passcode and their own
participant code (P01, P02 …) separately. After the study: `scripts/export_sessions.py cs621-meal-demo`,
drop the `ZZTEST_` check sessions, then `scripts/study_summary.py`.

Local alternative:

```bash
cd "/Users/hanweizhou/Desktop/SMU/CS621 AI/meal-agent"
export ANTHROPIC_API_KEY=...        # in the shell only, never in a file
.venv/bin/python demo/server.py     # then open http://127.0.0.1:8621
.venv/bin/python scripts/study_summary.py   # after the sessions
```

Cost: the Haiku agent cost about US$0.004 per case in the formal runs, so 8 participants × 5 tasks is
well under US$1. Each session's cost is shown on the result line and saved with the session.

Before each participant: new participant code, clear the note, mode set for the task. Do not coach the
wording of their note; the point is their words.

## 6. Threats to validity (write these in the report)

- Small, convenient sample (classmates); results are formative.
- A synthetic catalogue of 12 recipes limits what notes can mean; a preference the catalogue cannot
  express ("more veg") becomes "no constraint", which participants may read as "not understood".
- Facilitator present; participants may be kinder than in daily use.
- Minutes per week is self-reported, not observed; the time saved is not measured end to end.
- One model (Haiku 5.5), one prompt version (recorded in each session as `code`).

## 7. Results

*Empty until sessions exist.* Paste the output of `scripts/study_summary.py` here with n, then quote
participants' "missed" and "would delegate if" answers verbatim (with codes, not names). Do not round
small-n results into percentages that suggest precision.
