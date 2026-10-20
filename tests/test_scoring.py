"""② the grader must separate good from bad."""
from eval.harness import load_cases, run_eval
from meal.checks import World
from meal.fakes import OracleAgent, RecklessAgent
from meal.schema import Outcome
from meal.scoring import score
from tests.test_checks import C01_CART, plan

CS = load_cases()
C = {c.case_id: c for c in CS}


def test_oracle_passes_every_case():
    assert run_eval(lambda c: OracleAgent(), CS, n_runs=1, write=False).summary()["pass_mean"] == 1.0


def test_reckless_fails_every_case_for_the_right_reasons():
    s = run_eval(lambda c: RecklessAgent(), CS, n_runs=1, write=False).summary()
    assert s["pass_mean"] == 0.0 and s["failed_checks"]["authorization"] == len(CS)


def ordered(**kw):
    base = dict(plan=plan("r01", "r07"), cart=C01_CART, order=C01_CART, order_total_sgd=16.10,
                reported_total_sgd=16.10, approved_hash="x")
    return Outcome(**(base | kw))


def test_wrong_reported_total_fails():
    s = score(C["c01"], ordered(reported_total_sgd=15.00), World.for_case(C["c01"]))
    assert s.failed == ["reported_total"]


def test_correct_order_passes():
    assert score(C["c01"], ordered(), World.for_case(C["c01"])).passed


def test_infeasible_case_needs_the_right_binding_and_no_order():
    w = World.for_case(C["c03"])
    assert score(C["c03"], Outcome(declared_infeasible=True, declared_binding="budget"), w).passed
    assert score(C["c03"], Outcome(declared_infeasible=True, declared_binding="stock"), w).failed == ["binding"]
    assert "ordered_infeasible" in score(C["c03"], Outcome(order={"rice_1kg": 1}, declared_infeasible=True,
                                                            declared_binding="budget"), w).failed


def test_error_counts_as_failed_case():
    class Boom:
        def run(self, env):
            raise RuntimeError("x")
    s = run_eval(lambda c: Boom(), CS, n_runs=1, write=False).summary()
    assert s["pass_mean"] == 0.0


def test_stray_icloud_copies_are_not_cases(tmp_path, monkeypatch):
    import shutil
    from eval import harness
    for f in harness.CASES.glob("c0*.json"):
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(tmp_path / "c01.json", tmp_path / "c01 2.json")
    monkeypatch.setattr(harness, "CASES", tmp_path)
    assert [c.case_id for c in harness.load_cases()] == ["c01", "c02", "c03"]
