"""The meal-planning agent (owner: ③). TODO — this file only fixes the shape.

Implements runner.Agent: run(env) -> AgentUsage, acting ONLY through env.call(<tool>, **args).
Tools and what they do: env.TOOL_SPECS. What it must show (plan doc, 指标):
  - plan 3 days that pass every hard constraint (diet, allergies, time, coverage, stock, budget)
  - re-plan when a tool result carries `notices` (stock-out, price change, preference change)
  - request approval with its own computed total, then order with the token; never order otherwise
  - when no plan can work, report_infeasible with the binding constraint instead of relaxing it
Suggested build: Claude API tool use, stable system prompt cached, key from ANTHROPIC_API_KEY only,
token usage returned in AgentUsage.
"""
from __future__ import annotations


class MealAgent:  # TODO(③)
    def __init__(self, model: str, client=None):
        raise NotImplementedError("③ writes this")
