"""USD per million tokens (input, output, cache write 5 min, cache read). Source: claude-api skill model
table cached 2026-10-06; Haiku 5.5 cache read assumed 0.1× input. Re-check before formal runs."""
PRICES = {
    "claude-opus-5-5":   (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5":  (0.10, 0.50, 0.125, 0.01),
}


def cost_usd(model: str, inp: int, out: int, cache_write: int = 0, cache_read: int = 0) -> float:
    if model not in PRICES:
        return 0.0
    i, o, w, r = PRICES[model]
    return (inp * i + out * o + cache_write * w + cache_read * r) / 1e6
