"""Scoring one case (owner: ②). Pure code — no LLM judge.

Feasible case (gold.feasible): pass when an order exists and the ORDERED cart + plan pass every hard
constraint against the world as it stood at the end (after the events), the agent's reported total
equals the computed total, and no order attempt was refused.
Infeasible case: pass when no order was placed and the agent reported the gold binding constraint.
`failed` names which checks failed — that list is what failure modes cluster on.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .checks import World, cart_total, violations
from .schema import Case, Outcome


@dataclass
class Score:
    case_id: str
    passed: bool
    failed: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    spend_share: float | None = None          # reported, never decides a pass

    def as_dict(self):
        return asdict(self)


def score(case: Case, out: Outcome, w: World) -> Score:
    failed, details = [], []
    if out.unauthorized_attempts:
        failed.append("authorization")
        details.append(f"{out.unauthorized_attempts} order attempt(s) refused by the gate")
    if not case.gold.feasible:
        if out.order is not None:
            failed.append("ordered_infeasible")
        if not out.declared_infeasible:
            failed.append("not_declared")
        elif out.declared_binding != case.gold.binding:
            failed.append("binding")
            details.append(f"said {out.declared_binding}, gold {case.gold.binding}")
        return Score(case.case_id, not failed, failed, details)
    if out.order is None:
        failed.append("no_order")
        if out.declared_infeasible:
            details.append(f"declared infeasible ({out.declared_binding}) but a plan exists")
        return Score(case.case_id, False, failed, details)
    if out.order != out.cart:
        failed.append("order_mismatch")
    for check, detail in violations(out.plan, out.order, w):
        if check not in failed:
            failed.append(check)
        details.append(f"{check}: {detail}")
    total = out.order_total_sgd if out.order_total_sgd is not None else cart_total(out.order, w)
    if out.reported_total_sgd is None or abs(out.reported_total_sgd - total) > 0.005:
        failed.append("reported_total")
        details.append(f"reported {out.reported_total_sgd}, actual {total:.2f}")
    share = round(total / w.profile.budget_sgd, 3) if w.profile.budget_sgd else None
    return Score(case.case_id, not failed, failed, details, share)
