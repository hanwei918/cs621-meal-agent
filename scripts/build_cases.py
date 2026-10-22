"""Build cases/c01..c30.json from hand-written specs (owner: ①).

For each case the AUTHOR writes: the profile, store overrides, events, whether a valid plan exists,
the binding constraint if not, the recipes of a witness plan if so, and a one-line derivation.
This script only:
  - computes the witness cart (cheapest cover of the witness plan) and checks the witness passes every
    hard constraint in the post-event world;
  - for infeasible cases, checks the reference solver finds nothing AND names the same binding.
Any disagreement stops the build: fix the SPEC by re-reasoning and record why in cases/CHANGELOG.md;
never copy the solver's answer into the gold.

Run: .venv/bin/python scripts/build_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from meal.checks import cart_total, cheapest_cart, needs, violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case  # noqa: E402
from meal.solver import _plan, diagnose, solve  # noqa: E402

VEG_SAFE = ["egg", "gluten", "soy", "peanut"]


def prof(budget, minutes=30, diet=(), allergies=(), days=3, per_day=2, servings=1, pantry=None):
    return {"diet": list(diet), "allergies": list(allergies), "budget_sgd": budget, "days": days,
            "meals_per_day": per_day, "servings": servings, "max_cook_minutes": minutes, "pantry": pantry or {}}


def ev(kind, on="step", after=0, **kw):
    return {"on": on, "after_step": after, "kind": kind, **kw}


# (id, profile, overrides, events, feasible, binding, witness recipes, tags, boundary, derivation)
SPECS = [
    ("c01", prof(40, allergies=["peanut"]), {}, [], True, None, ["r01", "r07"], ["allergy"], False,
     "peanut allergy only excludes r04; egg fried rice + tomato omelette, 3 each, about S$16 << S$40"),
    ("c02", prof(25, diet=["vegetarian"], allergies=["egg"]), {},
     [ev("out_of_stock", after=3, sku="tofu_300g"), ev("price_change", after=5, sku="chickpeas_400g", price_sgd=4.50)],
     True, None, ["r04", "r09", "r10"], ["diet", "allergy", "stock_event", "price_event"], True,
     "vegetarian, no egg, tofu gone, chickpeas S$4.50: peanut noodles + tomato pasta + chickpea salad still fit S$25"),
    ("c03", prof(5), {}, [], False, "budget", None, ["infeasible", "budget"], True,
     "six meals for S$5: rice + one pack of eggs alone is S$6.00; every recipe needs >= S$5 of packs"),
    ("c04", prof(30, diet=["vegetarian"]), {}, [], True, None, ["r07", "r10"], ["diet"], False,
     "vegetarian allows omelette and chickpea salad; about S$14"),
    ("c05", prof(45, diet=["no_pork", "no_beef"], allergies=["shellfish"]), {}, [], True, None, ["r02", "r06"],
     ["diet", "allergy"], False, "no pork/beef, no shellfish: chicken stir-fry + salmon bowl, about S$40 <= S$45"),
    ("c06", prof(30, allergies=["gluten", "soy"]), {}, [], True, None, ["r07", "r10"], ["allergy"], False,
     "gluten + soy rule out soy-sauce, tofu, noodle and pasta recipes; omelette + chickpea salad remain"),
    ("c07", prof(25, minutes=10), {}, [], True, None, ["r07", "r10"], ["time"], True,
     "10-minute limit: only omelette (10) and chickpea salad (10) qualify, exactly at the limit"),
    ("c08", prof(40, minutes=9), {}, [], False, "time", None, ["infeasible", "time"], True,
     "fastest recipes take 10 minutes; a 9-minute limit leaves nothing"),
    ("c09", prof(30, diet=["vegetarian"], allergies=["egg", "gluten", "peanut"]), {}, [], True, None, ["r03", "r10"],
     ["diet", "allergy"], False, "tofu curry (soy is fine) + chickpea salad"),
    ("c10", prof(20, diet=["vegetarian"], allergies=VEG_SAFE), {}, [], True, None, ["r10"], ["diet", "allergy"], True,
     "only chickpea salad survives; x6 = chickpeas 3 + cucumber 2 + tomato 2 packs = S$13.00 <= S$20"),
    ("c11", prof(12, diet=["vegetarian"], allergies=VEG_SAFE), {}, [], False, "budget", None,
     ["infeasible", "budget", "diet"], True, "only chickpea salad survives and x6 costs S$13.00 > S$12"),
    ("c12", prof(13, diet=["vegetarian"], allergies=VEG_SAFE), {}, [], True, None, ["r10"], ["budget", "diet"], True,
     "same as c11 with budget S$13.00: the S$13.00 plan is exactly within budget"),
    ("c13", prof(30, diet=["vegetarian"], allergies=VEG_SAFE), {"chickpeas_400g": {"stock": 0}}, [], False, "stock",
     None, ["infeasible", "stock"], True, "chickpea salad is the only allowed recipe and chickpeas are out of stock"),
    ("c14", prof(8, pantry={"rice": 1000}), {}, [], True, None, ["r01"], ["pantry", "budget"], True,
     "rice already at home: egg fried rice x6 needs eggs 3.20 + spring onion 1.80 + soy 2.50 = S$7.50 <= S$8"),
    ("c15", prof(45, servings=2), {}, [], True, None, ["r01", "r07"], ["servings"], False,
     "two servings per meal doubles the grams; fried rice + omelette still about S$23"),
    ("c16", prof(15, servings=2), {}, [], False, "budget", None, ["infeasible", "budget", "servings"], True,
     "two servings: the cheapest option (fried rice x6) is about S$17.20 > S$15"),
    ("c17", prof(40, diet=["no_beef"]), {"chicken_breast_1kg": {"stock": 0}},
     [ev("out_of_stock", on="approval", sku="chicken_breast_500g")], True, None, ["r01", "r07"],
     ["stock_event", "approval_event"], False,
     "if the first cart uses chicken, both chicken SKUs are gone at approval; egg dishes still fit"),
    ("c18", prof(20, diet=["vegetarian"]), {}, [ev("price_change", on="approval", sku="egg_10pk", price_sgd=9.00)],
     True, None, ["r09", "r10"], ["price_event", "approval_event"], False,
     "eggs jump to S$9.00 at approval; pasta + chickpea salad avoid eggs and stay under S$20"),
    ("c19", prof(35), {}, [ev("preference", on="approval", add_diet="vegetarian")], True, None, ["r07", "r10"],
     ["preference_event", "approval_event"], False, "user turns vegetarian at approval; omelette + salad fit"),
    ("c20", prof(14), {}, [ev("preference", on="approval", add_diet="vegetarian"),
                           ev("preference", on="approval", add_allergy="egg"),
                           ev("preference", on="approval", add_allergy="gluten"),
                           ev("preference", on="approval", add_allergy="soy")],
     True, None, ["r10"], ["preference_event", "approval_event", "budget"], True,
     "after the update only chickpea salad remains: S$13.00 <= S$14"),
    ("c21", prof(12), {}, [ev("preference", on="approval", add_diet="vegetarian"),
                           ev("preference", on="approval", add_allergy="egg"),
                           ev("preference", on="approval", add_allergy="gluten"),
                           ev("preference", on="approval", add_allergy="soy")],
     False, "budget", None, ["preference_event", "approval_event", "infeasible", "budget"], True,
     "feasible before approval (fried rice ~S$10.30), but after the update only chickpea salad remains at S$13.00 > S$12"),
    ("c22", prof(30), {}, [ev("out_of_stock", after=2, sku="rice_1kg")], True, None, ["r07", "r10"],
     ["stock_event"], False, "rice disappears early; no rice dishes, omelette + salad"),
    ("c23", prof(30, diet=["vegetarian"], allergies=["egg", "gluten"]), {"tomato_500g": {"stock": 1}}, [], True, None,
     ["r03", "r10"], ["stock", "allergy"], False, "one pack of tomatoes: curry x3 + salad x3 needs 300 g <= 500 g"),
    ("c24", prof(25), {"chicken_breast_500g": {"stock": 1}}, [], True, None, ["r02"], ["stock", "multi_sku"], False,
     "chicken stir-fry x6 needs 900 g chicken: the 1 kg pack covers it; about S$21.60"),
    ("c25", prof(20, days=2, per_day=3), {}, [], True, None, ["r07", "r10"], ["shape"], False,
     "2 days x 3 meals is still six slots; omelette + salad about S$14"),
    ("c26", prof(6, per_day=1), {}, [], False, "budget", None, ["infeasible", "budget", "shape"], True,
     "three meals for S$6: the cheapest (omelette x3) is S$6.70"),
    ("c27", prof(25, minutes=45, diet=["vegetarian"]), {}, [], True, None, ["r12", "r10"], ["time"], False,
     "45-minute limit admits mushroom risotto; risotto + salad"),
    ("c28", prof(30), {"salmon_300g": {"stock": 0}, "prawns_300g": {"stock": 0}}, [], True, None, ["r01", "r09"],
     ["stock"], False, "seafood out of stock; fried rice + pasta"),
    ("c29", prof(25, diet=["no_pork"]), {}, [ev("out_of_stock", on="approval", sku="egg_10pk")], True, None,
     ["r09", "r10"], ["stock_event", "approval_event"], False, "eggs sell out at approval; pasta + salad need no egg"),
    ("c30", prof(40, allergies=["peanut"]), {}, [ev("price_change", on="approval", sku="rice_1kg", price_sgd=30.00)],
     True, None, ["r07", "r09"], ["price_event", "approval_event"], True,
     "rice jumps to S$30 at approval; omelette + pasta need no rice"),
]


def main():
    out_dir = ROOT / "cases"
    n_boundary = 0
    for cid, p, ov, evs, feasible, binding, wit, tags, boundary, why in SPECS:
        spec = {"case_id": cid, "synthetic": True, "profile": p, "store_overrides": ov, "events": evs,
                "gold": {"feasible": feasible, "binding": binding}, "tags": tags, "boundary": boundary,
                "derivation": why}
        case = Case.model_validate(spec)
        env = StoreEnv(case)
        w = env.fire_all()                                   # the post-event world the gold refers to
        if feasible:
            plan = _plan(tuple(wit), w)
            cart = cheapest_cart(needs(plan, w), w)
            bad = violations(plan, cart or {}, w) if cart is not None else [("stock", "witness not stocked")]
            if bad:
                sys.exit(f"{cid}: witness {wit} fails {bad} — re-reason the spec")
            spec["gold"]["witness"] = {"recipes": wit, "cart": cart}
            spec["derivation"] += f" [witness total S${cart_total(cart, w):.2f}]"
        else:
            if solve(w) is not None:
                sys.exit(f"{cid}: marked infeasible but the solver found a plan — re-reason the spec")
            if diagnose(w) != binding:
                sys.exit(f"{cid}: binding {binding} but the solver diagnoses {diagnose(w)} — re-reason the spec")
        Case.model_validate(spec)
        (out_dir / f"{cid}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n_boundary += boundary
    print(f"wrote {len(SPECS)} cases, {n_boundary} boundary ({n_boundary / len(SPECS):.0%})")


if __name__ == "__main__":
    main()
