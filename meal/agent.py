"""The meal-planning agent (owner: ③).

Implements runner.Agent: run(env) -> AgentUsage, acting ONLY through env.call(<tool>, **args).
Manual tool loop on the Claude API: we need the step cap, usage accounting and a clean stop
after the order or the infeasibility report. Tools + system prompt are byte-identical across
cases (cacheable); top-level automatic caching moves the breakpoint as the conversation grows.
Credentials come from the environment only (ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import json

from .env import TOOL_SPECS, StoreEnv
from .runner import AgentUsage

SYSTEM = """You plan three days of home cooking and do the grocery shopping for one user, in a simulated store, \
by calling tools. The user's profile (get_profile) holds hard constraints you must never relax: diet, allergies, \
budget in S$, days, meals per day, servings, maximum cooking minutes per meal, and what is already in the pantry.

How to work
- Read the profile. Search recipes within the time limit. Open each candidate with get_recipe and check every \
ingredient's allergens and animal against the profile (vegetarian excludes chicken, pork, beef, fish, shellfish).
- Fill every day × meal slot exactly once with set_plan.
- For each ingredient: grams needed = recipe grams × servings summed over the plan, minus the pantry. \
Buy whole packs (find_items) that cover it, only from items in stock, cheapest per gram first.
- Keep the cart total within budget. Check view_cart before asking for approval.
- Tool results may carry `notices` (an item went out of stock, a price changed, the user changed a preference). \
When they do, re-check the plan and the cart against the new situation and fix them; approval is revoked by any change.
- request_approval with the exact cart total you computed. If it is refused, read the violations, fix them, ask again.
- After approval, call place_order with the token, then stop.
- If no plan can satisfy every constraint, call report_infeasible with the binding constraint \
(budget, diet, time or stock) and stop. To name it, apply the constraints in this order: diet and allergies, \
then cooking time, then stock, then budget; the binding one is the first after which no valid plan is left. Never relax a constraint and never order without approval.
- This is not nutrition or medical advice; follow only the user's stated constraints."""

_S, _I = {"type": "string"}, {"type": "integer"}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


SCHEMAS = {
    "get_profile": _obj({}, []),
    "search_recipes": _obj({"max_minutes": _I}, []),
    "get_recipe": _obj({"recipe_id": _S}, ["recipe_id"]),
    "find_items": _obj({"ingredient": _S}, ["ingredient"]),
    "set_plan": _obj({"meals": {"type": "array", "items": _obj({"day": _I, "slot": _I, "recipe_id": _S},
                                                                ["day", "slot", "recipe_id"])}}, ["meals"]),
    "add_to_cart": _obj({"sku": _S, "packs": _I}, ["sku", "packs"]),
    "remove_from_cart": _obj({"sku": _S, "packs": _I}, ["sku", "packs"]),
    "view_cart": _obj({}, []),
    "request_approval": _obj({"reported_total_sgd": {"type": "number"}}, ["reported_total_sgd"]),
    "place_order": _obj({"token": _S}, ["token"]),
    "report_infeasible": _obj({"binding": {"type": "string", "enum": ["budget", "diet", "time", "stock"]},
                               "explanation": _S}, ["binding", "explanation"]),
}
assert set(SCHEMAS) == set(TOOL_SPECS), "every env tool needs a schema"
TOOLS = [{"name": n, "description": TOOL_SPECS[n], "input_schema": SCHEMAS[n]} for n in TOOL_SPECS]


class MealAgent:
    def __init__(self, model: str, client=None, effort: str | None = None, max_steps: int = 40):
        self.model, self.effort, self.max_steps = model, effort, max_steps
        self._client = client

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def run(self, env: StoreEnv) -> AgentUsage:
        client, u = self._get_client(), AgentUsage()
        messages = [{"role": "user", "content": "Plan my meals for the coming days and do the shopping."}]
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}
        for _ in range(self.max_steps):
            resp = client.messages.create(model=self.model, max_tokens=8000, system=SYSTEM, tools=TOOLS,
                                          messages=messages, cache_control={"type": "ephemeral"}, **extra)
            us = resp.usage
            u.input_tokens += us.input_tokens
            u.output_tokens += us.output_tokens
            u.cache_read_tokens += getattr(us, "cache_read_input_tokens", 0) or 0
            u.cache_write_tokens += getattr(us, "cache_creation_input_tokens", 0) or 0
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                break                                            # end_turn, refusal, max_tokens: stop
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    out = env.call(b.name, **(b.input or {}))
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": json.dumps(out, ensure_ascii=False), "is_error": "error" in out})
            messages.append({"role": "user", "content": results})
            if env.out.order is not None or env.out.declared_infeasible:
                break                                            # done: nothing after L1 / the report
        return u
