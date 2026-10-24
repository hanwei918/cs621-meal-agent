"""meal/energy.py against the proposal's own arithmetic fixture (§4 C-05) and gates P-02–P-04, C-02."""
import pytest

from meal.energy import targets
from meal.schema import Body


def body(**kw):
    base = dict(age_years=30, height_cm=175, weight_kg=80, equation_sex="male", activity="mostly_sedentary",
                goal="weight_loss", target_weight_kg=72)
    return Body(**(base | kw))


def test_proposal_fixture_to_the_hundredth():
    t = targets(body())                       # 80 kg, 175 cm, 30 y, male, mostly sedentary
    assert t["status"] == "ok"
    assert t["ree"] == pytest.approx(1748.75, abs=0.01)
    assert t["maintenance"] == pytest.approx(2098.50, abs=0.01)
    assert t["deficit"] == pytest.approx(209.85, abs=0.01)
    assert t["target"] == pytest.approx(1888.65, abs=0.01)
    assert t["low"] == pytest.approx(0.95 * 1888.65, abs=0.01) and t["high"] == pytest.approx(1.05 * 1888.65, abs=0.01)


def test_deficit_is_capped_at_500(monkeypatch):
    # at the default 10 % the cap needs maintenance > 5,000 kcal; the proposal allows a reviewed 10–20 %
    import meal.energy as e
    monkeypatch.setattr(e, "DEFICIT_FRACTION", 0.20)
    t = targets(body(weight_kg=150, target_weight_kg=100, activity="moderately_active"))   # maintenance ≈ 3,795
    assert t["deficit"] == 500 and t["high"] <= t["maintenance"]


def test_maintenance_has_no_deficit():
    t = targets(body(goal="maintenance", target_weight_kg=None))
    assert t["deficit"] == 0 and t["target"] == pytest.approx(2098.50, abs=0.01)


@pytest.mark.parametrize("kw,status", [
    (dict(age_years=17), "needs_professional_review"),
    (dict(age_years=65), "needs_professional_review"),
    (dict(scope_concern="pregnant"), "needs_professional_review"),
    (dict(weight_kg=55, height_cm=175, target_weight_kg=50), "needs_goal_review"),        # current BMI 18.0
    (dict(height_cm=170, weight_kg=58, target_weight_kg=50), "needs_goal_review"),        # target BMI 17.3
    (dict(target_weight_kg=80), "needs_goal_review"),                                     # not below current
    (dict(age_years=45, equation_sex="female", height_cm=160, weight_kg=58, target_weight_kg=52),
     "needs_professional_review"),                                                       # target 1289.5 < floor
])
def test_gates(kw, status):
    assert targets(body(**kw))["status"] == status


def test_below_floor_is_not_clamped():
    t = targets(body(age_years=45, equation_sex="female", height_cm=160, weight_kg=58, target_weight_kg=52))
    assert t["target"] == pytest.approx(1289.52, abs=0.01) and "low" not in t
