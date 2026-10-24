"""Stress set: gold by construction — every event hits an item the witness does not use, every note
excludes something the witness does not contain."""
from eval.harness import load_cases, run_eval
from meal.fakes import OracleAgent

S = load_cases(case_set="stress")
WITNESS_SKUS = {"egg_10pk", "tomato_500g", "spring_onion_100g", "chickpeas_400g", "cucumber_2pk"}


def test_shape():
    dims = {t.split(":")[1] for c in S for t in c.tags if t.startswith("dim:")}
    assert len(S) == 42 and dims == {"events", "days", "notes", "mixed"}


def test_events_never_touch_the_witness():
    for c in S:
        assert all(e.sku not in WITNESS_SKUS for e in c.events), c.case_id
        assert set(c.gold.witness.cart) <= WITNESS_SKUS


def test_event_count_matches_the_level():
    for c in S:
        if "dim:events" in c.tags:
            assert len(c.events) == int(next(t for t in c.tags if t.startswith("level:"))[6:])


def test_oracle_passes_every_stress_case():
    assert run_eval(lambda c: OracleAgent(), S, n_runs=1, write=False, case_set="stress").summary()["pass_mean"] == 1.0
