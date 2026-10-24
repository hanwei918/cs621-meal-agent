"""Build cases_stress/ — where the agent's ability ends (assignment: "where the boundaries are").

Three load dimensions, each varied with everything else fixed, plus a combined level:
  events  k = 0, 1, 2, 3, 4, 5 store events mid-run (stock-outs and price rises; with k ≥ 2 the last one
          strikes at the approval moment)                                            3 cases per level
  days    d = 3, 5, 7 (one event)                                                    3 cases per level
  notes   n = 1, 2, 3, 4 constraints in the user's own words                        3 cases per level
  mixed   k = 3, d = 7, n = 3                                                        3 cases
  mixed+  k = 5, d = 7, n = 4  (added 24 Oct, stress v2, after the output-limit fix)   3 cases

Gold by construction (the policy, not a run): every case has the same witness — tomato omelette and
chickpea salad alternating — and events only ever hit items that witness does not use, every note
excludes something the witness does not contain. So a valid plan always exists; the budget is the
witness cost × 1.25. This script checks the witness against every rule after all events under the gold
reading of the notes, and that the solver agrees. Events are chosen to break the CHEAP plans an agent is
likely to pick first (rice, noodles, pasta, soy sauce, tofu, peanut butter …), so re-planning is needed.

Run: .venv/bin/python scripts/build_stress_cases.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_cases import ev, prof  # noqa: E402
from build_nl_cases import gold_note  # noqa: E402
from meal.checks import World, cart_total, cheapest_cart, needs, violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case  # noqa: E402
from meal.solver import _plan, solve  # noqa: E402

WITNESS = ["r07", "r10"]
HIT = ["rice_1kg", "noodles_400g", "pasta_500g", "soy_sauce_300ml", "tofu_300g", "peanut_butter_340g",
       "chicken_breast_500g", "broccoli_300g", "garlic_100g", "coconut_milk_400ml"]
NOTES = [  # (the user's words, gold reading as gold_note kwargs)
    ("Nothing with peanuts, my flatmate is allergic.", {"ex_ing": ["peanut_butter"]}),
    ("I don't eat pork.", {"ex_ing": ["pork_mince"]}),
    ("No beef please.", {"ex_ing": ["beef_slices"]}),
    ("Cannot take spicy one lah.", {"ex_ing": ["curry_paste"]}),
    ("I'm off mushrooms at the moment.", {"ex_ing": ["mushrooms"]}),
    ("No prawns, they don't agree with me.", {"ex_ing": ["prawns"]}),
    ("The first dinner has to be 10 minutes max.", {"slots": [(1, 2, 10)]}),
]


def events(rng: random.Random, k: int) -> list[dict]:
    out = []
    for j, sku in enumerate(rng.sample(HIT, k)):
        on_approval = k >= 2 and j == k - 1
        kw = dict(on="approval") if on_approval else dict(after=3 * (j + 1))
        if rng.random() < 0.5:
            out.append(ev("out_of_stock", sku=sku, **kw))
        else:
            out.append(ev("price_change", sku=sku, price_sgd=None, **kw))      # price filled in below
    return out


def merge_notes(picked):
    ex_ing, slots = [], []
    for _, g in picked:
        ex_ing += g.get("ex_ing", [])
        slots += g.get("slots", [])
    return " ".join(t for t, _ in picked), gold_note(ex_ing=ex_ing, slots=slots)


def spec_for(cid, dim, level, days, k, n, seed):
    rng = random.Random(f"{cid}-{seed}")
    evs = events(rng, k)
    store = {s["sku"]: s for s in json.loads((ROOT / "data" / "store.json").read_text())}
    for e in evs:
        if e["kind"] == "price_change":
            e["price_sgd"] = round(store[e["sku"]]["price_sgd"] * 2.5, 2)
    text, gn = merge_notes(rng.sample(NOTES, n)) if n else (None, None)
    base = prof(1000, days=days) | ({"note": text} if text else {})
    probe = Case.model_validate({"case_id": cid, "profile": base, "gold": {"feasible": True}, "tags": ["x"],
                                 "derivation": "budget probe for the witness cost"})
    w0 = World.for_case(probe)
    cost = cart_total(cheapest_cart(needs(_plan(tuple(WITNESS), w0), w0), w0), w0)
    budget = math.ceil(cost * 1.25)
    return {"case_id": cid, "synthetic": True, "autonomy": "confirm", "profile": dict(base, budget_sgd=budget),
            "events": evs, "gold": {"feasible": True, "note": gn},
            "tags": ["stress", f"dim:{dim}", f"level:{level}"], "boundary": False,
            "derivation": f"stress {dim}={level}: {k} event(s) on items the witness does not use, {days} days, "
                          f"{n} note constraint(s); witness omelette + chickpea salad, budget = witness × 1.25"}


def main():
    out_dir = ROOT / "cases_stress"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("s*.json"):
        old.unlink()
    specs = []
    for k in range(6):
        specs += [spec_for(f"se{k}{'abc'[i]}", "events", k, 3, k, 0, i) for i in range(3)]
    for d in (3, 5, 7):
        specs += [spec_for(f"sd{d}{'abc'[i]}", "days", d, d, 1, 0, i) for i in range(3)]
    for n in (1, 2, 3, 4):
        specs += [spec_for(f"sn{n}{'abc'[i]}", "notes", n, 3, 0, n, i) for i in range(3)]
    specs += [spec_for(f"sx{'abc'[i]}", "mixed", "k3d7n3", 7, 3, 3, i) for i in range(3)]
    specs += [spec_for(f"sy{'abc'[i]}", "mixed", "k5d7n4", 7, 5, 4, i) for i in range(3)]
    for spec in specs:
        case = Case.model_validate(spec)
        env = StoreEnv(case)
        w = env.fire_all()
        w.note = case.gold.note
        plan = _plan(tuple(WITNESS), w)
        cart = cheapest_cart(needs(plan, w), w)
        bad = violations(plan, cart or {}, w) if cart is not None else [("stock", "witness not stocked")]
        if bad:
            sys.exit(f"{spec['case_id']}: witness fails {bad}")
        if solve(w) is None:
            sys.exit(f"{spec['case_id']}: the solver finds no plan")
        spec["gold"]["witness"] = {"recipes": WITNESS, "cart": cart}
        spec["derivation"] += f" [witness S${cart_total(cart, w):.2f} of S${spec['profile']['budget_sgd']}]"
        Case.model_validate(spec)
        (out_dir / f"{spec['case_id']}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")
    print(f"wrote {len(specs)} stress cases")


if __name__ == "__main__":
    main()
