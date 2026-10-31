"""Standard USD per million tokens (input, output, 5m cache write, cache read).

Source: Anthropic Claude Platform model pricing, verified 2026-10-31:
https://platform.claude.com/docs/en/about-claude/pricing

Scope: first-party global API, standard pricing. Haiku 5.5 has higher rates when
an *individual prompt* exceeds 100k tokens; this function only receives aggregate
tokens and cannot determine that threshold. This estimator also excludes other
pricing modifiers. Unknown model IDs retain the existing 0.0 fallback, which is
NOT proof of zero billable cost; verify pricing before paid formal evaluations.
"""
PRICES = {
    "claude-opus-5-5":   (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-haiku-5-5":  (0.10, 0.50, 0.125, 0.01),
}


def cost_usd(model: str, inp: int, out: int, cache_write: int = 0, cache_read: int = 0) -> float:
    if model not in PRICES:
        return 0.0
    i, o, w, r = PRICES[model]
    return (inp * i + out * o + cache_write * w + cache_read * r) / 1e6
