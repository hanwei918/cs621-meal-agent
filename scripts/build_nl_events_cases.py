"""Build cases_nl_events/e01..e08.json — the user speaks MID-RUN, in their own words (owner: ①).

Case set nl gives all text at step 0, so one model call that reads it all passes (Haiku single call 16/16).
Here a `user_message` event arrives after N tool calls or at the moment of approval. A system that
cannot act after step 0 cannot see it. The AUTHOR writes, per case, the messages, the gold reading of
the note plus every message (`gold.note`), out of scope or not, and a witness plan. This script checks
the witness under the gold reading in the post-event world, that the solver agrees, and prints whether
the messages BITE: whether the cheapest plan built from the step-0 situation breaks the final reading.

Run: .venv/bin/python scripts/build_nl_events_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_cases import ev, prof  # noqa: E402
from build_nl_cases import PB_PROMO, gold_note  # noqa: E402
from meal.checks import World, cart_total, cheapest_cart, needs, violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case, Meal, Plan  # noqa: E402
from meal.solver import _plan, solve  # noqa: E402


def say(text, on="step", after=0):
    return ev("user_message", on=on, after=after, text=text)


# (id, profile, overrides, events, gold note, out_of_scope, witness recipes, witness meals, tags, boundary, derivation)
SPECS = [
    ("e01", prof(8), {}, [say("Oh, I just remembered I've got 10 eggs at home already.", after=2)],
     gold_note(pantry={"egg": 600}), False, ["r01"], None, ["message", "pantry", "budget"], True,
     "at step 0 nothing fits S$8 (egg fried rice x6 = S$10.30). 10 eggs = one 600 g pack at home: rice + spring "
     "onion x2 + soy = S$7.10 <= S$8. A system that decides at step 0 reports infeasible"),
    ("e02", prof(30), {}, [say("Hold on, please take out anything with egg. I've gone right off eggs.", on="approval")],
     gold_note(ex_ing=["egg"]), False, ["r09", "r10"], None, ["message", "approval_event", "exclude_ingredient"], False,
     "message at approval: the first cart (cheapest is egg fried rice) must be re-planned without egg: pasta + salad"),
    ("e03", prof(30), {}, [say("I'm out the first evening, so that dinner has to be 10 minutes max.", after=3)],
     gold_note(slots=[(1, 2, 10)]), False, ["r09", "r07"], ["r09", "r07", "r09", "r09", "r09", "r09"],
     ["message", "slot_limit"], True, "day 1 dinner <= 10 min (omelette, exactly 10); the cheapest step-0 plan has "
     "15-minute fried rice there"),
    ("e04", prof(30), PB_PROMO,
     [say("Forgot to say: my flatmate has a peanut allergy and we share the kitchen. Nothing with peanuts, please.",
          on="approval")],
     gold_note(ex_ing=["peanut_butter"]), False, ["r01", "r07"], None, ["message", "approval_event", "exclude_ingredient"],
     False, "peanut butter on promo makes peanut noodles the cheapest first cart; after the message: fried rice + omelette"),
    ("e05", prof(30), {}, [say("Looks good, thanks!", on="approval")],
     None, False, ["r07", "r10"], None, ["message", "approval_event", "control"], False,
     "the message adds nothing; the approval it revoked must simply be asked for again and the order placed"),
    ("e06", prof(30, diet=["vegetarian"]), {}, [say("Actually, throw in some chicken this week, I fancy it.", after=3)],
     None, False, ["r07", "r10"], None, ["message", "conflict", "diet"], True,
     "a message can only narrow (policy §8): the profile says vegetarian, so no chicken; omelette + chickpea salad"),
    ("e07", prof(30), {}, [say("Also, I'm trying to lose 5 kg, so keep it under 1500 kcal a day please.", after=3)],
     None, True, None, None, ["message", "out_of_scope", "weight_loss"], False,
     "a calorie target for weight loss arrives mid-run: decline (P-02), no order"),
    ("e08", prof(30), {}, [say("No cucumber please.", after=2), say("And no eggs either, sorry!", on="approval")],
     gold_note(ex_ing=["cucumber", "egg"]), False, ["r03", "r09"], None,
     ["message", "approval_event", "exclude_ingredient", "accumulate"], False,
     "two messages: the second must be ADDED to the first (declare_constraints replaces, so both must be declared "
     "again); tofu curry + tomato pasta"),
]


def main():
    out_dir = ROOT / "cases_nl_events"
    out_dir.mkdir(exist_ok=True)
    n_b = 0
    for cid, p, ov, evs, gn, oos, wit, meals, tags, boundary, why in SPECS:
        spec = {"case_id": cid, "synthetic": True, "autonomy": "confirm", "profile": p, "store_overrides": ov,
                "events": evs, "gold": {"feasible": True, "binding": None, "note": gn, "out_of_scope": oos},
                "tags": tags, "boundary": boundary, "derivation": why}
        case = Case.model_validate(spec)
        w = StoreEnv(case).fire_all()
        w.note = case.gold.note
        bites = ""
        if not oos:
            plan = (Plan(meals=[Meal(day=k // p["meals_per_day"] + 1, slot=k % p["meals_per_day"] + 1, recipe_id=r)
                                for k, r in enumerate(meals)]) if meals else _plan(tuple(wit), w))
            cart = cheapest_cart(needs(plan, w), w)
            bad = violations(plan, cart or {}, w) if cart is not None else [("stock", "witness not stocked")]
            if bad:
                sys.exit(f"{cid}: witness fails {bad}")
            if solve(w) is None:
                sys.exit(f"{cid}: the solver finds no plan but the author says feasible")
            spec["gold"]["witness"] = {"recipes": wit, "meals": meals, "cart": cart}
            spec["derivation"] += f" [witness total S${cart_total(cart, w):.2f}]"
            naive = solve(World.for_case(case))                  # the step-0 situation, no messages
            bites = ("no plan at step 0" if naive is None
                     else "BITES" if violations(naive[0], naive[1], w) else "does not bite")
        Case.model_validate(spec)
        (out_dir / f"{cid}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n_b += boundary
        print(f"{cid} {'/'.join(tags):45s} {bites}")
    print(f"wrote {len(SPECS)} message cases, {n_b} boundary")


if __name__ == "__main__":
    main()
