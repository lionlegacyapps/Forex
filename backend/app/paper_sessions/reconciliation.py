"""Pre-activation broker reconciliation gate (read-only)."""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.broker_state.models import BrokerOrderSnapshot, BrokerPositionSnapshot
from app.broker_state.reconciliation import ReconciliationEngine
from app.models.broker_account import BrokerAccount
from app.models.enums import TradingMode
from app.paper_sessions.errors import ActivationRejectedError


class BrokerSnapshotSource(Protocol):
    async def get_account_identity(self) -> dict: ...
    async def get_positions(self) -> list[BrokerPositionSnapshot]: ...
    async def get_open_orders(self) -> list[BrokerOrderSnapshot]: ...


class StaticBrokerSnapshotSource:
    """Test double — never contacts Alpaca."""

    def __init__(
        self,
        *,
        external_account_id: str = "paper-test",
        paper_verified: bool = True,
        positions: list[BrokerPositionSnapshot] | None = None,
        open_orders: list[BrokerOrderSnapshot] | None = None,
    ) -> None:
        self.external_account_id = external_account_id
        self.paper_verified = paper_verified
        self.positions = list(positions or [])
        self.open_orders = list(open_orders or [])

    async def get_account_identity(self) -> dict:
        return {
            "external_account_id": self.external_account_id,
            "paper_verified": self.paper_verified,
            "trading_mode": "paper",
        }

    async def get_positions(self) -> list[BrokerPositionSnapshot]:
        return list(self.positions)

    async def get_open_orders(self) -> list[BrokerOrderSnapshot]:
        return list(self.open_orders)


class PreActivationReconciliationResult(BaseModel):
    ok: bool
    reasons: list[str] = Field(default_factory=list)
    open_order_count: int = 0
    open_position_count: int = 0
    finding_count: int = 0


async def reconcile_before_activation(
    db: Session,
    *,
    account: BrokerAccount,
    broker_source: BrokerSnapshotSource,
    instrument: str,
    allow_existing_positions: bool = False,
    allow_open_orders: bool = False,
) -> PreActivationReconciliationResult:
    if account.trading_mode != TradingMode.PAPER:
        raise ActivationRejectedError("live account rejected", code="live_account")

    identity = await broker_source.get_account_identity()
    reasons: list[str] = []
    if not identity.get("paper_verified", False):
        reasons.append("broker_not_paper_verified")
    ext = identity.get("external_account_id")
    if account.external_account_id and ext and account.external_account_id != ext:
        reasons.append("broker_account_identity_mismatch")

    positions = await broker_source.get_positions()
    orders = await broker_source.get_open_orders()
    sym = instrument.strip().upper()
    conflicting_pos = [p for p in positions if p.symbol.upper() == sym]
    conflicting_orders = [o for o in orders if o.symbol.upper() == sym]

    if conflicting_pos and not allow_existing_positions:
        reasons.append("conflicting_broker_positions")
    if conflicting_orders and not allow_open_orders:
        reasons.append("conflicting_open_orders")

    report = ReconciliationEngine(db).reconcile(
        broker_account_id=account.id,
        broker=account.broker,
        external_account_id=account.external_account_id,
        broker_positions=positions,
        broker_orders=orders,
    )
    # Stale local mismatches are informational unless severe
    severe = [
        f
        for f in report.findings
        if f.category.value
        in {
            "MISSING_INTERNAL_POSITION",
            "MISSING_BROKER_POSITION",
            "POSITION_QUANTITY_MISMATCH",
        }
    ]
    if severe:
        reasons.append("stale_local_state")

    ok = len(reasons) == 0
    return PreActivationReconciliationResult(
        ok=ok,
        reasons=reasons,
        open_order_count=len(orders),
        open_position_count=len(positions),
        finding_count=len(report.findings),
    )


def assert_activation_safe(result: PreActivationReconciliationResult) -> None:
    if not result.ok:
        raise ActivationRejectedError(
            "pre-activation reconciliation failed: " + ",".join(result.reasons),
            code="reconciliation_failed",
        )
