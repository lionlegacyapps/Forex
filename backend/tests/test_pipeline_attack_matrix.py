"""Attack matrix for Trading Safety Pipeline V1 — fail-closed proofs."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.brokers.adapters.simulation import SimulationBroker
from app.brokers.base.types import OrderRequest, OrderSide, OrderType as BrokerOrderType, TimeInForce
from app.models import (
    AssetClass,
    Order,
    OrderType,
    Position,
    PositionStatus,
    ProposalSource,
    RiskPolicy,
    RiskScopeType,
    TradeProposal,
    TradeProposalStatus,
    TradeSide,
    TradingMode,
)
from app.models.enums import StrategyStatus
from app.trading.proposals.schemas import CreateTradeProposalInput
from app.trading.proposals.service import TradeProposalService
from app.trading.proposals.transitions import assert_proposal_transition, can_transition
from app.trading.risk import codes
from app.trading.risk.engine import RiskEngine
from app.trading.risk.resolver import RiskPolicyResolver
from app.trading.routing.router import BrokerRouter
from app.trading.validation.validator import OrderValidator
from tests.pipeline_helpers import (
    make_assignment,
    make_global_policy,
    make_simulation_account,
    make_strategy,
    valid_limit_proposal,
)


def _service(session: Session) -> TradeProposalService:
    return TradeProposalService(session)


# ---------------------------------------------------------------------------
# Risk Engine attack cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_disabled_broker_account(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Dis-Acct", enabled=False)
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(valid_limit_proposal(account))
    assert result.status == TradeProposalStatus.RISK_REJECTED
    assert result.risk and result.risk.reason_code == codes.BROKER_ACCOUNT_DISABLED
    assert (db_session.scalar(select(func.count()).select_from(Order)) or 0) == 0


@pytest.mark.asyncio
async def test_reject_live_broker_account(db_session: Session) -> None:
    account = make_simulation_account(
        db_session, name="Live-Acct", enabled=True, trading_mode=TradingMode.LIVE
    )
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(valid_limit_proposal(account))
    assert result.risk and result.risk.reason_code == codes.LIVE_TRADING_NOT_ALLOWED
    assert result.submitted is False


@pytest.mark.asyncio
async def test_reject_disabled_strategy_assignment(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Asg-Dis")
    strategy = make_strategy(db_session, name="Asg-Dis-S")
    make_assignment(db_session, strategy=strategy, account=account, enabled=False)
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )
    assert result.risk and result.risk.reason_code == codes.STRATEGY_ASSIGNMENT_DISABLED


@pytest.mark.asyncio
async def test_reject_unassigned_strategy(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Unasg")
    strategy = make_strategy(db_session, name="Unasg-S")
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )
    assert result.risk and result.risk.reason_code == codes.STRATEGY_NOT_ASSIGNED


@pytest.mark.asyncio
async def test_reject_paused_strategy(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Pause-A")
    strategy = make_strategy(db_session, name="Pause-S", status=StrategyStatus.PAUSED)
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )
    assert result.risk and result.risk.reason_code == codes.STRATEGY_PAUSED


@pytest.mark.asyncio
async def test_reject_retired_strategy(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Ret-A")
    strategy = make_strategy(db_session, name="Ret-S", status=StrategyStatus.RETIRED)
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )
    assert result.risk and result.risk.reason_code == codes.STRATEGY_RETIRED


@pytest.mark.asyncio
async def test_reject_live_strategy_assignment(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Asg-Live")
    strategy = make_strategy(db_session, name="Asg-Live-S")
    make_assignment(
        db_session,
        strategy=strategy,
        account=account,
        trading_mode=TradingMode.LIVE,
    )
    make_global_policy(db_session)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, strategy_id=strategy.id)
    )
    assert result.risk and result.risk.reason_code == codes.STRATEGY_ASSIGNMENT_LIVE_NOT_ALLOWED


@pytest.mark.asyncio
async def test_reject_missing_required_stop_loss(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="SL-Miss")
    make_global_policy(db_session, require_stop_loss=True)
    payload = valid_limit_proposal(account, stop_loss_price=None)
    result = await _service(db_session).create_and_process(payload)
    assert result.risk and result.risk.reason_code == codes.STOP_LOSS_REQUIRED


@pytest.mark.asyncio
async def test_reject_zero_and_negative_quantity(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Qty-Bad")
    make_global_policy(db_session, require_stop_loss=False)

    for qty in (Decimal("0"), Decimal("-5")):
        # Bypass ORM CHECK by evaluating risk on an in-memory-ish path:
        # create via service still hits DB CHECK for quantity > 0.
        # Exercise RiskEngine directly with a flushed proposal that we mutate
        # after load is not possible due to CHECK — so call engine with a
        # detached-style object constructed then added only for engine unit
        # evaluation using pending row that fails DB. Instead call evaluate
        # on a proposal created with positive qty then patched.
        proposal = _service(db_session).create_proposal(
            valid_limit_proposal(account, quantity=Decimal("1"), stop_loss_price=None)
        )
        proposal.quantity = qty
        decision = RiskEngine(db_session).evaluate(proposal)
        assert decision.approved is False
        assert decision.reason_code == codes.QUANTITY_INVALID


@pytest.mark.asyncio
async def test_reject_max_position_size_exceeded(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MPS")
    strategy = make_strategy(db_session, name="MPS-S")
    make_assignment(
        db_session,
        strategy=strategy,
        account=account,
        max_position_size=Decimal("5"),
    )
    make_global_policy(db_session, require_stop_loss=False)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(
            account,
            strategy_id=strategy.id,
            quantity=Decimal("10"),
            stop_loss_price=None,
        )
    )
    assert result.risk and result.risk.reason_code == codes.MAX_POSITION_SIZE_EXCEEDED


@pytest.mark.asyncio
async def test_reject_max_order_value_when_calculable(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MOV")
    make_global_policy(
        db_session,
        require_stop_loss=False,
        max_order_value=Decimal("500"),
    )
    # 10 * 100 = 1000 > 500
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("100"),
            stop_loss_price=None,
        )
    )
    assert result.risk and result.risk.reason_code == codes.MAX_ORDER_VALUE_EXCEEDED


@pytest.mark.asyncio
async def test_max_order_value_not_evaluated_without_price(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MOV-Mkt")
    make_global_policy(
        db_session,
        require_stop_loss=False,
        max_order_value=Decimal("500"),
    )
    payload = CreateTradeProposalInput(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        stop_loss_price=None,
    )
    service = _service(db_session)
    proposal = service.create_proposal(payload)
    decision = service.evaluate_risk(proposal)
    # Market order cannot compute value without fabricating price — recorded,
    # and PAPER path may still approve other checks.
    assert any(
        c.reason_code == codes.NOT_EVALUATED_MARKET_PRICE_REQUIRED for c in decision.checks
    )


@pytest.mark.asyncio
async def test_reject_open_position_limit(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="OPL")
    make_global_policy(db_session, require_stop_loss=False, max_open_positions=1)
    db_session.add(
        Position(
            broker_account_id=account.id,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            quantity=Decimal("1"),
            average_entry_price=Decimal("10"),
            status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    assert result.risk and result.risk.reason_code == codes.MAX_OPEN_POSITIONS_EXCEEDED


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Idem")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    first = await service.create_and_process(
        valid_limit_proposal(account, stop_loss_price=None, idempotency_key="k-1")
    )
    assert first.submitted is True
    second = await service.create_and_process(
        valid_limit_proposal(account, stop_loss_price=None, idempotency_key="k-1")
    )
    assert second.risk and second.risk.reason_code == codes.DUPLICATE_PROPOSAL
    assert second.submitted is False


# ---------------------------------------------------------------------------
# Order Validator attack cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validator_rejects_blank_symbol(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Sym")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, symbol="AAPL", stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    proposal.symbol = "   "
    result = service.validate_order(proposal)
    assert result.valid is False
    assert result.reason_code == "INVALID_SYMBOL"


@pytest.mark.asyncio
async def test_validator_limit_without_limit_price(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Lim")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    proposal.limit_price = None
    result = OrderValidator(db_session).validate(proposal)
    assert result.valid is False
    assert result.reason_code == "LIMIT_PRICE_REQUIRED"


@pytest.mark.asyncio
async def test_validator_stop_without_stop_price(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Stp")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    payload = CreateTradeProposalInput(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.STOP,
        quantity=Decimal("1"),
        stop_price=Decimal("100"),
        stop_loss_price=None,
    )
    proposal = service.create_proposal(payload)
    service.evaluate_risk(proposal)
    proposal.stop_price = None
    result = OrderValidator(db_session).validate(proposal)
    assert result.valid is False
    assert result.reason_code == "STOP_PRICE_REQUIRED"


@pytest.mark.asyncio
async def test_validator_stop_limit_missing_prices(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="SLP")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    payload = CreateTradeProposalInput(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.STOP_LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("101"),
        stop_price=Decimal("100"),
        stop_loss_price=None,
    )
    proposal = service.create_proposal(payload)
    service.evaluate_risk(proposal)
    proposal.limit_price = None
    result = OrderValidator(db_session).validate(proposal)
    assert result.valid is False
    assert result.reason_code == "STOP_LIMIT_PRICES_REQUIRED"


@pytest.mark.asyncio
async def test_validator_rejects_non_risk_approved(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="NRA")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    # still pending
    result = OrderValidator(db_session).validate(proposal)
    assert result.valid is False
    assert result.reason_code == codes.PROPOSAL_NOT_RISK_APPROVED


# ---------------------------------------------------------------------------
# Router / simulation attack cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_broker_rejected(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Alp", broker="alpaca")
    make_global_policy(db_session, require_stop_loss=False)
    result = await _service(db_session).create_and_process(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    assert result.validation and result.validation.valid
    assert result.route and result.route.success is False
    assert result.route.reason_code == codes.UNSUPPORTED_BROKER
    assert (db_session.scalar(select(func.count()).select_from(Order)) or 0) == 0


@pytest.mark.asyncio
async def test_router_rejects_risk_rejected_proposal(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="RR", enabled=False)
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    assert proposal.status == TradeProposalStatus.RISK_REJECTED
    route = await service.route(proposal)
    assert route.success is False
    assert route.reason_code == codes.PROPOSAL_NOT_VALIDATED


@pytest.mark.asyncio
async def test_router_rejects_before_validation(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="BV")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    assert proposal.status == TradeProposalStatus.RISK_APPROVED
    route = await service.route(proposal)
    assert route.success is False
    assert route.reason_code == codes.PROPOSAL_NOT_VALIDATED


@pytest.mark.asyncio
async def test_illegal_state_transitions(db_session: Session) -> None:
    assert can_transition(TradeProposalStatus.PENDING, TradeProposalStatus.SUBMITTED) is False
    assert can_transition(TradeProposalStatus.RISK_REJECTED, TradeProposalStatus.SUBMITTED) is False
    assert can_transition(TradeProposalStatus.SUBMITTED, TradeProposalStatus.PENDING) is False
    with pytest.raises(Exception):
        assert_proposal_transition(
            TradeProposalStatus.PENDING, TradeProposalStatus.SUBMITTED
        )


# ---------------------------------------------------------------------------
# Fail-closed exception paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_engine_exception_fails_closed(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Rx")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    with patch.object(service.risk_engine, "evaluate", side_effect=RuntimeError("boom")):
        decision = service.evaluate_risk(proposal)
    assert decision.approved is False
    assert decision.reason_code == codes.RISK_ENGINE_ERROR
    assert proposal.status == TradeProposalStatus.RISK_REJECTED


@pytest.mark.asyncio
async def test_validator_exception_fails_closed(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Vx")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    with patch.object(service.order_validator, "validate", side_effect=RuntimeError("boom")):
        result = service.validate_order(proposal)
    assert result.valid is False
    assert result.reason_code == codes.ORDER_VALIDATION_ERROR
    assert proposal.status == TradeProposalStatus.VALIDATION_REJECTED


@pytest.mark.asyncio
async def test_router_exception_fails_closed(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Ro")
    make_global_policy(db_session, require_stop_loss=False)
    service = _service(db_session)
    proposal = service.create_proposal(
        valid_limit_proposal(account, stop_loss_price=None)
    )
    service.evaluate_risk(proposal)
    service.validate_order(proposal)
    with patch.object(
        service.broker_router,
        "_route_and_submit_inner",
        side_effect=RuntimeError("boom"),
    ):
        route = await service.route(proposal)
    assert route.success is False
    assert route.reason_code == codes.BROKER_ROUTER_ERROR
    assert (db_session.scalar(select(func.count()).select_from(Order)) or 0) == 0


# ---------------------------------------------------------------------------
# Policy resolution + simulation broker unit
# ---------------------------------------------------------------------------


def test_risk_policy_resolution_strictest_wins(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Pol")
    strategy = make_strategy(db_session, name="Pol-S")
    assignment = make_assignment(db_session, strategy=strategy, account=account)

    db_session.add(
        RiskPolicy(
            scope_type=RiskScopeType.GLOBAL,
            scope_id=None,
            max_order_value=Decimal("10000"),
            require_stop_loss=False,
            is_enabled=True,
        )
    )
    db_session.add(
        RiskPolicy(
            scope_type=RiskScopeType.BROKER_ACCOUNT,
            scope_id=account.id,
            max_order_value=Decimal("5000"),
            require_stop_loss=False,
            is_enabled=True,
        )
    )
    db_session.add(
        RiskPolicy(
            scope_type=RiskScopeType.STRATEGY,
            scope_id=strategy.id,
            max_order_value=Decimal("2000"),
            require_stop_loss=True,
            is_enabled=True,
        )
    )
    db_session.flush()

    limits = RiskPolicyResolver(db_session).resolve(
        broker_account_id=account.id,
        strategy_id=strategy.id,
        assignment=assignment,
    )
    assert limits.max_order_value == Decimal("2000")
    assert limits.require_stop_loss is True


@pytest.mark.asyncio
async def test_simulation_broker_no_network_and_no_autofill() -> None:
    broker = SimulationBroker()
    assert broker.provider_name == "simulation"
    order = await broker.place_order(
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            order_type=BrokerOrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            limit_price=Decimal("10"),
            metadata={"trading_mode": "paper"},
        )
    )
    assert order.id.startswith("sim_")
    assert order.status.value == "submitted"
    assert order.filled_quantity == Decimal("0")
    quote = await broker.get_quote("AAPL")
    assert quote.last is None
    assert quote.raw.get("available") is False
    # Ensure module does not pull httpx for network.
    import app.brokers.adapters.simulation as sim_mod

    assert not hasattr(sim_mod, "httpx")
    assert not hasattr(sim_mod, "requests")
