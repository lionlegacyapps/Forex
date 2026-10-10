"""Market data package — read-only quotes/trades/bars.

ALPACA MARKET DATA ACCESS DOES NOT ENABLE ALPACA ORDER EXECUTION.
"""

from app.market_data.errors import (
    AUTHENTICATION_FAILED,
    BARS_UNAVAILABLE,
    INVALID_SYMBOL,
    PRICE_UNAVAILABLE,
    PROVIDER_UNAVAILABLE,
    QUOTE_UNAVAILABLE,
    RATE_LIMITED,
    STALE_MARKET_DATA,
    TRADE_UNAVAILABLE,
    UNSUPPORTED_ASSET_CLASS,
    MarketDataError,
)
from app.market_data.models import Bar, MarketDataAssetClass, Quote, ReferencePrice, Trade
from app.market_data.provider import MarketDataProvider
from app.market_data.providers import (
    AlpacaMarketDataProvider,
    FakeMarketDataProvider,
    SimulationMarketDataProvider,
)
from app.market_data.service import MarketDataService

__all__ = [
    "MarketDataProvider",
    "MarketDataService",
    "MarketDataError",
    "Quote",
    "Trade",
    "Bar",
    "ReferencePrice",
    "MarketDataAssetClass",
    "AlpacaMarketDataProvider",
    "FakeMarketDataProvider",
    "SimulationMarketDataProvider",
    "PRICE_UNAVAILABLE",
    "QUOTE_UNAVAILABLE",
    "TRADE_UNAVAILABLE",
    "STALE_MARKET_DATA",
    "PROVIDER_UNAVAILABLE",
    "INVALID_SYMBOL",
    "RATE_LIMITED",
    "AUTHENTICATION_FAILED",
    "UNSUPPORTED_ASSET_CLASS",
    "BARS_UNAVAILABLE",
]
