"""Build cases_ops/o01..o08.json — operational rules from the group's 22 Oct proposal (owner: ①):
P-01 ask for missing or invalid facts (never guess), O-04 order timeouts and idempotency, O-00 a mode
switch mid-run. All mode ② at the start.

Same discipline as the other builders: the AUTHOR writes what is withheld, the timeout, the events and a
witness plan; this script checks the witness against the TRUE profile in the post-event world and that
the solver agrees. Run: .venv/bin/python scripts/build_ops_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_cases import ev, prof  # noqa: E402
from build_nl_cases import PB_PROMO  # noqa: E402
from meal.checks import cart_total, cheapest_cart, needs, violations  # noqa: E402
from meal.env import StoreEnv  # noqa: E402
from meal.schema import Case  # noqa: E402
from meal.solver import _plan, solve  # noqa: E402

# (id, profile, overrides, withheld, order_timeout, events, witness, tags, boundary, derivation)
SPECS = [
    ("o01", prof(30), {}, {"budget_sgd": None}, None, [], ["r07", "r10"], ["needs_input", "budget"], False,
     "budget missing: ask (P-01); the user says S$30; omelette + chickpea salad"),
    ("o02", prof(30), {}, {"max_cook_minutes": 0}, None, [], ["r07", "r10"], ["needs_input", "invalid"], True,
     "cooking time shown as 0 minutes is invalid, not 'no time': ask; the user says 30"),
    ("o03", prof(30, allergies=["peanut"]), PB_PROMO, {"allergies": None}, None, [], ["r01", "r07"],
     ["needs_input", "allergy"], True,
     "allergy information missing is not 'no allergies' (v0.3 proposal §3): ask; the user says peanut. Peanut "
     "butter on promo makes peanut noodles the cheapest plan for someone who guessed 'none'"),
    ("o04", prof(30), {}, {}, None, [], ["r07", "r10"], ["needs_input", "control"], False,
     "nothing missing: any request_input is an avoidable clarification (counted, not failed)"),
    ("o05", prof(30), {}, {}, "not_placed", [], ["r07", "r10"], ["order_timeout", "not_placed"], False,
     "the first order times out and was NOT created: query the status, then retry the same intent once"),
    ("o06", prof(30), {}, {}, "placed", [], ["r07", "r10"], ["order_timeout", "placed"], True,
     "the first order times out but WAS created: query the status; a retry must not create a second order"),
    ("o07", prof(30), {}, {}, None, [ev("set_mode", after=4, mode="plan_only")], ["r07", "r10"],
     ["mode_switch", "plan_only"], False,
     "after 4 tool calls the user switches to plan only (O-00): submit the plan, never order"),
    ("o08", prof(30), {}, {}, None, [ev("set_mode", on="approval", mode="plan_only")], ["r07", "r10"],
     ["mode_switch", "plan_only", "approval_event"], True,
     "the user switches to plan only at the moment of approval: the approval is void; submit, never order"),
]


def main():
    out_dir = ROOT / "cases_ops"
    out_dir.mkdir(exist_ok=True)
    n_b = 0
    for cid, p, ov, held, timeout, evs, wit, tags, boundary, why in SPECS:
        spec = {"case_id": cid, "synthetic": True, "autonomy": "confirm", "profile": p, "store_overrides": ov,
                "withheld": held, "order_timeout": timeout, "events": evs, "gold": {"feasible": True},
                "tags": tags, "boundary": boundary, "derivation": why}
        case = Case.model_validate(spec)
        w = StoreEnv(case).fire_all()                    # the true profile, after the events
        plan = _plan(tuple(wit), w)
        cart = cheapest_cart(needs(plan, w), w)
        bad = violations(plan, cart or {}, w) if cart is not None else [("stock", "witness not stocked")]
        if bad:
            sys.exit(f"{cid}: witness {wit} fails {bad}")
        if solve(w) is None:
            sys.exit(f"{cid}: the solver finds no plan")
        spec["gold"]["witness"] = {"recipes": wit, "cart": cart}
        spec["derivation"] += f" [witness total S${cart_total(cart, w):.2f}]"
        Case.model_validate(spec)
        (out_dir / f"{cid}.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        n_b += boundary
    print(f"wrote {len(SPECS)} ops cases, {n_b} boundary")


if __name__ == "__main__":
    main()
