"""MACD — independent implementation (EMA-based)."""

from __future__ import annotations

from decimal import Decimal

from app.indicators.ema import ema


def macd(
    closes: list[Decimal],
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    """Return (macd_line, signal_line, histogram).

    Warm-up: MACD line None until slow EMA available; signal None until
    ``signal`` MACD values after that.
    """
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("MACD periods must be >= 1")
    if fast >= slow:
        raise ValueError("fast period must be < slow period")

    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line: list[Decimal | None] = []
    for f, s in zip(fast_ema, slow_ema, strict=True):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)

    # Signal EMA over macd_line — treat None as missing; seed after enough non-None
    signal_line = _ema_sparse(macd_line, signal)
    hist: list[Decimal | None] = []
    for m, sig in zip(macd_line, signal_line, strict=True):
        if m is None or sig is None:
            hist.append(None)
        else:
            hist.append(m - sig)
    return macd_line, signal_line, hist


def _ema_sparse(values: list[Decimal | None], period: int) -> list[Decimal | None]:
    """EMA that skips leading Nones; seeds with SMA of first ``period`` non-None values in order."""
    out: list[Decimal | None] = [None] * len(values)
    collected: list[Decimal] = []
    prev: Decimal | None = None
    k = Decimal("2") / (Decimal(period) + Decimal("1"))
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            collected.append(v)
            if len(collected) == period:
                prev = sum(collected, Decimal("0")) / Decimal(period)
                out[i] = prev
            continue
        prev = v * k + prev * (Decimal("1") - k)
        out[i] = prev
    return out
