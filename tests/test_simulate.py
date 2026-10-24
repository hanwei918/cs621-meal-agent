"""Simulated pilot: persona truths are satisfiable, and the reading metric does not count what the profile
already excluded. No API calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from simulate_users import PERSONAS, build, recipe_exclusions  # noqa: E402

from meal.checks import World  # noqa: E402
from meal.schema import NoteConstraints  # noqa: E402
from meal.solver import solve  # noqa: E402


def test_every_persona_truth_has_a_valid_plan():
    for p in PERSONAS:
        c = build(p, "")
        w = World.for_case(c)
        w.note = c.gold.note
        assert c.gold.out_of_scope or solve(w) is not None, p["id"]


def test_profile_exclusions_are_not_counted_as_over_reading():
    p = next(x for x in PERSONAS if x["id"] == "mei")                     # vegetarian profile
    c = build(p, "")
    w = World.for_case(c)
    with_meat = NoteConstraints(exclude_ingredients=["egg", "tofu"], exclude_recipes=["r02", "r06", "r08"])
    assert recipe_exclusions(with_meat, w) == recipe_exclusions(c.gold.note, w) == {"r01", "r03", "r07"}
    assert recipe_exclusions(NoteConstraints(exclude_ingredients=["tomato"]), w) & {"r07", "r09", "r10"}
