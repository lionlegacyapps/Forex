"""Controlled PAPER order cancellation — exact order only.

No cancel_all_orders. No liquidation. No public HTTP endpoint.
Cancellation validates ownership + paper mode before broker DELETE.

ALL EXTERNAL EXECUTION REMAINS ALPACA PAPER ONLY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.brokers.execution.errors import (
    LIVE_BROKER_ACCESS_FORBIDDEN,
    ExecutionAdapterError,
)
from app.brokers.execution.order_status_sync import OrderStatusSyncService, SyncResult
from app.brokers.execution.status_map import is_cancellable_status, is_terminal_status, map_alpaca_order_status
from app.models.broker_account import BrokerAccount
from app.models.enums import OrderStatus, TradingMode
from app.models.order import Order


class CancelCapableBroker(Protocol):
    async def get_order_by_id(self, broker_order_id: str) -> dict[str, Any]: ...

    async def get_fills_for_order(self, broker_order_id: str) -> list[dict[str, Any]]: ...

    async def request_paper_cancel(self, broker_order_id: str) -> dict[str, Any]: ...


@dataclass
class CancellationRequest:
    """Trusted internal cancellation request (not a public API DTO)."""

    internal_order_id: UUID
    broker_order_id: str
    broker_account_id: UUID


@dataclass
class CancellationResult:
    ok: bool
    cancelled: bool = False
    filled_instead: bool = False
    order_id: UUID | None = None
    broker_order_id: str | None = None
    final_status: str | None = None
    reason_code: str | None = None
    message: str = ""
    sync: SyncResult | None = None
    details: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ControlledCancellationService:
    """Cancel one specific paper order after ownership + state checks."""

    def __init__(
        self,
        session: Session,
        *,
        broker: CancelCapableBroker,
        sync: OrderStatusSyncService | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._session = session
        self._broker = broker
        self._audit = audit or AuditService(session)
        self._sync = sync or OrderStatusSyncService(session, broker=broker, audit=self._audit)

    async def cancel(self, request: CancellationRequest) -> CancellationResult:
        order = self._session.get(Order, request.internal_order_id)
        if order is None:
            return CancellationResult(
                ok=False,
                reason_code="ORDER_NOT_FOUND",
                message="Internal order not found",
            )
        if order.broker_account_id != request.broker_account_id:
            return CancellationResult(
                ok=False,
                order_id=order.id,
                reason_code="ORDER_ACCOUNT_MISMATCH",
                message="Order does not belong to expected broker account",
            )
        if not order.broker_order_id or order.broker_order_id != request.broker_order_id:
            return CancellationResult(
                ok=False,
                order_id=order.id,
                reason_code="BROKER_ORDER_ID_MISMATCH",
                message="broker_order_id does not match internal order",
            )

        account = self._session.get(BrokerAccount, order.broker_account_id)
        if account is None:
            return CancellationResult(
                ok=False,
                order_id=order.id,
                reason_code="BROKER_ACCOUNT_NOT_FOUND",
                message="Broker account missing",
            )
        if account.broker.lower().strip() != "alpaca":
            return CancellationResult(
                ok=False,
                order_id=order.id,
                reason_code="UNSUPPORTED_BROKER",
                message="Controlled cancel supports alpaca paper only",
            )
        if account.trading_mode != TradingMode.PAPER:
            return CancellationResult(
                ok=False,
                order_id=order.id,
                reason_code=LIVE_BROKER_ACCESS_FORBIDDEN,
                message="Cancellation is paper-only",
            )

        # Sync first — broker may already be terminal (fill race)
        pre = await self._sync.sync_order(order)
        self._session.refresh(order)
        if is_terminal_status(order.status):
            if order.status == OrderStatus.FILLED:
                return CancellationResult(
                    ok=True,
                    cancelled=False,
                    filled_instead=True,
                    order_id=order.id,
                    broker_order_id=order.broker_order_id,
                    final_status=order.status.value,
                    message="Order already filled — cancel not applied",
                    sync=pre,
                )
            return CancellationResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                final_status=order.status.value,
                reason_code="ORDER_NOT_CANCELLABLE",
                message=f"Order already terminal ({order.status.value})",
                sync=pre,
            )

        if not is_cancellable_status(order.status):
            return CancellationResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                final_status=order.status.value,
                reason_code="ORDER_NOT_CANCELLABLE",
                message=f"Order status {order.status.value} is not cancellable",
                sync=pre,
            )

        self._audit.record(
            event_type=audit_events.ALPACA_ORDER_CANCEL_REQUESTED,
            entity_type="order",
            entity_id=order.id,
            details={
                "broker_order_id": order.broker_order_id,
                "broker_account_id": str(order.broker_account_id),
            },
        )

        try:
            cancel_payload = await self._broker.request_paper_cancel(order.broker_order_id)
        except ExecutionAdapterError as exc:
            # Race: filled while cancelling — sync authoritative broker state
            post = await self._sync.sync_order(order)
            self._session.refresh(order)
            if order.status == OrderStatus.FILLED:
                return CancellationResult(
                    ok=True,
                    cancelled=False,
                    filled_instead=True,
                    order_id=order.id,
                    broker_order_id=order.broker_order_id,
                    final_status=order.status.value,
                    message="Cancel raced with fill — order filled",
                    sync=post,
                    details={"cancel_error": exc.code},
                )
            self._audit.record(
                event_type=audit_events.ALPACA_ORDER_CANCEL_FAILED,
                entity_type="order",
                entity_id=order.id,
                details={"code": exc.code, "message": exc.message},
            )
            return CancellationResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                final_status=order.status.value,
                reason_code=exc.code,
                message=exc.message,
                sync=post,
            )

        # Sync after cancel request — broker is authoritative
        post = await self._sync.sync_order(order)
        self._session.refresh(order)
        if order.status == OrderStatus.FILLED:
            return CancellationResult(
                ok=True,
                cancelled=False,
                filled_instead=True,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                final_status=order.status.value,
                message="Broker reported filled after cancel request",
                sync=post,
                details={"cancel_response_status": str((cancel_payload or {}).get("status") or "")},
            )
        if order.status == OrderStatus.CANCELLED:
            return CancellationResult(
                ok=True,
                cancelled=True,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                final_status=order.status.value,
                message="Order cancelled",
                sync=post,
            )

        # Pending cancel or unexpected — report current broker-mapped state
        raw = str((cancel_payload or {}).get("status") or "")
        return CancellationResult(
            ok=post.ok,
            cancelled=False,
            order_id=order.id,
            broker_order_id=order.broker_order_id,
            final_status=order.status.value,
            reason_code="CANCEL_PENDING" if map_alpaca_order_status(raw) else "CANCEL_INCOMPLETE",
            message="Cancel requested; broker has not reached cancelled yet",
            sync=post,
            details={"raw_status": raw},
        )
