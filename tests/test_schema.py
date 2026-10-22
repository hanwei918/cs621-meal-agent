"""① contracts."""
import json

import pytest
from pydantic import ValidationError

from eval.harness import CASES, load_cases
from meal.schema import Case


def raw(cid):
    return json.loads((CASES / f"{cid}.json").read_text(encoding="utf-8"))


def test_cases_load_with_enough_boundary_cases():
    cs = load_cases()
    assert [c.case_id for c in cs] == [f"c{i:02d}" for i in range(1, 31)]
    assert sum(c.boundary for c in cs) * 3 >= len(cs)
    assert all(c.gold.witness for c in cs if c.gold.feasible)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(synthetic=False),
    lambda d: d["gold"].update(feasible=False, binding=None),       # infeasible must name the binding
    lambda d: d["profile"].update(diet=["keto"]),                   # unknown diet
    lambda d: d.update(derivation="trust me"),                      # gold needs a real derivation
    lambda d: d["profile"].update(budget=40),                       # typo'd field
])
def test_bad_cases_rejected(mutate):
    d = raw("c01")
    mutate(d)
    with pytest.raises(ValidationError):
        Case.model_validate(d)
