"""Freshness validation for market-data timestamps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.market_data.errors import STALE_MARKET_DATA, MarketDataError


def assert_fresh(
    timestamp: datetime,
    *,
    max_age_seconds: int,
    kind: str = "data",
) -> None:
    """Raise STALE_MARKET_DATA when ``timestamp`` is older than max age."""
    if max_age_seconds < 0:
        return
    ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    age = now - ts.astimezone(UTC)
    if age > timedelta(seconds=max_age_seconds):
        raise MarketDataError(
            f"{kind} is stale (age={age.total_seconds():.1f}s > {max_age_seconds}s)",
            code=STALE_MARKET_DATA,
        )


def is_fresh(timestamp: datetime, *, max_age_seconds: int) -> bool:
    try:
        assert_fresh(timestamp, max_age_seconds=max_age_seconds)
        return True
    except MarketDataError:
        return False
