"""Abstract broker adapter contract.

Strategies, AI models, and external signals must never call a broker
directly. All live order flow must go through:

    Trade Proposal → Risk Engine → Order Validator → Broker Router → Broker Adapter
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.brokers.base.types import (
    Balance,
    Bar,
    BuyingPower,
    ModifyOrderRequest,
    Order,
    OrderRequest,
    Position,
    Quote,
    Trade,
)


class BrokerAdapter(ABC):
    """Provider-agnostic broker interface.

    Concrete adapters (Alpaca, Tradovate, Interactive Brokers, etc.) will
    live under ``app.brokers.adapters`` and implement this contract.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier for the broker provider (e.g. 'alpaca')."""

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> Order:
        """Submit a new order."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Order:
        """Cancel an existing order by broker order id."""

    @abstractmethod
    async def modify_order(self, order_id: str, request: ModifyOrderRequest) -> Order:
        """Modify an existing open order."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return open positions for the bound account."""

    @abstractmethod
    async def get_orders(self, *, status: str | None = None) -> list[Order]:
        """Return orders, optionally filtered by status."""

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Return account cash / equity balances."""

    @abstractmethod
    async def get_buying_power(self) -> BuyingPower:
        """Return current buying power."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Return a current quote for ``symbol``."""

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """Return historical OHLCV bars."""

    @abstractmethod
    async def get_trades(self, *, symbol: str | None = None) -> list[Trade]:
        """Return recent fills / trades for the bound account."""
