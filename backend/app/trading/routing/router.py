"""Broker Router V1 — routes ONLY risk-approved + validated proposals.

Supports solely the ``simulation`` broker provider in this milestone.
Never silently falls back to simulation for other broker slugs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.brokers.adapters.simulation import SIMULATION_PROVIDER, SimulationBroker
from app.brokers.base.broker import BrokerAdapter
from app.brokers.base.types import OrderRequest, OrderSide, OrderType, TimeInForce
from app.core.exceptions import TradingPipelineError
from app.models.broker_account import BrokerAccount
from app.models.enums import OrderStatus, TradeProposalStatus
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data
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


class BrokerRouter:
    """Select adapter and submit only after risk + validation gates."""

    def __init__(
        self,
        session: Session,
        *,
        audit: AuditService | None = None,
        adapters: dict[str, BrokerAdapter] | None = None,
        market_data: SimulationMarketData | None = None,
        paper_execution: PaperExecutionService | None = None,
    ) -> None:
        self._session = session
        self._audit = audit or AuditService(session)
        self._market = market_data or default_simulation_market_data
        self._adapters: dict[str, BrokerAdapter] = adapters or {
            SIMULATION_PROVIDER: SimulationBroker(market_data=self._market),
        }
        self._paper = paper_execution or PaperExecutionService(
            session, market_data=self._market, audit=self._audit
        )

    def get_adapter(self, broker_slug: str) -> BrokerAdapter | None:
        return self._adapters.get(broker_slug.lower().strip())

    async def route_and_submit(self, proposal: TradeProposal) -> RouteResult:
        """Route a **validated** proposal to its broker adapter and persist order."""
        try:
            return await self._route_and_submit_inner(proposal)
        except TradingPipelineError as exc:
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

        broker_slug = account.broker.lower().strip()
        adapter = self.get_adapter(broker_slug)
        if adapter is None:
            return RouteResult(
                success=False,
                reason_code=codes.UNSUPPORTED_BROKER,
                message=f"Unsupported broker '{broker_slug}' — no silent fallback",
            )

        assert_proposal_transition(proposal.status, TradeProposalStatus.ROUTED)
        proposal.status = TradeProposalStatus.ROUTED
        self._session.flush()
        self._audit.record(
            event_type=audit_events.ORDER_ROUTED,
            entity_type="trade_proposal",
            entity_id=proposal.id,
            details={"broker": broker_slug, "adapter": adapter.provider_name},
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
                "broker": broker_slug,
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
