"""Runs one case: a fresh StoreEnv, the agent works it through tools, then score.

Agent interface (owner: ③; baselines ⑤ use the same):
    agent.run(env: StoreEnv) -> AgentUsage
The agent may only act through env.call(<tool>, **args); env.out is filled by the tools, never by
the agent. Return token usage for the cost ledger (zeros for code-only agents).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .env import StoreEnv
from .schema import Case, Outcome
from .scoring import Score, score


@dataclass
class AgentUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    nudges: int = 0                       # times the agent tried to stop with no result and was told to finish
    stop_reason: str = ""                 # why the loop ended: the API stop_reason, "result", "max_steps" or "cost"
    turns: int = 0                        # model calls made


class Agent(Protocol):
    def run(self, env: StoreEnv) -> AgentUsage: ...


@dataclass
class CaseResult:
    case_id: str
    outcome: Outcome
    score: Score
    log: list[str] = field(default_factory=list)
    usage: AgentUsage = field(default_factory=AgentUsage)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    error: Optional[str] = None


def run_case(agent: Agent, case: Case, gates: bool = True) -> CaseResult:
    t0 = time.perf_counter()
    env = StoreEnv(case, gates=gates)
    usage = agent.run(env) or AgentUsage()
    s = score(case, env.out, env.w)
    return CaseResult(case.case_id, env.out, s, list(env.w.log), usage, latency_s=round(time.perf_counter() - t0, 2))
