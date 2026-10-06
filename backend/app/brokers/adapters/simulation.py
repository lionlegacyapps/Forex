"""In-process SimulationBroker — ZERO external network calls.

Uses SimulationMarketData for quotes/fills. Never fabricates prices.
SIMULATION RESULTS DO NOT REPRESENT REAL MARKET EXECUTION.
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
from app.trading.execution.cash_ledger import SimulatedCashLedger, default_cash_ledger
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data

SIMULATION_PROVIDER = "simulation"
UNSUPPORTED = "SIMULATION_CAPABILITY_UNAVAILABLE"
PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"


class SimulationBroker(BrokerAdapter):
    """Deterministic paper simulation adapter."""

    def __init__(
        self,
        *,
        account_ref: str | None = None,
        market_data: SimulationMarketData | None = None,
        cash_ledger: SimulatedCashLedger | None = None,
        account_id: uuid.UUID | None = None,
        starting_cash: Decimal = Decimal("100000"),
    ) -> None:
        self._account_ref = account_ref or "sim-account"
        self._orders: dict[str, Order] = {}
        self._market = market_data or default_simulation_market_data
        self._cash = cash_ledger or default_cash_ledger
        self._account_id = account_id
        self._starting_cash = starting_cash
        if account_id is not None:
            self._cash.ensure_account(account_id, starting_cash=starting_cash)

    @property
    def provider_name(self) -> str:
        return SIMULATION_PROVIDER

    @property
    def market_data(self) -> SimulationMarketData:
        return self._market

    async def place_order(self, request: OrderRequest) -> Order:
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
                "note": "Accepted by simulation; durable fill handled by PaperExecutionService",
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
        if self._account_id is None:
            cash = self._starting_cash
        else:
            cash = self._cash.get_cash(self._account_id)
        return Balance(
            cash=cash,
            equity=cash,
            currency="USD",
            raw={"simulated": True, "model": "cash_equals_equity_v1"},
        )

    async def get_buying_power(self) -> BuyingPower:
        if self._account_id is None:
            bp = self._starting_cash
        else:
            bp = self._cash.get_buying_power(self._account_id)
        return BuyingPower(
            buying_power=bp,
            currency="USD",
            raw={"simulated": True, "model": "buying_power_equals_cash_v1"},
        )

    async def get_quote(self, symbol: str) -> Quote:
        price = self._market.get_price(symbol)
        if price is None:
            return Quote(
                symbol=symbol,
                bid=None,
                ask=None,
                last=None,
                timestamp=None,
                raw={"available": False, "reason": PRICE_UNAVAILABLE, "simulated": True},
            )
        return Quote(
            symbol=symbol,
            bid=price,
            ask=price,
            last=price,
            timestamp=datetime.now(UTC),
            raw={"available": True, "simulated": True, "source": "SimulationMarketData"},
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
