"""Fake execution adapter for offline tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.errors import (
    BROKER_ACCOUNT_DISABLED,
    INSUFFICIENT_BROKER_BUYING_POWER,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    PIPELINE_PRECONDITION_FAILED,
    UNSUPPORTED_ASSET_CLASS,
    ExecutionAdapterError,
)
from app.brokers.execution.types import ExecutionResult, ExecutionSubmission


class FakeExecutionAdapter(BrokerExecutionAdapter):
    """In-memory submit with idempotent client_order_id behavior."""

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
        self.post_count = 0

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

        # Buying power for buys with limit
        if submission.side == "buy" and submission.limit_price is not None:
            need = submission.quantity * submission.limit_price
            if need > self.buying_power:
                raise ExecutionAdapterError("bp", code=INSUFFICIENT_BROKER_BUYING_POWER)

        self.post_count += 1
        result = ExecutionResult(
            broker_order_id=f"fake-{submission.client_order_id}",
            client_order_id=submission.client_order_id,
            status="accepted",
            submitted_at=datetime.now(UTC),
            filled_quantity=Decimal("0"),
            recovered_existing=False,
            submit_http_calls=1,
        )
        self.orders_by_client[submission.client_order_id] = result

        if self.timeout_after_accept:
            # Simulate lost response — caller should recover via second submit
            from app.brokers.execution.errors import NETWORK_TIMEOUT

            raise ExecutionAdapterError("timeout after accept", code=NETWORK_TIMEOUT)

        return result
