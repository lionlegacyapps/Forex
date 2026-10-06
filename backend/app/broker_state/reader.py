"""BrokerAccountReader — READ ONLY account/position/order state.

Separate from:
  - MarketDataProvider (quotes/trades/bars)
  - BrokerAdapter / future BrokerExecutionAdapter (order mutation)

CONNECTING AN ALPACA ACCOUNT DOES NOT AUTHORIZE TRADING.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.broker_state.models import (
    AccountSnapshot,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
)


class BrokerAccountReader(ABC):
    """Provider-agnostic read-only broker account interface.

    Implementations must NEVER expose place_order / cancel_order / modify_order
    or any other mutating trading operation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable broker slug (e.g. 'alpaca')."""

    @abstractmethod
    async def get_account(self) -> AccountSnapshot:
        """Return a verified account snapshot."""

    @abstractmethod
    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        """Return open positions at the broker."""

    @abstractmethod
    async def get_orders(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[BrokerOrderSnapshot]:
        """Return orders (open and/or historical depending on ``status``)."""

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> BrokerOrderSnapshot:
        """Return a single order by broker id."""

    async def get_open_orders(self, *, limit: int | None = None) -> list[BrokerOrderSnapshot]:
        """Convenience: open orders only."""
        return await self.get_orders(status="open", limit=limit)

    async def get_trade_activity(
        self,
        *,
        limit: int | None = None,
    ) -> list[BrokerFillSnapshot]:
        """Optional fill/activity history. Default: empty list."""
        return []

    async def get_cash(self) -> Decimal:
        snap = await self.get_account()
        return snap.cash

    async def get_buying_power(self) -> Decimal:
        snap = await self.get_account()
        if snap.buying_power is None:
            return Decimal("0")
        return snap.buying_power

    async def get_balance(self) -> AccountSnapshot:
        """Alias for get_account (cash/equity/buying power)."""
        return await self.get_account()
