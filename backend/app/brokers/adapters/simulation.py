"""In-process SimulationBroker — ZERO external network calls.

Accepts PAPER orders only. Does not fabricate fills or market prices.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.brokers.base.broker import BrokerAdapter
from app.brokers.base.types import (
    Balance,
    Bar,
    BuyingPower,
    ModifyOrderRequest,
    Order,
    OrderRequest,
    OrderStatus,
    Position,
    Quote,
    Trade,
)
from app.core.exceptions import BrokerError

SIMULATION_PROVIDER = "simulation"
UNSUPPORTED = "SIMULATION_CAPABILITY_UNAVAILABLE"


class SimulationBroker(BrokerAdapter):
    """Deterministic paper simulation adapter.

    Network policy: this class must never import or call HTTP clients,
    sockets, or broker SDKs. All state is in-process memory.
    """

    def __init__(self, *, account_ref: str | None = None) -> None:
        self._account_ref = account_ref or "sim-account"
        self._orders: dict[str, Order] = {}
        self._cash = Decimal("0")

    @property
    def provider_name(self) -> str:
        return SIMULATION_PROVIDER

    async def place_order(self, request: OrderRequest) -> Order:
        # Refuse any hint of live intent in metadata.
        mode = (request.metadata or {}).get("trading_mode", "paper")
        if str(mode).lower() != "paper":
            raise BrokerError(
                "SimulationBroker accepts PAPER orders only",
                code="LIVE_TRADING_NOT_ALLOWED",
            )

        broker_order_id = f"sim_{uuid.uuid4()}"
        now = datetime.now(UTC)
        order = Order(
            id=broker_order_id,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled_quantity=Decimal("0"),
            order_type=request.order_type,
            status=OrderStatus.SUBMITTED,
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            average_fill_price=None,
            created_at=now,
            updated_at=now,
            raw={
                "provider": SIMULATION_PROVIDER,
                "simulated": True,
                "fill": None,
                "note": "Accepted; not auto-filled without deterministic pricing",
            },
        )
        self._orders[broker_order_id] = order
        return order

    async def cancel_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise BrokerError(f"Unknown simulation order {order_id}", code="ORDER_NOT_FOUND")
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        return order

    async def modify_order(self, order_id: str, request: ModifyOrderRequest) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise BrokerError(f"Unknown simulation order {order_id}", code="ORDER_NOT_FOUND")
        if request.quantity is not None:
            order.quantity = request.quantity
        if request.limit_price is not None:
            order.limit_price = request.limit_price
        if request.stop_price is not None:
            order.stop_price = request.stop_price
        order.updated_at = datetime.now(UTC)
        return order

    async def get_positions(self) -> list[Position]:
        return []

    async def get_orders(self, *, status: str | None = None) -> list[Order]:
        orders = list(self._orders.values())
        if status is None:
            return orders
        return [o for o in orders if o.status.value == status]

    async def get_balance(self) -> Balance:
        return Balance(
            cash=self._cash,
            equity=self._cash,
            currency="USD",
            raw={"simulated": True, "note": "No external balance feed"},
        )

    async def get_buying_power(self) -> BuyingPower:
        return BuyingPower(
            buying_power=self._cash,
            currency="USD",
            raw={"simulated": True, "note": "No external buying-power feed"},
        )

    async def get_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            bid=None,
            ask=None,
            last=None,
            timestamp=None,
            raw={"available": False, "reason": UNSUPPORTED},
        )

    async def get_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        _ = (symbol, timeframe, start, end, limit)
        return []

    async def get_trades(self, *, symbol: str | None = None) -> list[Trade]:
        _ = symbol
        return []
