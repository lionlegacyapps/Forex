"""SMA and EMA — independent implementations."""

from __future__ import annotations

from decimal import Decimal


def sma(values: list[Decimal], period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = []
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
            continue
        window = values[i + 1 - period : i + 1]
        out.append(sum(window, Decimal("0")) / Decimal(period))
    return out


def ema(values: list[Decimal], period: int) -> list[Decimal | None]:
    """EMA seeded with SMA of the first ``period`` values (standard convention)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = seed
    k = Decimal("2") / (Decimal(period) + Decimal("1"))
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (Decimal("1") - k)
        out[i] = prev
    return out
