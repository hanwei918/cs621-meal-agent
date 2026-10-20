"""① contracts."""
import json

import pytest
from pydantic import ValidationError

from eval.harness import CASES, load_cases
from meal.schema import Case


def raw(cid):
    return json.loads((CASES / f"{cid}.json").read_text(encoding="utf-8"))


def test_cases_load():
    assert [c.case_id for c in load_cases()] == ["c01", "c02", "c03"]


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
