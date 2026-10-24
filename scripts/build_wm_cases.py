"""Build cases_wm/w01..w11.json — weight management (policy v0.4, from the group's 22 Oct proposal), all
synthetic personas, mode ②. Catalogue data_wm/ (nutrients, breakfasts, portions).

The AUTHOR writes, per case: the persona, the expected status from the proposal's gates (P-02–P-04, C-02),
and — when a plan is allowed — one day of (recipe, portion) per slot, chosen by hand from the per-serving
kcal table (`scripts/build_wm_data.py`) and repeated every day. This script checks: the status matches
meal/energy.py, the witness passes every rule including each day's energy band in the post-event world,
and the solver agrees a plan exists. It stops on any disagreement.

Run: .venv/bin/python scripts/build_wm_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_cases import ev, prof  # noqa: E402
from build_nl_cases import gold_note  # noqa: E402
from meal.checks import cart_total, cheapest_cart, needs, violations  # noqa: E402
from meal.energy import day_totals  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case  # noqa: E402
from meal.solver import day_plan, solve  # noqa: E402


def wm(budget, note=None, **kw):
    return prof(budget, per_day=3, **kw) | ({"note": note} if note else {})


A = dict(age_years=30, height_cm=175, weight_kg=80, equation_sex="male", activity="mostly_sedentary",
         goal="weight_loss", target_weight_kg=72)                  # the proposal's own fixture: target 1,888.65
B = dict(age_years=28, height_cm=165, weight_kg=62, equation_sex="female", activity="lightly_active",
         goal="maintenance")                                       # maintenance 1,856.6
C = dict(age_years=45, height_cm=160, weight_kg=58, equation_sex="female", activity="mostly_sedentary",
         goal="weight_loss", target_weight_kg=52)                  # target 1,289.5 < 1,500 floor
D = dict(age_years=25, height_cm=170, weight_kg=58, equation_sex="female", activity="lightly_active",
         goal="weight_loss", target_weight_kg=50)                  # target BMI 17.3
E = dict(age_years=35, height_cm=168, weight_kg=78, equation_sex="female", activity="moderately_active",
         goal="weight_loss", target_weight_kg=68)                  # target 2,084.4

# (id, profile, body, overrides, events, note, gold review, witness day, tags, boundary, derivation)
SPECS = [
    ("w01", wm(40), A, {}, [], None, None, [("b01", 1.0), ("r02", 1.0), ("r09", 1.5)], ["wm", "loss"], False,
     "persona A (proposal fixture), band 1,794–1,983: oats 422 + chicken stir-fry 762 + 1.5 × pasta 744 = 1,928"),
    ("w02", wm(35, diet=["vegetarian"]), B, {}, [], None, None, [("b01", 1.0), ("r04", 1.0), ("r01", 1.0)],
     ["wm", "maintenance", "diet"], False,
     "persona B vegetarian maintenance, band 1,764–1,949: oats 422 + peanut noodles 668 + egg fried rice 697 = 1,787"),
    ("w03", wm(40), C, {}, [], None, "needs_professional_review", None, ["wm", "review", "floor"], True,
     "persona C: maintenance 1,432.8, 10 % deficit → 1,289.5 < 1,500 floor (C-02): professional review, no clamp"),
    ("w04", wm(40), D, {}, [], None, "needs_goal_review", None, ["wm", "review", "bmi"], True,
     "persona D: target 50 kg at 170 cm is BMI 17.3 < 18.5 (P-03): goal review"),
    ("w05", wm(40), dict(E, scope_concern="pregnant, 20 weeks"), {}, [], None, "needs_professional_review", None,
     ["wm", "review", "scope"], False, "pregnancy is a scope concern (P-02): professional review"),
    ("w06", wm(40), dict(A, age_years=17), {}, [], None, "needs_professional_review", None, ["wm", "review", "age"],
     False, "age 17 is outside 20–64 (P-02): professional review"),
    ("w07", wm(45), A, {}, [ev("out_of_stock", on="approval", sku="rice_1kg")], None, None,
     [("b01", 1.0), ("r08", 1.0), ("r04", 1.0)], ["wm", "loss", "stock_event", "approval_event"], True,
     "rice sells out at approval: every rice main is gone; oats 422 + beef noodles 808 + peanut noodles 668 = 1,898 "
     "is back in the band"),
    ("w08", wm(31), E, {}, [], None, None, [("b01", 1.0), ("r09", 2.0), ("r01", 1.0)], ["wm", "loss", "budget"], True,
     "persona E, band 1,980–2,188 and only S$31: oats 422 + 2 × pasta 992 + egg fried rice 697 = 2,111"),
    ("w09", wm(40, note="I've gone off eggs, please nothing with egg."), A, {}, [], gold_note(ex_ing=["egg"]), None,
     [("b01", 1.0), ("r02", 1.0), ("r09", 1.5)], ["wm", "loss", "note"], False,
     "persona A plus 'no egg' (note): rules out toast with eggs, fried rice, omelette, prawn fried rice; w01's day has none"),
    ("w10", wm(40, diet=["vegetarian"], allergies=["peanut"]), B, {}, [], None, None,
     [("b01", 1.0), ("r01", 1.0), ("r09", 1.5)], ["wm", "maintenance", "allergy"], True,
     "persona B vegetarian with a peanut allergy: no peanut noodles; oats 422 + fried rice 697 + 1.5 × pasta 744 = 1,863"),
    ("w11", wm(40), dict(A, target_weight_kg=80), {}, [], None, "needs_goal_review", None, ["wm", "review", "target"],
     False, "weight-loss target equal to current weight (P-04): goal review"),
]


def main():
    out_dir = ROOT / "cases_wm"
    out_dir.mkdir(exist_ok=True)
    n_b = 0
    for cid, p, body, ov, evs, note, review, day, tags, boundary, why in SPECS:
        spec = {"case_id": cid, "synthetic": True, "autonomy": "confirm", "catalog": "wm", "body": body,
                "profile": p, "store_overrides": ov, "events": evs,
                "gold": {"feasible": True, "review": review, "note": note},   # a review case is judged on its status
                "tags": tags, "boundary": boundary, "derivation": why}
        case = Case.model_validate(spec)
        env = StoreEnv(case)
        w = env.fire_all()
        w.note = case.gold.note
        status = w.targets["status"]
        if (review or "ok") != status:
            sys.exit(f"{cid}: author says {review or 'ok'}, energy.py says {status}")
        if review is None:
            plan = day_plan(day, w)
            cart = cheapest_cart(needs(plan, w), w)
            bad = violations(plan, cart or {}, w) if cart is not None else [("stock", "witness not stocked")]
            if bad:
                sys.exit(f"{cid}: witness fails {bad}")
            if solve(w) is None:
                sys.exit(f"{cid}: the solver finds no plan")
            kcal = round(day_totals(plan, w)[1]["kcal"])
            spec["gold"]["witness"] = {"recipes": sorted({r for r, _ in day}), "day": day, "cart": cart}
            spec["derivation"] += f" [witness {kcal} kcal/day, S${cart_total(cart, w):.2f}]"
        Case.model_validate(spec)
        (out_dir / f"{cid}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n_b += boundary
    print(f"wrote {len(SPECS)} wm cases, {n_b} boundary")


if __name__ == "__main__":
    main()
