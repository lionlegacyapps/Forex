"""Wilder RSI — independent implementation."""

from __future__ import annotations

from decimal import Decimal


def rsi(closes: list[Decimal], period: int = 14) -> list[Decimal | None]:
    """Relative Strength Index (Wilder smoothing).

    Warm-up: first ``period`` bars are None (need ``period`` changes → index period).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(closes)
    out: list[Decimal | None] = [None] * n
    if n <= period:
        return out

    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else Decimal("0"))
        losses.append(-delta if delta < 0 else Decimal("0"))
    avg_gain = sum(gains, Decimal("0")) / Decimal(period)
    avg_loss = sum(losses, Decimal("0")) / Decimal(period)
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)

    for i in range(period + 1, n):
        delta = closes[i] - closes[i - 1]
        gain = delta if delta > 0 else Decimal("0")
        loss = -delta if delta < 0 else Decimal("0")
        avg_gain = (avg_gain * (period - 1) + gain) / Decimal(period)
        avg_loss = (avg_loss * (period - 1) + loss) / Decimal(period)
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return Decimal("100") if avg_gain > 0 else Decimal("50")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))
