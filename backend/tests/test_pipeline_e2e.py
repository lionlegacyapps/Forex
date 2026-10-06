"""End-to-end Trading Safety Pipeline V1 tests (simulation only)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Order, TradeProposal, TradeProposalStatus
from app.trading.proposals.service import TradeProposalService
from tests.pipeline_helpers import (
    make_assignment,
    make_global_policy,
    make_simulation_account,
    make_strategy,
    valid_limit_proposal,
)


@pytest.mark.asyncio
async def test_e2e_paper_simulation_success(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="E2E-OK")
    strategy = make_strategy(db_session, name="E2E-Strat")
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session, require_stop_loss=True)

    service = TradeProposalService(db_session)
    result = await service.create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )

    assert result.submitted is True
    assert result.status == TradeProposalStatus.SUBMITTED
    assert result.risk is not None and result.risk.approved
    assert result.validation is not None and result.validation.valid
    assert result.route is not None and result.route.success
    assert result.broker_order_id is not None
    assert result.broker_order_id.startswith("sim_")

    proposal = db_session.get(TradeProposal, result.proposal_id)
    assert proposal is not None
    assert proposal.status == TradeProposalStatus.SUBMITTED

    orders = list(
        db_session.scalars(
            select(Order).where(Order.trade_proposal_id == proposal.id)
        ).all()
    )
    assert len(orders) == 1
    assert orders[0].broker_order_id == result.broker_order_id
    assert orders[0].broker_account_id == account.id

    event_types = {
        e.event_type
        for e in db_session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == proposal.id)
        ).all()
    }
    # Submitted audit is on the order entity; proposal still has earlier events.
    all_types = {e.event_type for e in db_session.scalars(select(AuditEvent)).all()}
    assert "TRADE_PROPOSAL_CREATED" in event_types or "TRADE_PROPOSAL_CREATED" in all_types
    assert "RISK_APPROVED" in all_types
    assert "ORDER_VALIDATED" in all_types
    assert "ORDER_ROUTED" in all_types
    assert "SIMULATION_ORDER_SUBMITTED" in all_types


@pytest.mark.asyncio
async def test_e2e_invalid_proposal_zero_broker_submission(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="E2E-Bad", enabled=False)
    make_global_policy(db_session, require_stop_loss=True)

    service = TradeProposalService(db_session)
    result = await service.create_and_process(valid_limit_proposal(account))

    assert result.submitted is False
    assert result.status == TradeProposalStatus.RISK_REJECTED
    assert result.risk is not None and result.risk.approved is False
    assert result.route is None

    order_count = db_session.scalar(select(func.count()).select_from(Order)) or 0
    assert order_count == 0

    all_types = {e.event_type for e in db_session.scalars(select(AuditEvent)).all()}
    assert "RISK_REJECTED" in all_types
    assert "SIMULATION_ORDER_SUBMITTED" not in all_types
    assert "ORDER_ROUTED" not in all_types
