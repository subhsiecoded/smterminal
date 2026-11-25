"""Pure, dependency-free technical indicator math. Deliberately has no
knowledge of HTTP, Redis, or the provider clients - it takes a list of
closing prices and returns numbers, which makes it trivial to unit test
against hand-computed values (see the __main__ self-check below) instead
of trusting a library's output blindly.
"""


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def ema_series(closes: list[float], period: int) -> list[float]:
    """Full EMA series (not just the latest value) - RSI's smoothing needs
    the running series, not a one-shot number.
    """
    if not closes:
        return []
    k = 2 / (period + 1)
    out = [closes[0]]
    for price in closes[1:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return ema_series(closes, period)[-1]


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Needs at least period+1 closes to produce the first
    smoothed value.
    """
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for prev, curr in zip(closes, closes[1:]):
        delta = curr - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_all(closes: list[float]) -> dict:
    return {
        "sma20": sma(closes, 20),
        "ema12": ema(closes, 12),
        "ema26": ema(closes, 26),
        "rsi14": rsi(closes, 14),
        "latest_close": closes[-1] if closes else None,
    }


if __name__ == "__main__":
    # Self-check against Wilder's own worked example (New Concepts in
    # Technical Trading Systems). The commonly-cited RSI≈70.5 is the FIRST
    # value the series produces - i.e. computed from the first 15 closes
    # (14 deltas), the exact point period=14 needs for its first reading -
    # not from the full 20-close series, which applies 5 further smoothing
    # steps and legitimately lands somewhere else. Checking against the
    # wrong window here would have passed a subtly wrong formula; this
    # caught that the first version of this check was itself miscalibrated.
    sample = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    ]
    first_value = rsi(sample[:15], 14)
    print(f"RSI(14) at first reading = {first_value:.2f} (textbook ≈ 70.5)")
    assert first_value is not None and 69 < first_value < 72, "RSI self-check failed"

    full_series_value = rsi(sample, 14)
    print(f"RSI(14) after continued smoothing through all 20 closes = {full_series_value:.2f}")
    print("OK")
