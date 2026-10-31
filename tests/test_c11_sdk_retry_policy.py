"""C11: use SDK's bounded retries, never add an application-level retry loop."""
from types import SimpleNamespace as NS
import sys

import pytest

from meal.agent import MealAgent
from meal.env import StoreEnv
from eval.harness import load_cases


def _case():
    return next(c for c in load_cases() if c.case_id == "c01")


def test_default_client_sets_explicit_sdk_retry_limit(monkeypatch):
    captured = []
    sdk_client = object()
    def ctor(**kwargs):
        captured.append(kwargs)
        return sdk_client
    monkeypatch.setitem(sys.modules, "anthropic", NS(Anthropic=ctor))
    agent = MealAgent("claude-haiku-5-5")
    assert agent._get_client() is sdk_client
    assert captured == [{"max_retries": 2}]


def test_sdk_client_is_cached(monkeypatch):
    created = []
    def ctor(**kwargs):
        obj = object()
        created.append(obj)
        return obj
    monkeypatch.setitem(sys.modules, "anthropic", NS(Anthropic=ctor))
    agent = MealAgent("claude-haiku-5-5")
    assert agent._get_client() is agent._get_client()
    assert len(created) == 1


def test_injected_client_is_unchanged(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("Injected clients must not instantiate the Anthropic SDK")
    monkeypatch.setitem(sys.modules, "anthropic", NS(Anthropic=unexpected))
    supplied = object()
    assert MealAgent("test", client=supplied)._get_client() is supplied


def test_no_second_application_level_retry_after_sdk_failure():
    class BrokenAPI:
        def __init__(self):
            self.messages = self
            self.calls = 0
        def create(self, **kw):
            self.calls += 1
            raise ConnectionError("SDK exhausted retry budget")
    fake = BrokenAPI()
    agent = MealAgent("test", client=fake)
    env = StoreEnv(_case())
    with pytest.raises(ConnectionError, match="SDK exhausted retry budget"):
        agent.run(env)
    assert fake.calls == 1  # the SDK itself has already performed its retries
    assert env.out.steps == 0  # no action when API response fails


def test_no_new_dependency_or_public_agent_argument():
    import inspect
    sig = inspect.signature(MealAgent)
    assert "api_retries" not in sig.parameters
    assert "max_steps" in sig.parameters and "max_cost_usd" in sig.parameters
