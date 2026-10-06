"""Market-data error codes and exceptions (no fabricated prices)."""

from __future__ import annotations


PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
QUOTE_UNAVAILABLE = "QUOTE_UNAVAILABLE"
TRADE_UNAVAILABLE = "TRADE_UNAVAILABLE"
STALE_MARKET_DATA = "STALE_MARKET_DATA"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
INVALID_SYMBOL = "INVALID_SYMBOL"
RATE_LIMITED = "RATE_LIMITED"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
UNSUPPORTED_ASSET_CLASS = "UNSUPPORTED_ASSET_CLASS"
BARS_UNAVAILABLE = "BARS_UNAVAILABLE"


class MarketDataError(Exception):
    """Provider/service failure with a stable reason code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)
