"""C12 regression: standard-rate pricing and source-backed Sonnet cache hit."""
import pytest

from eval.pricing import PRICES, cost_usd


def test_sonnet_55_cache_hit_uses_verified_rate():
    assert PRICES["claude-sonnet-5-5"][3] == pytest.approx(0.10)


def test_sonnet_55_read_pricing():
    assert cost_usd("claude-sonnet-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.10)


def test_sonnet_55_standard_uncached_pricing():
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)


def test_sonnet_55_cache_write_unchanged():
    assert cost_usd("claude-sonnet-5-5", 0, 0, cache_write=1_000_000) == pytest.approx(2.50)


def test_haiku_55_standard_rates_unchanged():
    assert PRICES["claude-haiku-5-5"] == (0.10, 0.50, 0.125, 0.01)


def test_opus_55_standard_rates_unchanged():
    assert PRICES["claude-opus-5-5"] == (4.00, 20.00, 5.00, 0.20)


def test_non_cached_computation_remains_same():
    assert cost_usd("claude-haiku-5-5", 1000, 2000, 100, 5000) == pytest.approx(
        (1000 * .10 + 2000 * .50 + 100 * .125 + 5000 * .01) / 1_000_000
    )


def test_unknown_model_legacy_behavior_unchanged():
    # Existing API behavior deliberately kept unchanged in this narrow P2 patch.
    assert cost_usd("unknown-model", 12, 34) == 0.0
