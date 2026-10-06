"""Version 1 trading schema integration tests (PostgreSQL via DATABASE_URL)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AssetClass,
    AuditEvent,
    BrokerAccount,
    Execution,
    MarketMemoryEvent,
    Order,
    OrderStatus,
    OrderType,
    Position,
    PositionStatus,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    StrategyAccountAssignment,
    StrategyStatus,
    TradeProposal,
    TradeProposalStatus,
    TradeSide,
    TradingMode,
)


def test_broker_account_defaults_to_paper(db_session: Session) -> None:
    account = BrokerAccount(name="Paper Main", broker="alpaca")
    db_session.add(account)
    db_session.flush()

    assert account.trading_mode == TradingMode.PAPER
    assert account.is_enabled is True
    assert account.id is not None
    assert account.created_at is not None
    assert account.updated_at is not None


def test_strategy_creation(db_session: Session) -> None:
    strategy = Strategy(
        name="MeanReversion-A",
        description="Placeholder strategy metadata",
        strategy_type="mean_reversion",
    )
    db_session.add(strategy)
    db_session.flush()

    assert strategy.status == StrategyStatus.DEVELOPMENT
    assert strategy.version == "0.1.0"


def test_strategy_account_assignment_and_duplicate_prevention(db_session: Session) -> None:
    account = BrokerAccount(name="Acct", broker="alpaca")
    strategy = Strategy(name="Trend-A", strategy_type="trend")
    db_session.add_all([account, strategy])
    db_session.flush()

    assignment = StrategyAccountAssignment(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        capital_allocation=Decimal("10000.00"),
    )
    db_session.add(assignment)
    db_session.flush()

    assert assignment.trading_mode == TradingMode.PAPER
    assert assignment.is_enabled is True

    with db_session.begin_nested():
        duplicate = StrategyAccountAssignment(
            strategy_id=strategy.id,
            broker_account_id=account.id,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_trade_proposal_order_and_multiple_executions(db_session: Session) -> None:
    account = BrokerAccount(name="Live-Sim", broker="tradovate")
    strategy = Strategy(name="Breakout-A", strategy_type="breakout")
    db_session.add_all([account, strategy])
    db_session.flush()

    proposal = TradeProposal(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        source="strategy",
        symbol="EURUSD",
        asset_class=AssetClass.FOREX,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("100000"),
        metadata_={"note": "schema test"},
    )
    db_session.add(proposal)
    db_session.flush()
    assert proposal.status == TradeProposalStatus.PENDING

    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        symbol="EURUSD",
        asset_class=AssetClass.FOREX,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("100000"),
        status=OrderStatus.PARTIALLY_FILLED,
    )
    db_session.add(order)
    db_session.flush()

    fill_a = Execution(
        order_id=order.id,
        quantity=Decimal("40000"),
        price=Decimal("1.08510"),
        commission=Decimal("0.50"),
    )
    fill_b = Execution(
        order_id=order.id,
        quantity=Decimal("60000"),
        price=Decimal("1.08520"),
        commission=Decimal("0.75"),
    )
    db_session.add_all([fill_a, fill_b])
    db_session.flush()

    db_session.refresh(order)
    assert len(order.executions) == 2
    assert order.trade_proposal_id == proposal.id


def test_position_creation_strategy_aware(db_session: Session) -> None:
    account = BrokerAccount(name="Pos-Acct", broker="ibkr")
    strategy_a = Strategy(name="Pos-Strat-A", strategy_type="scalp")
    strategy_b = Strategy(name="Pos-Strat-B", strategy_type="swing")
    db_session.add_all([account, strategy_a, strategy_b])
    db_session.flush()

    pos_a = Position(
        broker_account_id=account.id,
        strategy_id=strategy_a.id,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("10"),
        average_entry_price=Decimal("190.50"),
    )
    pos_b = Position(
        broker_account_id=account.id,
        strategy_id=strategy_b.id,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("5"),
        average_entry_price=Decimal("191.00"),
    )
    db_session.add_all([pos_a, pos_b])
    db_session.flush()

    assert pos_a.status == PositionStatus.OPEN
    assert pos_a.realized_pnl == Decimal("0")
    assert pos_a.id != pos_b.id


def test_risk_policy_audit_and_market_memory(db_session: Session) -> None:
    account = BrokerAccount(name="Risk-Acct", broker="alpaca")
    strategy = Strategy(name="Risk-Strat", strategy_type="ml")
    db_session.add_all([account, strategy])
    db_session.flush()

    proposal = TradeProposal(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        source="manual",
        symbol="BTCUSD",
        asset_class=AssetClass.CRYPTO,
        side=TradeSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.25"),
        limit_price=Decimal("65000"),
    )
    db_session.add(proposal)
    db_session.flush()

    policy = RiskPolicy(
        scope_type=RiskScopeType.GLOBAL,
        max_daily_loss=Decimal("1000"),
        max_open_positions=10,
        require_stop_loss=True,
    )
    audit = AuditEvent(
        event_type="trade_proposal.created",
        entity_type="trade_proposal",
        entity_id=proposal.id,
        actor_type="user",
        actor_reference="owner",
        details={"symbol": "BTCUSD"},
    )
    memory = MarketMemoryEvent(
        symbol="BTCUSD",
        asset_class=AssetClass.CRYPTO,
        event_type="signal_context",
        market_context={"regime": "high_vol"},
        source="manual",
        strategy_id=strategy.id,
        trade_proposal_id=proposal.id,
    )
    db_session.add_all([policy, audit, memory])
    db_session.flush()

    assert policy.is_enabled is True
    assert policy.scope_id is None
    assert audit.details["symbol"] == "BTCUSD"
    assert memory.outcome is None


def test_broker_account_delete_restricted_when_orders_exist(db_session: Session) -> None:
    account = BrokerAccount(name="Restrict-Acct", broker="alpaca")
    db_session.add(account)
    db_session.flush()

    proposal = TradeProposal(
        broker_account_id=account.id,
        source="manual",
        symbol="SPY",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    db_session.add(proposal)
    db_session.flush()

    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        symbol="SPY",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )
    db_session.add(order)
    db_session.flush()

    with db_session.begin_nested():
        db_session.delete(account)
        with pytest.raises(IntegrityError):
            db_session.flush()
