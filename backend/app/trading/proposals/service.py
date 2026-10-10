"""Trade Proposal Service — create proposals and drive the safety pipeline.

Does NOT call brokers directly. Submission only occurs via BrokerRouter after
Risk Engine + Order Validator succeed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.audit import service as audit_events
from app.audit.service import AuditService
from app.models.enums import TradeProposalStatus
from app.models.trade_proposal import TradeProposal
from app.market_data.service import MarketDataService
from app.trading.execution.market_data import SimulationMarketData, default_simulation_market_data
from app.trading.proposals.schemas import CreateTradeProposalInput, PipelineResult
from app.trading.proposals.transitions import assert_proposal_transition
from app.trading.risk import codes
from app.trading.risk.engine import RiskEngine
from app.trading.risk.results import RiskDecision
from app.trading.routing.router import BrokerRouter, RouteResult
from app.trading.validation.validator import OrderValidator, ValidationResult


@dataclass
class TradeProposalService:
    """Application service for proposal creation and pipeline processing."""

    session: Session
    risk_engine: RiskEngine | None = None
    order_validator: OrderValidator | None = None
    broker_router: BrokerRouter | None = None
    audit: AuditService | None = None
    market_data: SimulationMarketData | None = None
    market_data_service: MarketDataService | None = None

    def __post_init__(self) -> None:
        market = self.market_data or default_simulation_market_data
        self.market_data = market
        self.audit = self.audit or AuditService(self.session)
        self.risk_engine = self.risk_engine or RiskEngine(
            self.session,
            market_data=market,
            market_data_service=self.market_data_service,
        )
        self.order_validator = self.order_validator or OrderValidator(self.session)
        self.broker_router = self.broker_router or BrokerRouter(
            self.session, audit=self.audit, market_data=market
        )

    def create_proposal(self, data: CreateTradeProposalInput) -> TradeProposal:
        metadata = dict(data.metadata or {})
        if data.idempotency_key:
            metadata["idempotency_key"] = data.idempotency_key

        proposal = TradeProposal(
            broker_account_id=data.broker_account_id,
            strategy_id=data.strategy_id,
            source=data.source,
            symbol=data.symbol,
            asset_class=data.asset_class,
            side=data.side,
            order_type=data.order_type,
            quantity=data.quantity,
            limit_price=data.limit_price,
            stop_price=data.stop_price,
            stop_loss_price=data.stop_loss_price,
            take_profit_price=data.take_profit_price,
            time_in_force=data.time_in_force,
            signal_reference=data.signal_reference,
            status=TradeProposalStatus.PENDING,
            metadata_=metadata,
        )
        self.session.add(proposal)
        self.session.flush()
        self.audit.record(
            event_type=audit_events.TRADE_PROPOSAL_CREATED,
            entity_type="trade_proposal",
            entity_id=proposal.id,
            details={
                "symbol": proposal.symbol,
                "side": proposal.side.value,
                "order_type": proposal.order_type.value,
                "source": proposal.source.value,
                "broker_account_id": str(proposal.broker_account_id),
            },
        )
        return proposal

    def evaluate_risk(self, proposal: TradeProposal) -> RiskDecision:
        """Run Risk Engine; transition to risk_approved / risk_rejected. Fail-closed."""
        if proposal.status != TradeProposalStatus.PENDING:
            return RiskDecision.reject(
                reason_code=codes.INVALID_STATE_TRANSITION,
                message=f"Risk evaluation requires pending status, got {proposal.status.value}",
            )

        try:
            decision = self.risk_engine.evaluate(proposal)
        except Exception as exc:  # noqa: BLE001 — fail closed
            self.audit.record(
                event_type=audit_events.PIPELINE_ERROR,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={"stage": "risk", "error_type": type(exc).__name__},
            )
            decision = RiskDecision.reject(
                reason_code=codes.RISK_ENGINE_ERROR,
                message="Risk Engine failed closed due to unexpected error",
            )

        if decision.approved:
            assert_proposal_transition(proposal.status, TradeProposalStatus.RISK_APPROVED)
            proposal.status = TradeProposalStatus.RISK_APPROVED
            proposal.rejection_reason = None
            self.session.flush()
            self.audit.record(
                event_type=audit_events.RISK_APPROVED,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={
                    "checks": [c.model_dump() for c in decision.checks],
                },
            )
        else:
            assert_proposal_transition(proposal.status, TradeProposalStatus.RISK_REJECTED)
            proposal.status = TradeProposalStatus.RISK_REJECTED
            proposal.rejection_reason = (
                f"{decision.reason_code}: {decision.message}" if decision.reason_code else decision.message
            )
            self.session.flush()
            self.audit.record(
                event_type=audit_events.RISK_REJECTED,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={
                    "reason_code": decision.reason_code,
                    "message": decision.message,
                    "checks": [c.model_dump() for c in decision.checks],
                },
            )
        return decision

    def validate_order(self, proposal: TradeProposal) -> ValidationResult:
        """Run Order Validator; transition validated / validation_rejected. Fail-closed."""
        try:
            result = self.order_validator.validate(proposal)
        except Exception as exc:  # noqa: BLE001
            self.audit.record(
                event_type=audit_events.PIPELINE_ERROR,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={"stage": "validation", "error_type": type(exc).__name__},
            )
            result = ValidationResult.reject(
                reason_code=codes.ORDER_VALIDATION_ERROR,
                message="Order Validator failed closed due to unexpected error",
            )

        if proposal.status != TradeProposalStatus.RISK_APPROVED:
            # Do not mutate terminal/wrong states into validated.
            return result if not result.valid else ValidationResult.reject(
                reason_code=codes.PROPOSAL_NOT_RISK_APPROVED,
                message="Cannot validate proposal that is not risk_approved",
            )

        if result.valid:
            assert_proposal_transition(proposal.status, TradeProposalStatus.VALIDATED)
            proposal.status = TradeProposalStatus.VALIDATED
            proposal.rejection_reason = None
            self.session.flush()
            self.audit.record(
                event_type=audit_events.ORDER_VALIDATED,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={"checks": [c.model_dump() for c in result.checks]},
            )
        else:
            assert_proposal_transition(
                proposal.status, TradeProposalStatus.VALIDATION_REJECTED
            )
            proposal.status = TradeProposalStatus.VALIDATION_REJECTED
            proposal.rejection_reason = (
                f"{result.reason_code}: {result.message}" if result.reason_code else result.message
            )
            self.session.flush()
            self.audit.record(
                event_type=audit_events.ORDER_VALIDATION_REJECTED,
                entity_type="trade_proposal",
                entity_id=proposal.id,
                details={
                    "reason_code": result.reason_code,
                    "message": result.message,
                    "checks": [c.model_dump() for c in result.checks],
                },
            )
        return result

    async def route(self, proposal: TradeProposal) -> RouteResult:
        """Submit via BrokerRouter only when validated."""
        return await self.broker_router.route_and_submit(proposal)

    async def create_and_process(self, data: CreateTradeProposalInput) -> PipelineResult:
        """Full PAPER path: create → risk → validate → route/submit. Fail-closed."""
        proposal = self.create_proposal(data)
        risk = self.evaluate_risk(proposal)
        if not risk.approved:
            return PipelineResult(
                proposal_id=proposal.id,
                status=proposal.status,
                risk=risk,
                submitted=False,
            )

        validation = self.validate_order(proposal)
        if not validation.valid:
            return PipelineResult(
                proposal_id=proposal.id,
                status=proposal.status,
                risk=risk,
                validation=validation,
                submitted=False,
            )

        route = await self.route(proposal)
        return PipelineResult(
            proposal_id=proposal.id,
            status=proposal.status,
            risk=risk,
            validation=validation,
            route=route,
            submitted=route.success,
            broker_order_id=route.broker_order_id,
        )
