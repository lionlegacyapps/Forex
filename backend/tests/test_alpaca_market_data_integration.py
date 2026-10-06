"""Optional live Alpaca market-data integration (SKIP without credentials)."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.market_data.service import MarketDataService


def _credentials() -> tuple[str, str] | None:
    get_settings.cache_clear()
    settings = get_settings()
    key = (settings.alpaca_api_key or os.getenv("ALPACA_API_KEY") or "").strip()
    secret = (settings.alpaca_api_secret or os.getenv("ALPACA_API_SECRET") or "").strip()
    if not key or not secret:
        return None
    return key, secret


@pytest.mark.asyncio
async def test_alpaca_market_data_readonly_optional() -> None:
    creds = _credentials()
    if creds is None:
        pytest.skip("ALPACA_API_KEY / ALPACA_API_SECRET not configured")

    key, secret = creds
    provider = AlpacaMarketDataProvider(
        api_key=key,
        api_secret=secret,
        timeout_seconds=10.0,
    )
    # Architectural: no trading methods
    assert not hasattr(provider, "place_order")

    svc = MarketDataService(provider, enforce_freshness=False)
    # Market may be closed — still expect a parseable latest quote or trade.
    try:
        quote = await svc.get_quote("AAPL", enforce_freshness=False)
        assert quote.symbol == "AAPL"
        assert quote.timestamp is not None
        if quote.bid_price is not None:
            assert isinstance(quote.bid_price, Decimal)
    except Exception:
        trade = await svc.get_latest_trade("AAPL", enforce_freshness=False)
        assert trade.symbol == "AAPL"
        assert isinstance(trade.price, Decimal)
        assert trade.timestamp is not None
