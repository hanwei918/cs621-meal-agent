"""Energy targets for case set `wm` (policy v0.4, from the group's 22 Oct proposal §3–§4). Pure code: the
model never computes or overrides these numbers.

Order of checks (first that applies wins):
  P-02  age outside 20–64, or a scope concern (pregnancy, eating disorder, clinician-managed diet)
        → needs_professional_review
  P-03  current BMI or target-weight BMI below 18.5                    → needs_goal_review
  P-04  weight-loss target at or above current weight                  → needs_goal_review
  C-01  REE (Mifflin et al. 1990) × activity factor = estimated maintenance
  C-02  weight loss: deficit = min(10% of maintenance, 500); target below 1,500 kcal/day
        → needs_professional_review (never clamped). Maintenance: target = maintenance.
These are the proposal's versioned engineering assumptions for a teaching benchmark, not clinical rules.
"""
from __future__ import annotations

ACTIVITY = {"mostly_sedentary": 1.20, "lightly_active": 1.375, "moderately_active": 1.55}
COEFF = {"male": 5, "female": -161}
FLOOR_KCAL = 1500
DEFICIT_FRACTION, DEFICIT_CAP = 0.10, 500
MACRO_SHARES = {"protein": 0.20, "carb": 0.50, "fat": 0.30}     # C-04 preset: reported, not gated here
BAND = 0.05                                                     # N-05: ±5 % per day


def bmi(weight_kg: float, height_cm: float) -> float:
    return weight_kg / (height_cm / 100) ** 2


def targets(body) -> dict:
    """{status, reason?, bmi, ree, maintenance, deficit, target, low, high, macros_g} — full precision."""
    b = body
    out = {"status": "ok", "bmi": bmi(b.weight_kg, b.height_cm)}
    if not 20 <= b.age_years <= 64:
        return dict(out, status="needs_professional_review", reason=f"age {b.age_years} is outside 20–64 (P-02)")
    if b.scope_concern:
        return dict(out, status="needs_professional_review", reason=f"scope concern: {b.scope_concern} (P-02)")
    if out["bmi"] < 18.5:
        return dict(out, status="needs_goal_review", reason=f"current BMI {out['bmi']:.1f} < 18.5 (P-03)")
    if b.goal == "weight_loss":
        if b.target_weight_kg is None or b.target_weight_kg >= b.weight_kg:
            return dict(out, status="needs_goal_review", reason="weight-loss target is not below current weight (P-04)")
        tb = bmi(b.target_weight_kg, b.height_cm)
        if tb < 18.5:
            return dict(out, status="needs_goal_review", reason=f"target BMI {tb:.1f} < 18.5 (P-03)")
    ree = 10 * b.weight_kg + 6.25 * b.height_cm - 5 * b.age_years + COEFF[b.equation_sex]
    maint = ree * ACTIVITY[b.activity]
    deficit = min(maint * DEFICIT_FRACTION, DEFICIT_CAP) if b.goal == "weight_loss" else 0.0
    target = maint - deficit
    out.update(ree=ree, maintenance=maint, deficit=deficit, target=target)
    if target < FLOOR_KCAL:
        return dict(out, status="needs_professional_review",
                    reason=f"computed target {target:.0f} kcal/day is below the {FLOOR_KCAL} floor (C-02); not clamped")
    low = max(FLOOR_KCAL, (1 - BAND) * target) if deficit else (1 - BAND) * target
    high = min((1 + BAND) * target, maint) if deficit else (1 + BAND) * target
    macros = {"protein": target * MACRO_SHARES["protein"] / 4, "carb": target * MACRO_SHARES["carb"] / 4,
              "fat": target * MACRO_SHARES["fat"] / 9}
    return dict(out, low=low, high=high, macros_g=macros)


def recipe_nutrients(recipe, ingredients) -> dict:
    """kcal and macros for ONE serving, from the per-100 g table."""
    tot = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    for i, g in recipe.grams.items():
        ing = ingredients[i]
        for k in tot:
            tot[k] += (getattr(ing, k) or 0.0) * g / 100
    return tot


def day_totals(plan, w) -> dict[int, dict]:
    """Per day: kcal and macro grams of the planned meals (portion × servings)."""
    days: dict[int, dict] = {}
    for m in plan.meals:
        if m.recipe_id not in w.recipes:
            continue
        n = recipe_nutrients(w.recipes[m.recipe_id], w.ingredients)
        d = days.setdefault(m.day, {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0})
        for k in d:
            d[k] += n[k] * m.portion * w.profile.servings
    return days


def macro_shares(day: dict) -> dict:
    """Energy shares by the normalized 4/4/9 contributions (proposal N-06). Reported, not gated."""
    e = {"protein": day["protein_g"] * 4, "carb": day["carb_g"] * 4, "fat": day["fat_g"] * 9}
    s = sum(e.values()) or 1.0
    return {k: v / s for k, v in e.items()}
