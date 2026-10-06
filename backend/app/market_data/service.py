"""MarketDataService — provider-independent access with freshness + reference price.

Consumers (Risk Engine, Exposure) should use this service, not Alpaca directly.
Does not expose any order-execution methods.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal

from app.market_data.errors import (
    PRICE_UNAVAILABLE,
    PROVIDER_UNAVAILABLE,
    QUOTE_UNAVAILABLE,
    TRADE_UNAVAILABLE,
    MarketDataError,
)
from app.market_data.freshness import assert_fresh
from app.market_data.models import Bar, MarketDataAssetClass, Quote, ReferencePrice, Trade
from app.market_data.provider import MarketDataProvider
from app.market_data.reference import resolve_reference_price

logger = logging.getLogger(__name__)


class MarketDataService:
    """Normalize symbols, enforce freshness, resolve reference prices."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        quote_max_age_seconds: int = 30,
        trade_max_age_seconds: int = 60,
        enforce_freshness: bool = True,
    ) -> None:
        self._provider = provider
        self._quote_max_age = quote_max_age_seconds
        self._trade_max_age = trade_max_age_seconds
        self._enforce_freshness = enforce_freshness

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def provider(self) -> MarketDataProvider:
        return self._provider

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    async def get_quote(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
        enforce_freshness: bool | None = None,
    ) -> Quote:
        sym = self.normalize_symbol(symbol)
        started = time.perf_counter()
        try:
            quote = await self._provider.get_quote(sym, asset_class=asset_class)
            if enforce_freshness if enforce_freshness is not None else self._enforce_freshness:
                assert_fresh(quote.timestamp, max_age_seconds=self._quote_max_age, kind="quote")
            logger.info(
                "market_data_quote_ok",
                extra={
                    "provider": self.provider_name,
                    "symbol": sym,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return quote
        except MarketDataError as exc:
            logger.info(
                "market_data_quote_fail",
                extra={
                    "provider": self.provider_name,
                    "symbol": sym,
                    "code": exc.code,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise

    async def get_latest_trade(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
        enforce_freshness: bool | None = None,
    ) -> Trade:
        sym = self.normalize_symbol(symbol)
        trade = await self._provider.get_latest_trade(sym, asset_class=asset_class)
        if enforce_freshness if enforce_freshness is not None else self._enforce_freshness:
            assert_fresh(trade.timestamp, max_age_seconds=self._trade_max_age, kind="trade")
        return trade

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
        sym = self.normalize_symbol(symbol)
        return await self._provider.get_bars(
            sym,
            timeframe=timeframe,
            start=start,
            end=end,
            asset_class=asset_class,
            limit=limit,
        )

    async def get_reference_price(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
        enforce_freshness: bool | None = None,
    ) -> ReferencePrice:
        """Bid/ask midpoint, else last trade. Raises MarketDataError on failure."""
        sym = self.normalize_symbol(symbol)
        quote: Quote | None = None
        trade: Trade | None = None
        quote_error: MarketDataError | None = None
        trade_error: MarketDataError | None = None

        try:
            quote = await self.get_quote(
                sym, asset_class=asset_class, enforce_freshness=enforce_freshness
            )
        except MarketDataError as exc:
            quote_error = exc

        try:
            trade = await self.get_latest_trade(
                sym, asset_class=asset_class, enforce_freshness=enforce_freshness
            )
        except MarketDataError as exc:
            trade_error = exc

        try:
            return resolve_reference_price(
                symbol=sym,
                quote=quote,
                trade=trade,
                provider=self.provider_name,
            )
        except MarketDataError:
            # Prefer the most specific upstream code.
            if quote_error and quote_error.code not in {QUOTE_UNAVAILABLE, PRICE_UNAVAILABLE}:
                raise quote_error
            if trade_error and trade_error.code not in {TRADE_UNAVAILABLE, PRICE_UNAVAILABLE}:
                raise trade_error
            raise MarketDataError(
                f"Reference price unavailable for {sym}",
                code=PRICE_UNAVAILABLE,
            )

    def sync_reference_price(
        self,
        symbol: str,
        *,
        enforce_freshness: bool | None = None,
    ) -> ReferencePrice:
        """Synchronous reference price for in-memory providers (simulation/fake).

        Used by Risk Engine / Exposure on the sync evaluation path.
        Alpaca (network) must use ``await get_reference_price`` instead.
        """
        from app.market_data.providers.fake import FakeMarketDataProvider
        from app.market_data.providers.simulation import SimulationMarketDataProvider

        sym = self.normalize_symbol(symbol)
        enforce = self._enforce_freshness if enforce_freshness is None else enforce_freshness
        provider = self._provider

        quote: Quote | None = None
        trade: Trade | None = None

        if isinstance(provider, SimulationMarketDataProvider):
            price = provider.board.get_price(sym)
            if price is None:
                raise MarketDataError(
                    f"Simulation price unavailable for {sym}",
                    code=PRICE_UNAVAILABLE,
                )
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            quote = Quote(
                symbol=sym,
                bid_price=price,
                ask_price=price,
                timestamp=now,
                provider=provider.provider_name,
            )
            trade = Trade(
                symbol=sym,
                price=price,
                timestamp=now,
                provider=provider.provider_name,
            )
        elif isinstance(provider, FakeMarketDataProvider):
            quote = provider.quotes.get(sym)
            trade = provider.trades.get(sym)
            if quote is None and trade is None:
                raise MarketDataError(
                    f"No fake market data for {sym}",
                    code=PRICE_UNAVAILABLE,
                )
            if enforce:
                if quote is not None:
                    assert_fresh(
                        quote.timestamp,
                        max_age_seconds=self._quote_max_age,
                        kind="quote",
                    )
                elif trade is not None:
                    assert_fresh(
                        trade.timestamp,
                        max_age_seconds=self._trade_max_age,
                        kind="trade",
                    )
        else:
            raise MarketDataError(
                "sync_reference_price supports simulation/fake providers only",
                code=PROVIDER_UNAVAILABLE,
            )

        return resolve_reference_price(
            symbol=sym,
            quote=quote,
            trade=trade,
            provider=self.provider_name,
        )

    def get_price_sync_compatible(self, symbol: str) -> Decimal | None:
        """Legacy SimulationMarketData-style helper; None when unavailable."""
        try:
            return self.sync_reference_price(symbol, enforce_freshness=False).price
        except MarketDataError:
            return None
