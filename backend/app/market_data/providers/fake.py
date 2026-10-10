"""Injectable fake provider for deterministic unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.errors import (
    AUTHENTICATION_FAILED,
    INVALID_SYMBOL,
    QUOTE_UNAVAILABLE,
    RATE_LIMITED,
    TRADE_UNAVAILABLE,
    UNSUPPORTED_ASSET_CLASS,
    MarketDataError,
)
from app.market_data.models import Bar, MarketDataAssetClass, Quote, Trade
from app.market_data.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    """In-memory fake with controllable quotes/trades/errors."""

    def __init__(self) -> None:
        self.quotes: dict[str, Quote] = {}
        self.trades: dict[str, Trade] = {}
        self.bars: dict[str, list[Bar]] = {}
        self.fail_with: MarketDataError | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    def set_quote(
        self,
        symbol: str,
        *,
        bid: Decimal,
        ask: Decimal,
        timestamp: datetime | None = None,
        bid_size: Decimal | None = None,
        ask_size: Decimal | None = None,
    ) -> None:
        sym = symbol.strip().upper()
        self.quotes[sym] = Quote(
            symbol=sym,
            bid_price=bid,
            ask_price=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            timestamp=timestamp or datetime.now(UTC),
            provider=self.provider_name,
        )

    def set_trade(
        self,
        symbol: str,
        *,
        price: Decimal,
        timestamp: datetime | None = None,
        size: Decimal | None = None,
    ) -> None:
        sym = symbol.strip().upper()
        self.trades[sym] = Trade(
            symbol=sym,
            price=price,
            size=size,
            timestamp=timestamp or datetime.now(UTC),
            provider=self.provider_name,
        )

    async def get_quote(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Quote:
        self._check_fail(asset_class)
        sym = symbol.strip().upper()
        if not sym:
            raise MarketDataError("Invalid symbol", code=INVALID_SYMBOL)
        q = self.quotes.get(sym)
        if q is None:
            raise MarketDataError(f"No quote for {sym}", code=QUOTE_UNAVAILABLE)
        return q

    async def get_latest_trade(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Trade:
        self._check_fail(asset_class)
        sym = symbol.strip().upper()
        t = self.trades.get(sym)
        if t is None:
            raise MarketDataError(f"No trade for {sym}", code=TRADE_UNAVAILABLE)
        return t

    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
        limit: int | None = None,
    ) -> list[Bar]:
        _ = (timeframe, start, end, limit)
        self._check_fail(asset_class)
        return list(self.bars.get(symbol.strip().upper(), []))

    def _check_fail(self, asset_class: MarketDataAssetClass) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        if asset_class in {
            MarketDataAssetClass.FUTURES,
            MarketDataAssetClass.OPTION,
        }:
            raise MarketDataError(
                f"Unsupported asset class {asset_class}",
                code=UNSUPPORTED_ASSET_CLASS,
            )

    def simulate_rate_limit(self) -> None:
        self.fail_with = MarketDataError("rate limited", code=RATE_LIMITED)

    def simulate_auth_failure(self) -> None:
        self.fail_with = MarketDataError("auth failed", code=AUTHENTICATION_FAILED)
