"""Verify Alpaca market-data access through the existing provider (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.market_data.errors import MarketDataError
from app.market_data.models import Bar, MarketDataAssetClass
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.onboarding.errors import OnboardingBlockedError
from app.paper_sessions.market_data import assert_bar_complete


@dataclass(frozen=True, slots=True)
class MarketDataAccessResult:
    ok: bool
    feed: str
    host: str
    symbol: str
    bars_returned: int
    latest_bar_timestamp: datetime | None
    detail: str = ""


async def verify_alpaca_market_data_access(
    *,
    settings: Settings | None = None,
    symbol: str = "AAPL",
    timeframe: str = "1Day",
    lookback_days: int = 14,
    provider: AlpacaMarketDataProvider | None = None,
) -> MarketDataAccessResult:
    """Fetch recent completed bars via Market Data Provider — never invent prices."""
    cfg = settings or get_settings()
    host = (cfg.alpaca_data_base_url or "").rstrip("/")
    feed = (cfg.alpaca_data_feed or "iex").strip().lower()

    if provider is None:
        if not cfg.alpaca_api_key or not cfg.alpaca_api_secret:
            raise OnboardingBlockedError(
                "ALPACA_API_KEY / ALPACA_API_SECRET missing for market-data check",
                code="alpaca_credentials_missing",
            )
        provider = AlpacaMarketDataProvider(
            api_key=cfg.alpaca_api_key,
            api_secret=cfg.alpaca_api_secret,
            base_url=cfg.alpaca_data_base_url,
            timeout_seconds=max(cfg.market_data_timeout_seconds, 15.0),
            feed=feed,
        )

    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)
    try:
        bars: list[Bar] = await provider.get_bars(
            symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            asset_class=MarketDataAssetClass.EQUITY,
            limit=50,
        )
    except MarketDataError as exc:
        raise OnboardingBlockedError(
            f"Market-data access failed ({exc.code}): {exc.message}",
            code=exc.code.lower(),
        ) from exc

    if not bars:
        raise OnboardingBlockedError(
            "Market-data returned zero bars",
            code="bars_unavailable",
        )

    for bar in bars:
        assert_bar_complete(bar)

    latest = bars[-1].timestamp
    return MarketDataAccessResult(
        ok=True,
        feed=getattr(provider, "feed", feed),
        host=host,
        symbol=symbol.strip().upper(),
        bars_returned=len(bars),
        latest_bar_timestamp=latest,
        detail=f"feed={feed} bars={len(bars)} latest={latest.isoformat()}",
    )
