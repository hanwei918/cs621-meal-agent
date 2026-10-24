"""③ the agent loop, with a scripted fake client (no API calls, no cost)."""
import copy
import json
from types import SimpleNamespace as NS

from eval.harness import load_cases
from meal.agent import SYSTEM, TOOLS, MealAgent
from meal.runner import run_case
from tests.test_checks import C01_CART, plan

C = {c.case_id: c for c in load_cases()}


def use(name, args, i):
    return NS(type="tool_use", id=f"tu{i}", name=name, input=args)


def resp(blocks, stop="tool_use"):
    return NS(content=blocks, stop_reason=stop,
              usage=NS(input_tokens=100, output_tokens=10, cache_read_input_tokens=50, cache_creation_input_tokens=5))


def last_result(msgs, tool_use_id):
    for m in reversed(msgs):
        if m["role"] == "user" and isinstance(m["content"], list):
            for r in m["content"]:
                if r.get("tool_use_id") == tool_use_id:
                    return json.loads(r["content"])


class FakeClient:
    """Each script entry is a function(messages) -> response, so later steps can read earlier results."""
    def __init__(self, script):
        self.script, self.sent = list(script), []
        self.messages = self

    def create(self, **kw):
        self.sent.append(copy.deepcopy({k: v for k, v in kw.items() if k != "messages"}) | {"n": len(kw["messages"])})
        return self.script.pop(0)(kw["messages"])


GOOD = [
    lambda m: resp([use("get_profile", {}, 1)]),
    lambda m: resp([use("set_plan", {"meals": [x.model_dump() for x in plan("r01", "r07").meals]}, 2)]),
    lambda m: resp([use("add_to_cart", {"sku": s, "packs": n}, 10 + k) for k, (s, n) in enumerate(C01_CART.items())]),
    lambda m: resp([use("request_approval", {"reported_total_sgd": 16.10}, 3)]),
    lambda m: resp([use("place_order", {"token": last_result(m, "tu3")["token"]}, 4)]),
    lambda m: resp([NS(type="text", text="never reached")], "end_turn"),
]


def test_scripted_agent_orders_and_passes():
    fc = FakeClient(GOOD)
    r = run_case(MealAgent("claude-haiku-5-5", client=fc), C["c01"])
    assert r.score.passed, r.score
    assert len(fc.sent) == 5                                   # stopped right after the order
    assert r.usage.input_tokens == 500 and r.usage.cache_read_tokens == 250


def test_prefix_is_stable_and_cached():
    fc = FakeClient(GOOD)
    run_case(MealAgent("claude-haiku-5-5", client=fc), C["c01"])
    assert all(s["system"] == SYSTEM and s["tools"] == TOOLS for s in fc.sent)
    assert all(s["cache_control"] == {"type": "ephemeral"} for s in fc.sent)


def test_parallel_tool_results_return_in_one_message():
    fc = FakeClient(GOOD)
    run_case(MealAgent("claude-haiku-5-5", client=fc), C["c01"])
    assert fc.sent[3]["n"] == fc.sent[2]["n"] + 2              # one assistant + ONE user message for 5 tool calls


def test_bad_tool_call_is_reported_as_error_and_loop_continues():
    seen = {}
    def check(m):
        seen["r"] = last_result(m, "tu1")
        return resp([NS(type="text", text="stop")], "end_turn")
    fc = FakeClient([lambda m: resp([use("add_to_cart", {"sku": "caviar", "packs": 1}, 1)]), check])
    r = run_case(MealAgent("claude-haiku-5-5", client=fc, max_nudges=0), C["c01"])   # about errors, not nudges
    assert "error" in seen["r"] and r.score.failed == ["no_order"]


def test_step_cap_stops_a_looping_agent():
    fc = FakeClient([lambda m: resp([use("view_cart", {}, 1)])] * 5)
    run_case(MealAgent("claude-haiku-5-5", client=fc, max_steps=5), C["c01"])
    assert len(fc.sent) == 5


def test_single_call_baseline_applies_its_answer_through_the_tools():
    from meal.baselines import SingleCallBaseline
    ans = {"feasible": True, "binding": "none", "meals": [m.model_dump() for m in plan("r01", "r07").meals],
           "cart": [{"sku": s, "packs": n} for s, n in C01_CART.items()], "total_sgd": 16.10}
    fc = FakeClient([lambda m: resp([NS(type="text", text=json.dumps(ans))], "end_turn")])
    r = run_case(SingleCallBaseline("claude-haiku-5-5", client=fc), C["c01"])
    assert r.score.passed and len(fc.sent) == 1 and "tools" not in fc.sent[0]


def test_single_call_cannot_react_to_an_approval_event():
    """c29: eggs sell out at approval. A plan with eggs gets approved, revoked, and the baseline stops."""
    from meal.baselines import SingleCallBaseline
    from meal.checks import World, cheapest_cart, needs
    w = World.for_case(C["c29"])
    p = plan("r01", "r07")
    ans = {"feasible": True, "binding": "none", "meals": [m.model_dump() for m in p.meals],
           "cart": [{"sku": s, "packs": n} for s, n in cheapest_cart(needs(p, w), w).items()], "total_sgd": 0}
    from meal.checks import cart_total
    ans["total_sgd"] = cart_total({x["sku"]: x["packs"] for x in ans["cart"]}, w)
    fc = FakeClient([lambda m: resp([NS(type="text", text=json.dumps(ans))], "end_turn")])
    r = run_case(SingleCallBaseline("claude-haiku-5-5", client=fc), C["c29"])
    assert not r.score.passed and r.score.failed == ["no_order"]



def _c03():
    from meal.env import StoreEnv
    return StoreEnv({c.case_id: c for c in load_cases()}["c03"])


def test_a_silent_give_up_is_nudged_once_then_the_agent_continues():
    from meal.agent import NUDGE
    seen = []
    script = [lambda m: resp([use("get_profile", {}, 1)]),
              lambda m: resp([], stop="end_turn"),                      # stops with no result
              lambda m: (seen.append(m[-1]["content"]), resp([use("report_infeasible",
                                                                  {"binding": "budget", "explanation": "x"}, 2)]))[1]]
    env = _c03()
    u = MealAgent("claude-haiku-5-5", client=FakeClient(script)).run(env)
    assert u.nudges == 1 and env.out.declared_infeasible and seen == [NUDGE]


def test_only_one_nudge_and_none_after_a_result():
    client = FakeClient([lambda m: resp([], stop="end_turn"), lambda m: resp([], stop="end_turn")])
    assert MealAgent("claude-haiku-5-5", client=client).run(_c03()).nudges == 1 and len(client.sent) == 2
    client = FakeClient([lambda m: resp([use("report_infeasible", {"binding": "budget", "explanation": "x"}, 1)]),
                         lambda m: resp([], stop="end_turn")])
    assert MealAgent("claude-haiku-5-5", client=client).run(_c03()).nudges == 0
