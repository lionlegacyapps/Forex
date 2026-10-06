"""OrderStatusSyncService — fetch, normalize, sync fills, poll to terminal.

Does not place new orders. Broker state is authoritative.
ALL EXTERNAL EXECUTION REMAINS ALPACA PAPER ONLY.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.broker_state.models import BrokerOrderSnapshot, ReconciliationReport
from app.broker_state.reconciliation import ReconciliationEngine
from app.brokers.execution.errors import (
    BROKER_UNAVAILABLE,
    MALFORMED_RESPONSE,
    ExecutionAdapterError,
)
from app.brokers.execution.fill_sync import AlpacaFillSyncService
from app.brokers.execution.status_map import is_terminal_status, map_alpaca_order_status
from app.models.broker_account import BrokerAccount
from app.models.enums import TradingMode
from app.models.order import Order


class OrderLifecycleBroker(Protocol):
    """Minimal broker surface for lifecycle sync (paper execution adapter)."""

    async def get_order_by_id(self, broker_order_id: str) -> dict[str, Any]: ...

    async def get_fills_for_order(self, broker_order_id: str) -> list[dict[str, Any]]: ...


@dataclass
class SyncResult:
    ok: bool
    order_id: UUID
    broker_order_id: str | None
    mapped_status: str
    fills_recorded: int = 0
    status_changed: bool = False
    illegal_transition: bool = False
    terminal: bool = False
    error_code: str | None = None
    message: str = ""
    reconciliation: ReconciliationReport | None = None
    details: dict[str, Any] = field(default_factory=dict)
    synced_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class OrderStatusSyncService:
    """Synchronize one internal order with Alpaca paper broker state."""

    def __init__(
        self,
        session: Session,
        *,
        broker: OrderLifecycleBroker,
        fill_sync: AlpacaFillSyncService | None = None,
        audit: AuditService | None = None,
        reconcile: bool = True,
    ) -> None:
        self._session = session
        self._broker = broker
        self._audit = audit or AuditService(session)
        self._fill_sync = fill_sync or AlpacaFillSyncService(session, audit=self._audit)
        self._reconcile = reconcile

    async def sync_order(self, order: Order) -> SyncResult:
        if not order.broker_order_id:
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=None,
                mapped_status=order.status.value,
                error_code="MISSING_BROKER_ORDER_ID",
                message="Order has no broker_order_id",
            )

        account = self._session.get(BrokerAccount, order.broker_account_id)
        if account is None:
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code="BROKER_ACCOUNT_NOT_FOUND",
                message="Broker account missing",
            )
        if account.trading_mode != TradingMode.PAPER:
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code="LIVE_BROKER_ACCESS_FORBIDDEN",
                message="Lifecycle sync is paper-only",
            )

        prior_status = order.status
        try:
            payload = await self._broker.get_order_by_id(order.broker_order_id)
        except ExecutionAdapterError as exc:
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code=exc.code,
                message=exc.message,
            )
        except Exception as exc:  # noqa: BLE001
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code=BROKER_UNAVAILABLE,
                message=f"Sync failed: {type(exc).__name__}",
            )

        if not isinstance(payload, dict):
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code=MALFORMED_RESPONSE,
                message="Malformed broker order payload — state left unchanged",
            )

        fills: list[dict[str, Any]] | None = None
        try:
            fills = await self._broker.get_fills_for_order(order.broker_order_id)
        except Exception:
            fills = None

        applied = self._fill_sync.apply_broker_order_snapshot(
            order, payload, fills=fills or None
        )
        if not applied.get("ok", True) and applied.get("error"):
            return SyncResult(
                ok=False,
                order_id=order.id,
                broker_order_id=order.broker_order_id,
                mapped_status=order.status.value,
                error_code=str(applied.get("error")),
                message="Fill sync refused malformed payload — state left unchanged",
            )

        recon = None
        if self._reconcile:
            try:
                mapped = map_alpaca_order_status(str(payload.get("status") or ""))
                from decimal import Decimal

                filled = Decimal(str(payload.get("filled_qty") or "0"))
                snap = BrokerOrderSnapshot(
                    broker_order_id=order.broker_order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    order_type=order.order_type.value,
                    quantity=order.quantity,
                    filled_quantity=filled,
                    status=mapped.value,
                    limit_price=order.limit_price,
                )
                recon = ReconciliationEngine(self._session).reconcile(
                    broker_account_id=order.broker_account_id,
                    broker=account.broker,
                    external_account_id=account.external_account_id,
                    broker_positions=[],
                    broker_orders=[snap],
                )
                mismatches = [f for f in recon.findings if f.category.value != "MATCH"]
                if mismatches:
                    self._audit.record(
                        event_type=audit_events.ALPACA_RECONCILIATION_MISMATCH,
                        entity_type="order",
                        entity_id=order.id,
                        details={
                            "categories": [f.category.value for f in mismatches[:20]],
                            "count": len(mismatches),
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                applied["recon_error"] = type(exc).__name__

        return SyncResult(
            ok=True,
            order_id=order.id,
            broker_order_id=order.broker_order_id,
            mapped_status=order.status.value,
            fills_recorded=int(applied.get("fills_recorded") or 0),
            status_changed=bool(applied.get("status_changed")),
            illegal_transition=bool(applied.get("illegal_transition")),
            terminal=is_terminal_status(order.status),
            reconciliation=recon,
            details={
                "prior_status": prior_status.value,
                "raw_status": str(payload.get("status") or ""),
                **{k: v for k, v in applied.items() if k not in {"ok"}},
            },
        )

    async def poll_until_terminal(
        self,
        order: Order,
        *,
        interval_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
        max_iterations: int = 30,
    ) -> SyncResult:
        """Bounded polling — no infinite loops / busy waiting / retry storms."""
        if interval_seconds <= 0:
            interval_seconds = 0.5
        if timeout_seconds <= 0:
            timeout_seconds = 1.0
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        last = await self.sync_order(order)
        if last.terminal or not last.ok:
            return last
        iterations = 1
        while iterations < max_iterations:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval_seconds, remaining))
            # Refresh order from session
            self._session.refresh(order)
            last = await self.sync_order(order)
            iterations += 1
            if last.terminal or not last.ok:
                break
        last.details = {**last.details, "poll_iterations": iterations}
        return last
