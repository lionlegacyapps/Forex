"""Fake execution adapter for offline tests (submit + lifecycle helpers)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.errors import (
    BROKER_ACCOUNT_DISABLED,
    BROKER_UNAVAILABLE,
    INSUFFICIENT_BROKER_BUYING_POWER,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    ORDER_REJECTED_BY_BROKER,
    PIPELINE_PRECONDITION_FAILED,
    UNSUPPORTED_ASSET_CLASS,
    ExecutionAdapterError,
)
from app.brokers.execution.types import ExecutionResult, ExecutionSubmission


class FakeExecutionAdapter(BrokerExecutionAdapter):
    """In-memory submit with idempotent client_order_id + lifecycle stubs."""

    def __init__(
        self,
        *,
        provider: str = "alpaca",
        buying_power: Decimal = Decimal("1000000"),
        fail_code: str | None = None,
        timeout_after_accept: bool = False,
    ) -> None:
        self._provider = provider
        self.buying_power = buying_power
        self.fail_code = fail_code
        self.timeout_after_accept = timeout_after_accept
        self.orders_by_client: dict[str, ExecutionResult] = {}
        self.broker_orders: dict[str, dict[str, Any]] = {}
        self.fills_by_order: dict[str, list[dict[str, Any]]] = {}
        self.post_count = 0
        self.cancel_count = 0
        self.cancel_should_fail_code: str | None = None
        self.get_order_should_fail: bool = False
        self.malformed_get: bool = False
        # When cancel is called, optionally flip status to filled (race)
        self.cancel_race_fill: bool = False

    @property
    def provider_name(self) -> str:
        return self._provider

    async def submit_order(self, submission: ExecutionSubmission) -> ExecutionResult:
        if not (submission.risk_approved and submission.validated and submission.routed):
            raise ExecutionAdapterError("pipeline", code=PIPELINE_PRECONDITION_FAILED)
        if submission.proposal_status != "routed":
            raise ExecutionAdapterError("status", code=PIPELINE_PRECONDITION_FAILED)
        if submission.trading_mode != "paper":
            raise ExecutionAdapterError("live", code=LIVE_BROKER_ACCESS_FORBIDDEN)
        if not submission.account_enabled:
            raise ExecutionAdapterError("disabled", code=BROKER_ACCOUNT_DISABLED)
        if submission.asset_class != "equity":
            raise ExecutionAdapterError("asset", code=UNSUPPORTED_ASSET_CLASS)
        if self.fail_code:
            raise ExecutionAdapterError("forced", code=self.fail_code)

        existing = self.orders_by_client.get(submission.client_order_id)
        if existing is not None:
            return existing.model_copy(update={"recovered_existing": True, "submit_http_calls": 0})

        if submission.side == "buy" and submission.limit_price is not None:
            need = submission.quantity * submission.limit_price
            if need > self.buying_power:
                raise ExecutionAdapterError("bp", code=INSUFFICIENT_BROKER_BUYING_POWER)

        self.post_count += 1
        broker_id = f"fake-{submission.client_order_id}"
        result = ExecutionResult(
            broker_order_id=broker_id,
            client_order_id=submission.client_order_id,
            status="accepted",
            submitted_at=datetime.now(UTC),
            filled_quantity=Decimal("0"),
            recovered_existing=False,
            submit_http_calls=1,
        )
        self.orders_by_client[submission.client_order_id] = result
        self.broker_orders[broker_id] = {
            "id": broker_id,
            "client_order_id": submission.client_order_id,
            "status": "accepted",
            "symbol": submission.symbol,
            "side": submission.side,
            "type": submission.order_type,
            "qty": str(submission.quantity),
            "filled_qty": "0",
            "filled_avg_price": None,
            "limit_price": str(submission.limit_price) if submission.limit_price else None,
            "time_in_force": submission.time_in_force,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
        self.fills_by_order.setdefault(broker_id, [])

        if self.timeout_after_accept:
            from app.brokers.execution.errors import NETWORK_TIMEOUT

            raise ExecutionAdapterError("timeout after accept", code=NETWORK_TIMEOUT)

        return result

    def set_broker_status(self, broker_order_id: str, status: str, **fields: Any) -> None:
        row = self.broker_orders.setdefault(broker_order_id, {"id": broker_order_id})
        row["status"] = status
        row.update(fields)

    def add_fill(
        self,
        broker_order_id: str,
        *,
        fill_id: str,
        qty: Decimal,
        price: Decimal,
    ) -> None:
        fills = self.fills_by_order.setdefault(broker_order_id, [])
        fills.append(
            {
                "id": fill_id,
                "order_id": broker_order_id,
                "qty": str(qty),
                "price": str(price),
                "activity_type": "FILL",
                "transaction_time": datetime.now(UTC).isoformat(),
            }
        )
        row = self.broker_orders.setdefault(broker_order_id, {"id": broker_order_id})
        prev = Decimal(str(row.get("filled_qty") or "0"))
        new_qty = prev + qty
        row["filled_qty"] = str(new_qty)
        row["filled_avg_price"] = str(price)
        if "qty" in row and new_qty >= Decimal(str(row["qty"])):
            row["status"] = "filled"
        else:
            row["status"] = "partially_filled"

    async def get_order_by_id(self, broker_order_id: str) -> dict[str, Any]:
        if self.get_order_should_fail:
            raise ExecutionAdapterError("down", code=BROKER_UNAVAILABLE)
        if self.malformed_get:
            return "not-a-dict"  # type: ignore[return-value]
        if broker_order_id not in self.broker_orders:
            raise ExecutionAdapterError("missing", code=BROKER_UNAVAILABLE)
        return dict(self.broker_orders[broker_order_id])

    async def get_order_by_client_order_id(
        self, client_order_id: str
    ) -> dict[str, Any] | None:
        """Fallback lookup used after uncertain acknowledgments."""
        existing = self.orders_by_client.get(client_order_id)
        if existing is None:
            return None
        return dict(self.broker_orders.get(existing.broker_order_id) or {})

    async def get_fills_for_order(self, broker_order_id: str) -> list[dict[str, Any]]:
        return list(self.fills_by_order.get(broker_order_id, []))

    async def request_paper_cancel(self, broker_order_id: str) -> dict[str, Any]:
        self.cancel_count += 1
        if self.cancel_race_fill:
            row = self.broker_orders.get(broker_order_id) or {"id": broker_order_id, "qty": "1"}
            qty = Decimal(str(row.get("qty") or "1"))
            price = Decimal(str(row.get("limit_price") or "10"))
            self.add_fill(broker_order_id, fill_id=f"race-fill-{broker_order_id}", qty=qty, price=price)
            row["status"] = "filled"
            row["filled_qty"] = str(qty)
            raise ExecutionAdapterError("already filled", code=ORDER_REJECTED_BY_BROKER)
        if self.cancel_should_fail_code:
            raise ExecutionAdapterError("cancel fail", code=self.cancel_should_fail_code)
        row = self.broker_orders.get(broker_order_id)
        if row is None:
            raise ExecutionAdapterError("missing", code=ORDER_REJECTED_BY_BROKER)
        row["status"] = "canceled"
        row["canceled_at"] = datetime.now(UTC).isoformat()
        return dict(row)
