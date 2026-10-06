"""Simulation MarketDataProvider — wraps SimulationMarketData (offline)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.errors import PRICE_UNAVAILABLE, QUOTE_UNAVAILABLE, TRADE_UNAVAILABLE, MarketDataError
from app.market_data.models import Bar, MarketDataAssetClass, Quote, Trade
from app.market_data.provider import MarketDataProvider
from app.trading.execution.market_data import SimulationMarketData


class SimulationMarketDataProvider(MarketDataProvider):
    """Exposes SimulationMarketData through the MarketDataProvider interface.

    Quotes/trades are synthesized from the configured board price with
    identical bid/ask = last = board price and ``now`` timestamps.
    """

    def __init__(self, board: SimulationMarketData | None = None) -> None:
        from app.trading.execution.market_data import default_simulation_market_data

        self._board = board or default_simulation_market_data

    @property
    def provider_name(self) -> str:
        return "simulation"

    @property
    def board(self) -> SimulationMarketData:
        return self._board

    def _require(self, symbol: str) -> Decimal:
        price = self._board.get_price(symbol)
        if price is None:
            raise MarketDataError(
                f"Simulation price unavailable for {symbol}",
                code=PRICE_UNAVAILABLE,
            )
        return price

    async def get_quote(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Quote:
        if asset_class not in {MarketDataAssetClass.EQUITY, MarketDataAssetClass.OTHER}:
            # Simulation board is asset-agnostic; still allow equity/other.
            pass
        try:
            price = self._require(symbol)
        except MarketDataError as exc:
            raise MarketDataError(exc.message, code=QUOTE_UNAVAILABLE) from exc
        now = datetime.now(UTC)
        return Quote(
            symbol=symbol.strip().upper(),
            bid_price=price,
            ask_price=price,
            bid_size=None,
            ask_size=None,
            timestamp=now,
            provider=self.provider_name,
            asset_class=asset_class,
            raw={"simulated": True, "source": "SimulationMarketData"},
        )

    async def get_latest_trade(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Trade:
        try:
            price = self._require(symbol)
        except MarketDataError as exc:
            raise MarketDataError(exc.message, code=TRADE_UNAVAILABLE) from exc
        return Trade(
            symbol=symbol.strip().upper(),
            price=price,
            size=None,
            timestamp=datetime.now(UTC),
            provider=self.provider_name,
            asset_class=asset_class,
            raw={"simulated": True},
        )

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
        _ = (start, end, limit)
        price = self._require(symbol)
        return [
            Bar(
                symbol=symbol.strip().upper(),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=None,
                timestamp=datetime.now(UTC),
                timeframe=timeframe,
                provider=self.provider_name,
                asset_class=asset_class,
                raw={"simulated": True},
            )
        ]
