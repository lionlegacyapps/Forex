"""ATR (Average True Range, Wilder) — independent implementation."""

from __future__ import annotations

from decimal import Decimal


def atr(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("highs/lows/closes length mismatch")
    out: list[Decimal | None] = [None] * n
    if n <= period:
        return out

    trs: list[Decimal] = []
    for i in range(n):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

    # First ATR at index ``period`` using SMA of TR[1..period] (Wilder common seed)
    seed = sum(trs[1 : period + 1], Decimal("0")) / Decimal(period)
    out[period] = seed
    prev = seed
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / Decimal(period)
        out[i] = prev
    return out
