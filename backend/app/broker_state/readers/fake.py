"""Fake broker account reader for offline deterministic tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.broker_state.errors import (
    AUTHENTICATION_FAILED,
    ORDER_NOT_FOUND,
    RATE_LIMITED,
    BrokerStateError,
)
from app.broker_state.models import (
    AccountSnapshot,
    BrokerFillSnapshot,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
)
from app.broker_state.reader import BrokerAccountReader


class FakeBrokerAccountReader(BrokerAccountReader):
    """In-memory reader for unit tests (no network)."""

    def __init__(
        self,
        *,
        account: AccountSnapshot | None = None,
        positions: list[BrokerPositionSnapshot] | None = None,
        orders: list[BrokerOrderSnapshot] | None = None,
        fills: list[BrokerFillSnapshot] | None = None,
        fail_auth: bool = False,
        fail_rate_limit: bool = False,
        provider: str = "fake",
    ) -> None:
        self._provider = provider
        self._fail_auth = fail_auth
        self._fail_rate_limit = fail_rate_limit
        self.account = account or AccountSnapshot(
            broker=provider,
            external_account_id="fake-acct-1",
            account_status="ACTIVE",
            currency="USD",
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            timestamp=datetime.now(UTC),
            paper_verified=True,
        )
        self.positions = list(positions or [])
        self.orders = list(orders or [])
        self.fills = list(fills or [])
        self.mutations = 0  # Observability for tests — never incremented by reads

    @property
    def provider_name(self) -> str:
        return self._provider

    def _guard(self) -> None:
        if self._fail_auth:
            raise BrokerStateError("auth failed", code=AUTHENTICATION_FAILED)
        if self._fail_rate_limit:
            raise BrokerStateError("rate limited", code=RATE_LIMITED)

    async def get_account(self) -> AccountSnapshot:
        self._guard()
        return self.account

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        self._guard()
        return list(self.positions)

    async def get_orders(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[BrokerOrderSnapshot]:
        self._guard()
        rows = list(self.orders)
        if status == "open":
            open_statuses = {"new", "submitted", "accepted", "partially_filled", "open", "pending_new"}
            rows = [o for o in rows if o.status in open_statuses]
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def get_order(self, broker_order_id: str) -> BrokerOrderSnapshot:
        self._guard()
        for order in self.orders:
            if order.broker_order_id == broker_order_id:
                return order
        raise BrokerStateError("order not found", code=ORDER_NOT_FOUND)

    async def get_trade_activity(
        self,
        *,
        limit: int | None = None,
    ) -> list[BrokerFillSnapshot]:
        self._guard()
        rows = list(self.fills)
        if limit is not None:
            rows = rows[:limit]
        return rows
