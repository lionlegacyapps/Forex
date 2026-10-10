"""Deterministic factor calculations inspired by Qlib-style factor research.

This is NOT the full Qlib expression engine. Factors use only point-in-time
history available at each row index (no lookahead).
"""

from __future__ import annotations

from decimal import Decimal

from app.research.data import ResearchBarFrame


def compute_return_factor(frame: ResearchBarFrame, *, period: int = 1) -> list[Decimal | None]:
    """Simple return: close[t]/close[t-period] - 1. None where insufficient history."""
    if period < 1:
        raise ValueError("period must be >= 1")
    closes = frame.closes
    out: list[Decimal | None] = []
    for i, price in enumerate(closes):
        if i < period or closes[i - period] == 0:
            out.append(None)
            continue
        out.append(price / closes[i - period] - Decimal("1"))
    return out


def compute_momentum_factor(frame: ResearchBarFrame, *, lookback: int = 5) -> list[Decimal | None]:
    """Momentum vs trailing mean of prior closes (excludes current close from mean)."""
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    closes = frame.closes
    out: list[Decimal | None] = []
    for i, price in enumerate(closes):
        if i < lookback:
            out.append(None)
            continue
        window = closes[i - lookback : i]  # prior bars only — no lookahead
        mean = sum(window, Decimal("0")) / Decimal(lookback)
        if mean == 0:
            out.append(None)
            continue
        out.append(price / mean - Decimal("1"))
    return out


def assert_no_lookahead_factor(
    values: list[Decimal | None],
    *,
    min_history: int,
) -> None:
    """Assert early indices are None (insufficient history)."""
    for i in range(min(min_history, len(values))):
        if values[i] is not None:
            raise AssertionError(f"Lookahead/leak at index {i}: expected None")
