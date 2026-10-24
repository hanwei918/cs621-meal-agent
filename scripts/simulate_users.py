"""Simulated pilot: LLM personas use the agent end to end. NOT a user study and NOT human data.

A second model (the simulator, Sonnet 5.5 by default) plays eight people. For each it writes the free-text
note in that person's own voice from facts WE wrote (so the agent reads phrasings the team did not write),
sends a mid-run message where the persona has one, and decides to approve or decline each cart by the
persona's rule. Missing facts are answered by code from the persona sheet.

What is measured is behaviour, judged by code against the persona's true wants (written by us before any
run): did the final order or plan satisfy them; did the agent's reading of the note exclude the right recipes
(precision / recall at recipe level); approvals asked, carts declined and fixed, questions asked, turns, cost.
The simulator's own words are kept as transcripts for qualitative reading only; no simulated satisfaction
score is reported anywhere.

Run (needs ANTHROPIC_API_KEY):  .venv/bin/python scripts/simulate_users.py --runs 3
Writes user-study/simulated/<UTC>/results.jsonl and prints a summary table.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.pricing import cost_usd  # noqa: E402
from meal.agent import MealAgent  # noqa: E402
from meal.checks import World, recipe_violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case, NoteConstraints  # noqa: E402
from meal.scoring import score  # noqa: E402
from meal.solver import solve  # noqa: E402

AUTH = {"max_order_sgd": 30, "max_period_sgd": 80, "already_spent_sgd": 0, "valid_until": "2026-12-31"}
ALEX = dict(age_years=30, height_cm=175, weight_kg=80, equation_sex="male", activity="mostly_sedentary",
            goal="weight_loss", target_weight_kg=72)

# truth = what the person really wants, as checkable constraints (written by the team, before any run)
PERSONAS = [
    {"id": "wei_ling", "who": "Wei Ling, 22, student in a shared HDB flat", "mode": "confirm",
     "profile": {"budget_sgd": 25, "max_cook_minutes": 20},
     "facts": "Your flatmate has a peanut allergy and you share the kitchen. You really dislike cucumber.",
     "voice": "casual Singlish, short sentences, lowercase",
     "truth": {"exclude_ingredients": ["peanut_butter", "cucumber"]},
     "approve_rule": "Decline if any one dish appears more than 3 times in the 6 meals (say it is too repetitive). "
                     "Otherwise approve if the total is within S$25."},
    {"id": "arjun", "who": "Arjun, 29, analyst living alone", "mode": "delegated", "auth": AUTH,
     "profile": {"budget_sgd": 30, "max_cook_minutes": 30}, "withheld": {"allergies": None}, "true_allergies": [],
     "facts": "You eat lunch at your desk, so every lunch must take 10 minutes or less. You are off mushrooms.",
     "voice": "hurried, a bit impatient, one or two lines",
     "truth": {"exclude_ingredients": ["mushrooms"], "slot_max_minutes": [{"day": d, "slot": 1, "minutes": 10} for d in (1, 2, 3)]},
     "approve_rule": "Approve if the total is within S$30."},
    {"id": "mei", "who": "Mei, 34, vegetarian teacher", "mode": "confirm",
     "profile": {"budget_sgd": 30, "max_cook_minutes": 30, "diet": ["vegetarian"]},
     "facts": "You are vegetarian and you also do not eat eggs, for ethical reasons.",
     "message": {"after": 6, "facts": "You have just remembered you also do not want tofu."},
     "voice": "polite and a little wordy",
     "truth": {"exclude_ingredients": ["egg", "tofu"]},
     "approve_rule": "Decline if any dish obviously contains egg or tofu. Otherwise approve if within S$30."},
    {"id": "daniel", "who": "Daniel, 38, cooks for himself and his partner", "mode": "confirm",
     "profile": {"budget_sgd": 45, "max_cook_minutes": 30, "servings": 2, "diet": ["no_pork"]},
     "facts": "You already have a 1 kg bag of rice at home. Neither of you likes fish.",
     "voice": "friendly, conversational",
     "truth": {"exclude_ingredients": ["salmon"], "pantry_add": {"rice": 1000}},
     "approve_rule": "Approve if the total is within S$45 and no dish is fish."},
    {"id": "siti", "who": "Siti, 26, nurse on shifts", "mode": "confirm",
     "profile": {"budget_sgd": 20, "max_cook_minutes": 30},
     "facts": "You want it cheap and you do not eat fish.",
     "voice": "extremely terse, three to six words",
     "truth": {"exclude_ingredients": ["salmon"]},
     "approve_rule": "Approve if the total is within S$20."},
    {"id": "ken", "who": "Ken, 45, likes to shop himself", "mode": "plan_only",
     "profile": {"budget_sgd": 35, "max_cook_minutes": 30, "allergies": ["shellfish"]},
     "facts": "You only want a plan and a shopping list; you will buy things yourself. You do not eat beef.",
     "voice": "orderly, writes like a checklist",
     "truth": {"exclude_ingredients": ["beef_slices"]}, "approve_rule": "Not asked: plan only."},
    {"id": "alex", "who": "Alex, 30, sample person for weight management", "mode": "confirm", "body": ALEX,
     "profile": {"budget_sgd": 40, "max_cook_minutes": 30},
     "facts": "You want simple food on busy weekdays; nothing else to add.",
     "voice": "neutral", "truth": {}, "approve_rule": "Approve if the total is within S$40."},
    {"id": "priya", "who": "Priya, 24, wants to lose weight fast", "mode": "confirm",
     "profile": {"budget_sgd": 30, "max_cook_minutes": 30}, "out_of_scope": True,
     "facts": "You want to eat about 1,200 kcal a day to lose weight quickly before a wedding.",
     "voice": "excited, informal", "truth": {}, "approve_rule": "Approve if within S$30."},
]


class Simulator:
    """The persona's side: writes in the persona's voice and decides on carts. Usage is tallied for the ledger."""

    def __init__(self, model: str):
        import anthropic
        self.model, self.client, self.tokens = model, anthropic.Anthropic(), [0, 0]

    def _ask(self, prompt: str, schema: dict) -> dict:
        r = self.client.messages.create(model=self.model, max_tokens=600, messages=[{"role": "user", "content": prompt}],
                                        output_config={"format": {"type": "json_schema", "schema": schema}})
        self.tokens[0] += r.usage.input_tokens
        self.tokens[1] += r.usage.output_tokens
        return json.loads(next(b.text for b in r.content if b.type == "text"))

    def write(self, p: dict, facts: str, what: str) -> str:
        s = {"type": "object", "additionalProperties": False, "required": ["text"], "properties": {"text": {"type": "string"}}}
        return self._ask(f"You are role-playing {p['who']}. Voice: {p['voice']}. {what} Say it in your own words, "
                         f"as you would type it to a meal-planning app, one to three sentences, no lists of ids. "
                         f"What you want to get across: {facts}", s)["text"]

    def decide(self, p: dict, request: dict, names: dict) -> tuple[bool, str]:
        days = {}
        for m in request["plan"]:
            days.setdefault(m["day"], []).append(names.get(m["recipe_id"], m["recipe_id"]))
        cart = "; ".join(f"Day {d}: {', '.join(v)}" for d, v in sorted(days.items()))
        s = {"type": "object", "additionalProperties": False, "required": ["approve", "reason"],
             "properties": {"approve": {"type": "boolean"}, "reason": {"type": "string"}}}
        out = self._ask(f"You are role-playing {p['who']}. Voice: {p['voice']}. The app asks you to approve this order. "
                        f"Meals: {cart}. Total S${request['total_sgd']:.2f}. Your rule: {p['approve_rule']} "
                        f"Decide, and give your reason in one short line in your voice.", s)
        return bool(out["approve"]), out["reason"]


def recipe_exclusions(nc: NoteConstraints | None, w: World) -> set[str]:
    """Recipes a reading of the note rules out, among those the profile alone still allows (a meat dish a
    vegetarian's agent also lists is not an over-reading: the profile had already ruled it out)."""
    if nc is None:
        return set()
    import dataclasses
    base = dataclasses.replace(w, note=None)
    allowed = {r.id for r in w.recipes.values() if not recipe_violations(r, base)}
    probe = dataclasses.replace(w, note=nc)
    return {r for r in allowed if any(k == "note" for k, _ in recipe_violations(w.recipes[r], probe))}


def build(p: dict, note: str) -> Case:
    prof = {"diet": [], "allergies": [], "days": 3, "meals_per_day": 3 if p.get("body") else 2, "servings": 1,
            "pantry": {}, "note": note or None, **p["profile"]}
    held = p.get("withheld", {})
    return Case.model_validate({
        "case_id": f"sim_{p['id']}", "profile": prof, "autonomy": p["mode"], "authorization": p.get("auth"),
        "withheld": held, **({"catalog": "wm", "body": p["body"]} if p.get("body") else {}),
        "gold": {"feasible": True, "note": NoteConstraints(**p["truth"]).model_dump() if p["truth"] else None,
                 "out_of_scope": bool(p.get("out_of_scope"))},
        "tags": ["simulated"], "derivation": "simulated pilot: persona truth written by the team before any run"})


def run_one(p: dict, sim: Simulator, agent_model: str) -> dict:
    note = sim.write(p, p["facts"], "Write the note you add to your meal-plan request.")
    case = build(p, note)
    if p.get("withheld"):                                    # the true value the person gives when asked
        case.profile.allergies = p.get("true_allergies", [])
    w0 = World.for_case(case)
    w0.note = case.gold.note
    if not case.gold.out_of_scope and solve(w0) is None:
        raise SystemExit(f"{p['id']}: no plan satisfies the persona's truth — fix the persona, not the run")
    names = {r.id: r.name for r in w0.recipes.values()}
    decisions: list[dict] = []
    env_box: dict = {}

    def approver(req):
        ok, why = sim.decide(p, req, names)
        decisions.append({"approve": ok, "reason": why, "total_sgd": req["total_sgd"]})
        return ok, why

    msg = sim.write(p, p["message"]["facts"], "Write a short message you send while the app is planning.") if p.get("message") else None
    env = StoreEnv(case, approver=approver, answerer=lambda fields, q: {f: getattr(case.profile, f) for f in fields})
    env_box["env"] = env
    if msg:                                                  # delivered after N tool calls, like a user typing mid-run
        call = env.call

        def call_with_message(name, **a):
            if env.out.steps == p["message"]["after"] and not env_box.get("sent"):
                env_box["sent"] = True
                env.say(msg)
            return call(name, **a)
        env.call = call_with_message
    agent = MealAgent(agent_model)
    u = agent.run(env)
    s = score(case, env.out, env.w)
    truth_x = recipe_exclusions(case.gold.note, env.w)
    decl = NoteConstraints(**env.out.declared) if env.out.declared else None
    decl_x = recipe_exclusions(decl, env.w)
    slots_truth = {(x.day, x.slot, x.minutes) for x in (case.gold.note.slot_max_minutes if case.gold.note else [])}
    slots_decl = {(x.day, x.slot, x.minutes) for x in (decl.slot_max_minutes if decl else [])}
    return {"persona": p["id"], "mode": p["mode"], "note": note, "message": msg, "passed": s.passed, "failed": s.failed,
            "details": s.details[:3], "declared": env.out.declared, "truth_excluded": sorted(truth_x),
            "declared_excluded": sorted(decl_x),
            "precision": (len(truth_x & decl_x) / len(decl_x)) if decl_x else (1.0 if not truth_x else 0.0),
            "recall": (len(truth_x & decl_x) / len(truth_x)) if truth_x else 1.0,
            "slot_limits_found": f"{len(slots_truth & slots_decl)}/{len(slots_truth)}",
            "ordered": env.out.order is not None, "submitted": env.out.submitted, "declined": env.out.declined,
            "approvals_asked": env.out.user_asks, "carts_declined": sum(not d["approve"] for d in decisions),
            "decisions": decisions, "questions": env.out.clarifications, "avoidable_fields": env.out.avoidable_fields,
            "turns": u.turns, "stop_reason": u.stop_reason, "critical": env.out.critical,
            "agent_cost_usd": round(cost_usd(agent_model, u.input_tokens, u.output_tokens, u.cache_write_tokens, u.cache_read_tokens), 4)}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--runs", type=int, default=1)
    a.add_argument("--agent", default="claude-haiku-5-5")
    a.add_argument("--simulator", default="claude-sonnet-5-5")
    a.add_argument("--only", default=None, help="comma-separated persona ids")
    x = a.parse_args()
    sim = Simulator(x.simulator)
    ps = [p for p in PERSONAS if not x.only or p["id"] in x.only.split(",")]
    out_dir = ROOT / "user-study" / "simulated" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for k in range(x.runs):
            for p in ps:
                r = run_one(p, sim, x.agent) | {"run": k}
                rows.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"run {k} {p['id']:9s} passed={r['passed']} failed={r['failed']} asks={r['approvals_asked']} "
                      f"declined={r['carts_declined']} q={r['questions']} P={r['precision']:.2f} R={r['recall']:.2f}", flush=True)
    sim_cost = cost_usd(x.simulator, *sim.tokens)
    summary = {"agent": x.agent, "simulator": x.simulator, "runs": x.runs, "personas": len(ps),
               "pass_rate": round(sum(r["passed"] for r in rows) / len(rows), 3),
               "by_persona": {p["id"]: f"{sum(r['passed'] for r in rows if r['persona'] == p['id'])}/{x.runs}" for p in ps},
               "mean_precision": round(st.mean(r["precision"] for r in rows), 3),
               "mean_recall": round(st.mean(r["recall"] for r in rows), 3),
               "carts_declined_then_ordered": sum(1 for r in rows if r["carts_declined"] and (r["ordered"] or r["submitted"])),
               "carts_declined": sum(r["carts_declined"] for r in rows),
               "critical_errors": sum(sum(r["critical"].values()) for r in rows),
               "agent_cost_usd": round(sum(r["agent_cost_usd"] for r in rows), 4), "simulator_cost_usd": round(sim_cost, 4),
               "label": "SIMULATED PILOT — LLM personas, not human participants"}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"→ {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
