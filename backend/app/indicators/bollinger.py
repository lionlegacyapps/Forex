"""Bollinger Bands — independent implementation."""

from __future__ import annotations

from decimal import Decimal

from app.indicators.ema import sma


def bollinger_bands(
    closes: list[Decimal],
    *,
    period: int = 20,
    num_std: Decimal = Decimal("2"),
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    """Return (middle, upper, lower). Population stdev over the SMA window."""
    if period < 2:
        raise ValueError("period must be >= 2")
    if num_std < 0:
        raise ValueError("num_std must be >= 0")
    mid = sma(closes, period)
    upper: list[Decimal | None] = []
    lower: list[Decimal | None] = []
    for i in range(len(closes)):
        if mid[i] is None:
            upper.append(None)
            lower.append(None)
            continue
        window = closes[i + 1 - period : i + 1]
        mean = mid[i]
        assert mean is not None
        var = sum((x - mean) ** 2 for x in window) / Decimal(period)
        # Decimal sqrt via float for stdev — deterministic for fixture sizes
        std = Decimal(str(float(var) ** 0.5))
        upper.append(mean + num_std * std)
        lower.append(mean - num_std * std)
    return mid, upper, lower
