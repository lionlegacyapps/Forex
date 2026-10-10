"""MarketDataProvider abstraction — separate from BrokerAdapter.

ALPACA MARKET DATA ACCESS DOES NOT ENABLE ALPACA ORDER EXECUTION.
Providers must never expose place_order / cancel_order / modify_order.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.market_data.models import Bar, MarketDataAssetClass, Quote, Trade


class MarketDataProvider(ABC):
    """Read-only market data contract."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider id (e.g. 'simulation', 'alpaca')."""

    @abstractmethod
    async def get_quote(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Quote:
        ...

    @abstractmethod
    async def get_latest_trade(
        self,
        symbol: str,
        *,
        asset_class: MarketDataAssetClass = MarketDataAssetClass.EQUITY,
    ) -> Trade:
        ...

    @abstractmethod
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
        ...
