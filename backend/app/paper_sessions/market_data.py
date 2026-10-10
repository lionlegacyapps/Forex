"""Session market-data abstraction — completed bars only for V1."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.market_data.models import Bar
from app.paper_sessions.errors import ActivationRejectedError, PaperSessionError


class SessionBarSource(Protocol):
    def get_completed_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        after: datetime | None,
        limit: int = 500,
    ) -> list[Bar]:
        """Return completed bars strictly after ``after`` (ascending)."""
        ...


class InMemorySessionBarSource:
    """Deterministic bar source for tests / offline dry-run."""

    def __init__(self, bars: list[Bar] | None = None) -> None:
        self._bars = list(bars or [])

    def load(self, bars: list[Bar]) -> None:
        self._bars = sorted(bars, key=lambda b: b.timestamp)

    def get_completed_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        after: datetime | None,
        limit: int = 500,
    ) -> list[Bar]:
        sym = symbol.strip().upper()
        out: list[Bar] = []
        for b in self._bars:
            if b.symbol.strip().upper() != sym:
                continue
            if b.timeframe != timeframe:
                continue
            if after is not None and b.timestamp <= after:
                continue
            # Completed bars only — require OHLC consistency already in Bar
            if b.high < b.low:
                raise PaperSessionError("incomplete/invalid bar", code="incomplete_bar")
            out.append(b)
            if len(out) >= limit:
                break
        return out


def assert_bars_fresh(
    bars: list[Bar],
    *,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if not bars:
        raise ActivationRejectedError("no market bars available", code="missing_market_data")
    latest = bars[-1].timestamp
    age = (now - latest).total_seconds()
    if age > max_age_seconds:
        raise ActivationRejectedError(
            f"stale market data age={age:.0f}s > {max_age_seconds}s",
            code="stale_market_data",
        )


def assert_bar_complete(bar: Bar) -> None:
    if bar.high < bar.low:
        raise PaperSessionError("incomplete bar: high < low", code="incomplete_bar")
    if min(bar.open, bar.close) < bar.low or max(bar.open, bar.close) > bar.high:
        raise PaperSessionError("incomplete bar: OHLC inconsistent", code="incomplete_bar")
