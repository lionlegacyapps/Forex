"""Broker Router V1 — routes ONLY risk-approved + validated proposals.

Supports:
  - simulation → SimulationBroker + PaperExecutionService (local fills)
  - alpaca → BrokerExecutionAdapter (Alpaca paper submit) + fill sync

Never silently falls back to simulation for other broker slugs.
ALPACA PAPER EXECUTION DOES NOT ENABLE LIVE TRADING.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.broker_state.models import BrokerOrderSnapshot
from app.broker_state.reconciliation import ReconciliationEngine
from app.brokers.adapters.simulation import SIMULATION_PROVIDER, SimulationBroker
from app.brokers.base.broker import BrokerAdapter
from app.brokers.base.types import OrderRequest, OrderSide, OrderType, TimeInForce
from app.brokers.execution.adapter import BrokerExecutionAdapter
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.errors import ExecutionAdapterError
from app.brokers.execution.fill_sync import AlpacaFillSyncService
from app.brokers.execution.status_map import map_alpaca_order_status
from app.brokers.execution.types import ExecutionSubmission
from app.core.exceptions import TradingPipelineError
from app.models.broker_account import BrokerAccount
from app.models.enums import OrderStatus, TradeProposalStatus, TradingMode
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data
from app.trading.execution.order_transitions import assert_order_transition
from app.trading.execution.service import PaperExecutionService
from app.trading.proposals.transitions import assert_proposal_transition
from app.trading.risk import codes


class RouteResult(BaseModel):
    success: bool
    reason_code: str | None = None
    message: str = ""
    order_id: str | None = None
    broker_order_id: str | None = None
    details: dict = Field(default_factory=dict)


ALPACA_PROVIDER = "alpaca"


def _default_execution_adapters() -> dict[str, BrokerExecutionAdapter]:
    """Do not auto-enable Alpaca writes from credentials alone.

    Operators/tests must inject ``AlpacaPaperExecutionAdapter`` explicitly.
    Market-data credentials must never silently unlock order submission.
    """
    return {}


class BrokerRouter:
    """Select adapter and submit only after risk + validation gates."""

    def __init__(
        self,
        session: Session,
        *,
        audit: AuditService | None = None,
        adapters: dict[str, BrokerAdapter] | None = None,
        execution_adapters: dict[str, BrokerExecutionAdapter] | None = None,
        market_data: SimulationMarketData | None = None,
        paper_execution: PaperExecutionService | None = None,
        fill_sync: AlpacaFillSyncService | None = None,
    ) -> None:
        self._session = session
        self._audit = audit or AuditService(session)
        self._market = market_data or default_simulation_market_data
        self._adapters: dict[str, BrokerAdapter] = adapters or {
            SIMULATION_PROVIDER: SimulationBroker(market_data=self._market),
        }
        self._execution_adapters: dict[str, BrokerExecutionAdapter] = (
            execution_adapters if execution_adapters is not None else _default_execution_adapters()
        )
        self._paper = paper_execution or PaperExecutionService(
            session, market_data=self._market, audit=self._audit
        )
        self._fill_sync = fill_sync or AlpacaFillSyncService(session, audit=self._audit)

    def get_adapter(self, broker_slug: str) -> BrokerAdapter | None:
        return self._adapters.get(broker_slug.lower().strip())

    def get_execution_adapter(self, broker_slug: str) -> BrokerExecutionAdapter | None:
        return self._execution_adapters.get(broker_slug.lower().strip())

    async def route_and_submit(self, proposal: TradeProposal) -> RouteResult:
        """Route a **validated** proposal to its broker adapter and persist order."""
        try:
            return await self._route_and_submit_inner(proposal)
        except TradingPipelineError as exc:
            return RouteResult(success=False, reason_code=exc.code, message=exc.message)
        except ExecutionAdapterError as exc:
            self._audit.record(
                event_type=audit_events.ALPACA_PAPER_ORDER_REJECTED,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={"code": exc.code, "message": exc.message},
            )
            return RouteResult(success=False, reason_code=exc.code, message=exc.message)
        except Exception as exc:  # noqa: BLE001 — fail closed
            self._audit.record(
                event_type=audit_events.PIPELINE_ERROR,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={"stage": "router", "error_type": type(exc).__name__},
            )
            return RouteResult(
                success=False,
                reason_code=codes.BROKER_ROUTER_ERROR,
                message="Router failed closed due to unexpected error",
            )

    async def _route_and_submit_inner(self, proposal: TradeProposal) -> RouteResult:
        if proposal.status != TradeProposalStatus.VALIDATED:
            return RouteResult(
                success=False,
                reason_code=codes.PROPOSAL_NOT_VALIDATED,
                message=(
                    "Router requires validated proposal; "
                    f"got {proposal.status.value}"
                ),
            )

        account = self._session.get(BrokerAccount, proposal.broker_account_id)
        if account is None:
            return RouteResult(
                success=False,
                reason_code=codes.BROKER_ACCOUNT_NOT_FOUND,
                message="Broker account not found",
            )

        if not account.is_enabled:
            return RouteResult(
                success=False,
                reason_code=codes.BROKER_ACCOUNT_DISABLED,
                message="Broker account is disabled",
            )

        if account.trading_mode != TradingMode.PAPER:
            return RouteResult(
                success=False,
                reason_code=codes.LIVE_TRADING_NOT_ALLOWED,
                message="Router rejects non-paper trading mode",
            )

        broker_slug = account.broker.lower().strip()
        execution_adapter = self.get_execution_adapter(broker_slug)
        sim_adapter = self.get_adapter(broker_slug)

        if execution_adapter is not None:
            return await self._route_external_execution(proposal, account, execution_adapter)
        if sim_adapter is not None:
            return await self._route_simulation(proposal, account, sim_adapter)

        return RouteResult(
            success=False,
            reason_code=codes.UNSUPPORTED_BROKER,
            message=f"Unsupported broker '{broker_slug}' — no silent fallback",
        )

    async def _route_simulation(
        self,
        proposal: TradeProposal,
        account: BrokerAccount,
        adapter: BrokerAdapter,
    ) -> RouteResult:
        assert_proposal_transition(proposal.status, TradeProposalStatus.ROUTED)
        proposal.status = TradeProposalStatus.ROUTED
        self._session.flush()
        self._audit.record(
            event_type=audit_events.ORDER_ROUTED,
            entity_type="trade_proposal",
            entity_id=proposal.id,
            details={"broker": account.broker, "adapter": adapter.provider_name},
        )

        request = OrderRequest(
            symbol=proposal.symbol,
            side=OrderSide(proposal.side.value),
            quantity=proposal.quantity,
            order_type=OrderType(proposal.order_type.value),
            time_in_force=TimeInForce(proposal.time_in_force.value),
            limit_price=proposal.limit_price,
            stop_price=proposal.stop_price,
            client_order_id=str(proposal.id),
            metadata={
                "trading_mode": account.trading_mode.value,
                "trade_proposal_id": str(proposal.id),
                "simulated": True,
            },
        )

        broker_order = await adapter.place_order(request)

        db_order = Order(
            trade_proposal_id=proposal.id,
            broker_account_id=proposal.broker_account_id,
            broker_order_id=broker_order.id,
            symbol=proposal.symbol,
            asset_class=proposal.asset_class,
            side=proposal.side,
            order_type=proposal.order_type,
            quantity=proposal.quantity,
            limit_price=proposal.limit_price,
            stop_price=proposal.stop_price,
            time_in_force=proposal.time_in_force,
            status=OrderStatus.SUBMITTED,
            submitted_at=datetime.now(UTC),
        )
        self._session.add(db_order)
        self._session.flush()

        fill = self._paper.process_submitted_order(db_order)

        assert_proposal_transition(proposal.status, TradeProposalStatus.SUBMITTED)
        proposal.status = TradeProposalStatus.SUBMITTED
        self._session.flush()

        self._audit.record(
            event_type=audit_events.SIMULATION_ORDER_SUBMITTED,
            entity_type="order",
            entity_id=db_order.id,
            details={
                "broker_order_id": broker_order.id,
                "trade_proposal_id": str(proposal.id),
                "broker": account.broker,
                "status": db_order.status.value,
                "filled": fill.filled,
                "fill_reason": fill.reason_code,
            },
        )

        return RouteResult(
            success=True,
            message=(
                "Order submitted and filled via simulation"
                if fill.filled
                else "Order submitted via simulation (not filled)"
            ),
            order_id=str(db_order.id),
            broker_order_id=broker_order.id,
            details={
                "provider": adapter.provider_name,
                "filled": fill.filled,
                "fill_price": str(fill.fill_price) if fill.fill_price is not None else None,
                "broker_execution_id": fill.broker_execution_id,
                "fill_reason_code": fill.reason_code,
            },
        )

    async def _route_external_execution(
        self,
        proposal: TradeProposal,
        account: BrokerAccount,
        adapter: BrokerExecutionAdapter,
    ) -> RouteResult:
        """Alpaca paper (or injected) execution path — no sim fill fabrication."""
        assert_proposal_transition(proposal.status, TradeProposalStatus.ROUTED)
        proposal.status = TradeProposalStatus.ROUTED
        self._session.flush()
        self._audit.record(
            event_type=audit_events.ORDER_ROUTED,
            entity_type="trade_proposal",
            entity_id=proposal.id,
            details={"broker": account.broker, "adapter": adapter.provider_name},
        )

        # Persist internal order BEFORE broker submit for durable client_order_id.
        db_order = Order(
            trade_proposal_id=proposal.id,
            broker_account_id=proposal.broker_account_id,
            broker_order_id=None,
            symbol=proposal.symbol,
            asset_class=proposal.asset_class,
            side=proposal.side,
            order_type=proposal.order_type,
            quantity=proposal.quantity,
            limit_price=proposal.limit_price,
            stop_price=proposal.stop_price,
            time_in_force=proposal.time_in_force,
            status=OrderStatus.NEW,
            submitted_at=None,
        )
        self._session.add(db_order)
        self._session.flush()

        client_order_id = build_client_order_id(db_order.id)
        submission = ExecutionSubmission(
            trade_proposal_id=proposal.id,
            proposal_status=proposal.status.value,
            risk_approved=True,
            validated=True,
            routed=True,
            broker_account_id=account.id,
            broker=account.broker.lower().strip(),
            trading_mode=account.trading_mode.value,
            account_enabled=account.is_enabled,
            internal_order_id=db_order.id,
            client_order_id=client_order_id,
            symbol=proposal.symbol,
            asset_class=proposal.asset_class.value,
            side=proposal.side.value,
            order_type=proposal.order_type.value,
            quantity=proposal.quantity,
            limit_price=proposal.limit_price,
            stop_price=proposal.stop_price,
            time_in_force=proposal.time_in_force.value,
        )

        self._audit.record(
            event_type=audit_events.ALPACA_PAPER_PRE_SUBMIT_CHECK,
            entity_type="order",
            entity_id=db_order.id,
            details={
                "client_order_id": client_order_id,
                "symbol": proposal.symbol,
                "broker": account.broker,
            },
        )

        try:
            result = await adapter.submit_order(submission)
        except ExecutionAdapterError:
            # Leave order NEW / proposal ROUTED for operator inspection; do not invent fill
            raise

        assert_order_transition(db_order.status, OrderStatus.SUBMITTED)
        db_order.broker_order_id = result.broker_order_id
        db_order.status = OrderStatus.SUBMITTED
        db_order.submitted_at = result.submitted_at or datetime.now(UTC)
        self._session.flush()

        self._audit.record(
            event_type=audit_events.ALPACA_PAPER_ORDER_SUBMITTED,
            entity_type="order",
            entity_id=db_order.id,
            details={
                "broker_order_id": result.broker_order_id,
                "client_order_id": result.client_order_id,
                "recovered_existing": result.recovered_existing,
                "submit_http_calls": result.submit_http_calls,
            },
        )
        self._audit.record(
            event_type=audit_events.ALPACA_PAPER_ORDER_ACCEPTED,
            entity_type="order",
            entity_id=db_order.id,
            details={"broker_status": result.status},
        )

        # Status sync + fills via read helpers when available
        sync_details: dict = {}
        if hasattr(adapter, "get_order_by_id"):
            try:
                payload = await adapter.get_order_by_id(result.broker_order_id)  # type: ignore[attr-defined]
                sync_details = self._fill_sync.apply_broker_order_snapshot(db_order, payload)
            except Exception as exc:  # noqa: BLE001
                sync_details = {"sync_error": type(exc).__name__}

        # Observational reconciliation
        recon_findings = 0
        try:
            broker_orders = [
                BrokerOrderSnapshot(
                    broker_order_id=result.broker_order_id,
                    symbol=proposal.symbol.upper(),
                    side=proposal.side.value,
                    order_type=proposal.order_type.value,
                    quantity=proposal.quantity,
                    filled_quantity=result.filled_quantity,
                    status=map_alpaca_order_status(result.status).value,
                )
            ]
            report = ReconciliationEngine(self._session).reconcile(
                broker_account_id=account.id,
                broker=account.broker,
                external_account_id=account.external_account_id,
                broker_positions=[],  # positions refreshed separately when needed
                broker_orders=broker_orders,
            )
            mismatches = [
                f for f in report.findings if f.category.value != "MATCH"
            ]
            recon_findings = len(mismatches)
            if mismatches:
                self._audit.record(
                    event_type=audit_events.ALPACA_RECONCILIATION_MISMATCH,
                    entity_type="order",
                    entity_id=db_order.id,
                    details={
                        "count": len(mismatches),
                        "categories": [f.category.value for f in mismatches[:10]],
                    },
                )
        except Exception as exc:  # noqa: BLE001
            sync_details["recon_error"] = type(exc).__name__

        assert_proposal_transition(proposal.status, TradeProposalStatus.SUBMITTED)
        proposal.status = TradeProposalStatus.SUBMITTED
        self._session.flush()

        return RouteResult(
            success=True,
            message="Order submitted via Alpaca paper execution",
            order_id=str(db_order.id),
            broker_order_id=result.broker_order_id,
            details={
                "provider": adapter.provider_name,
                "client_order_id": result.client_order_id,
                "broker_status": result.status,
                "recovered_existing": result.recovered_existing,
                "submit_http_calls": result.submit_http_calls,
                "sync": sync_details,
                "reconciliation_mismatches": recon_findings,
                "paper": True,
                "live": False,
            },
        )
