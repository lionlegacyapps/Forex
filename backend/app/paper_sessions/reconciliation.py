"""Pre-activation broker reconciliation gate (read-only)."""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.broker_state.models import BrokerOrderSnapshot, BrokerPositionSnapshot
from app.broker_state.reconciliation import ReconciliationEngine
from decimal import Decimal

from app.models.broker_account import BrokerAccount
from app.models.enums import TradingMode
from app.paper_sessions.errors import ActivationRejectedError
from app.paper_sessions.paper_endpoint import verify_alpaca_paper_endpoint


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
        buying_power: str = "100000",
        paper_base_url: str = "https://paper-api.alpaca.markets",
        positions: list[BrokerPositionSnapshot] | None = None,
        open_orders: list[BrokerOrderSnapshot] | None = None,
    ) -> None:
        self.external_account_id = external_account_id
        self.paper_verified = paper_verified
        self.buying_power = buying_power
        self.paper_base_url = paper_base_url
        self.positions = list(positions or [])
        self.open_orders = list(open_orders or [])

    async def get_account_identity(self) -> dict:
        return {
            "external_account_id": self.external_account_id,
            "paper_verified": self.paper_verified,
            "trading_mode": "paper",
            "buying_power": self.buying_power,
            "paper_base_url": self.paper_base_url,
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
    require_buying_power: bool = False,
    verify_paper_endpoint: bool = False,
) -> PreActivationReconciliationResult:
    if account.trading_mode != TradingMode.PAPER:
        raise ActivationRejectedError("live account rejected", code="live_account")

    identity = await broker_source.get_account_identity()
    reasons: list[str] = []
    if not identity.get("paper_verified", False):
        reasons.append("broker_not_paper_verified")
    # Never trust client trading_mode flags — only server account mode + paper_verified.
    if identity.get("trading_mode") and identity.get("trading_mode") != "paper":
        reasons.append("broker_identity_not_paper")
    ext = identity.get("external_account_id")
    if account.external_account_id and ext and account.external_account_id != ext:
        reasons.append("broker_account_identity_mismatch")

    if verify_paper_endpoint:
        try:
            endpoint = identity.get("paper_base_url")
            verify_alpaca_paper_endpoint(
                str(endpoint) if endpoint else None
            )
        except ActivationRejectedError as exc:
            reasons.append(exc.code)

    if require_buying_power:
        try:
            bp = Decimal(str(identity.get("buying_power", "0")))
        except Exception:  # noqa: BLE001
            bp = Decimal("0")
        if bp <= 0:
            reasons.append("insufficient_paper_buying_power")

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
