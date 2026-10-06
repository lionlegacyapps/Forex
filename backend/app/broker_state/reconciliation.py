"""Observational reconciliation V1 — READ ONLY, zero mutations.

Compares internal DB positions/orders against broker snapshots.
Does NOT create/cancel orders or alter internal positions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker_state.models import (
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    ReconciliationCategory,
    ReconciliationFinding,
    ReconciliationReport,
)
from app.models.enums import PositionStatus
from app.models.execution import Execution
from app.models.order import Order
from app.models.position import Position


def _side_from_qty(qty: Decimal) -> str:
    return "long" if qty > 0 else "short" if qty < 0 else "flat"


def _norm_status(status: str) -> str:
    s = (status or "").lower().strip()
    if s == "canceled":
        return "cancelled"
    return s


class ReconciliationEngine:
    """Compare internal accounting vs external broker state. Observational only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reconcile(
        self,
        *,
        broker_account_id: UUID,
        broker: str,
        external_account_id: str | None,
        broker_positions: Iterable[BrokerPositionSnapshot],
        broker_orders: Iterable[BrokerOrderSnapshot],
    ) -> ReconciliationReport:
        findings: list[ReconciliationFinding] = []

        # --- Positions: aggregate internal open qty by symbol ---
        internal_rows = self._session.scalars(
            select(Position).where(
                Position.broker_account_id == broker_account_id,
                Position.status == PositionStatus.OPEN,
            )
        ).all()
        internal_by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for pos in internal_rows:
            internal_by_symbol[pos.symbol.upper()] += pos.quantity

        broker_by_symbol: dict[str, BrokerPositionSnapshot] = {}
        for bp in broker_positions:
            sym = bp.symbol.upper()
            # Signed quantity for comparison
            signed = bp.quantity if bp.side == "long" else -bp.quantity
            if sym in broker_by_symbol:
                existing = broker_by_symbol[sym]
                existing_signed = existing.quantity if existing.side == "long" else -existing.quantity
                combined = existing_signed + signed
                broker_by_symbol[sym] = BrokerPositionSnapshot(
                    symbol=sym,
                    asset_class=bp.asset_class,
                    quantity=abs(combined),
                    side=_side_from_qty(combined) if combined != 0 else "flat",
                    average_entry_price=bp.average_entry_price,
                    current_price=bp.current_price,
                    market_value=bp.market_value,
                    unrealized_pnl=bp.unrealized_pnl,
                    unrealized_pnl_percent=bp.unrealized_pnl_percent,
                    timestamp=bp.timestamp,
                    broker=bp.broker,
                )
            else:
                broker_by_symbol[sym] = bp

        all_symbols = set(internal_by_symbol) | set(broker_by_symbol)
        for sym in sorted(all_symbols):
            i_qty = internal_by_symbol.get(sym)
            b_pos = broker_by_symbol.get(sym)
            if i_qty is None and b_pos is not None:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MISSING_INTERNAL_POSITION,
                        message=f"Broker has position in {sym} with no internal open position",
                        symbol=sym,
                        broker_value=f"{b_pos.side}:{b_pos.quantity}",
                    )
                )
                continue
            if b_pos is None and i_qty is not None:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MISSING_BROKER_POSITION,
                        message=f"Internal open position in {sym} missing at broker",
                        symbol=sym,
                        internal_value=str(i_qty),
                    )
                )
                continue
            assert i_qty is not None and b_pos is not None
            i_side = _side_from_qty(i_qty)
            b_signed = b_pos.quantity if b_pos.side == "long" else -b_pos.quantity
            if i_side != "flat" and b_pos.side != "flat" and i_side != b_pos.side:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.POSITION_SIDE_MISMATCH,
                        message=f"Side mismatch for {sym}",
                        symbol=sym,
                        internal_value=i_side,
                        broker_value=b_pos.side,
                    )
                )
            elif i_qty != b_signed:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.POSITION_QUANTITY_MISMATCH,
                        message=f"Quantity mismatch for {sym}",
                        symbol=sym,
                        internal_value=str(i_qty),
                        broker_value=str(b_signed),
                    )
                )
            else:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MATCH,
                        message=f"Position {sym} matches",
                        symbol=sym,
                        internal_value=str(i_qty),
                        broker_value=str(b_signed),
                    )
                )

        # --- Orders: match by broker_order_id ---
        internal_orders = self._session.scalars(
            select(Order).where(Order.broker_account_id == broker_account_id)
        ).all()
        internal_by_broker_id = {
            o.broker_order_id: o for o in internal_orders if o.broker_order_id
        }
        broker_order_list = list(broker_orders)
        broker_ids = {o.broker_order_id for o in broker_order_list}

        for bo in broker_order_list:
            io = internal_by_broker_id.get(bo.broker_order_id)
            if io is None:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.UNKNOWN_BROKER_ORDER,
                        message=f"Broker order {bo.broker_order_id} not found internally",
                        symbol=bo.symbol,
                        broker_order_id=bo.broker_order_id,
                        broker_value=bo.status,
                    )
                )
                continue
            i_status = _norm_status(io.status.value if hasattr(io.status, "value") else str(io.status))
            b_status = _norm_status(bo.status)
            if i_status != b_status:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.ORDER_STATUS_MISMATCH,
                        message=f"Order status mismatch for {bo.broker_order_id}",
                        symbol=bo.symbol,
                        broker_order_id=bo.broker_order_id,
                        internal_value=i_status,
                        broker_value=b_status,
                    )
                )
            else:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MATCH,
                        message=f"Order {bo.broker_order_id} matches",
                        symbol=bo.symbol,
                        broker_order_id=bo.broker_order_id,
                    )
                )

            # Fill quantity / missing execution checks
            execs = self._session.scalars(
                select(Execution).where(Execution.order_id == io.id)
            ).all()
            internal_filled = sum((e.quantity for e in execs), Decimal("0"))
            broker_filled = bo.filled_quantity or Decimal("0")
            if broker_filled > 0 and len(execs) == 0:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MISSING_EXECUTION,
                        message=f"Broker filled qty without internal executions for {bo.broker_order_id}",
                        symbol=bo.symbol,
                        broker_order_id=bo.broker_order_id,
                        broker_value=str(broker_filled),
                        internal_value="0",
                    )
                )
            elif internal_filled != broker_filled:
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.FILL_QUANTITY_MISMATCH,
                        message=f"Filled quantity mismatch for {bo.broker_order_id}",
                        symbol=bo.symbol,
                        broker_order_id=bo.broker_order_id,
                        internal_value=str(internal_filled),
                        broker_value=str(broker_filled),
                    )
                )

        for broker_order_id, io in internal_by_broker_id.items():
            if broker_order_id not in broker_ids:
                # Only flag non-terminal internal orders as missing at broker when
                # reconciling against an open-order set; for full sets always report.
                findings.append(
                    ReconciliationFinding(
                        category=ReconciliationCategory.MISSING_BROKER_ORDER,
                        message=f"Internal order {broker_order_id} missing at broker",
                        symbol=io.symbol,
                        broker_order_id=broker_order_id,
                        internal_value=_norm_status(
                            io.status.value if hasattr(io.status, "value") else str(io.status)
                        ),
                    )
                )

        return ReconciliationReport(
            broker=broker,
            external_account_id=external_account_id,
            generated_at=datetime.now(UTC),
            findings=findings,
            mutations=0,
        )
