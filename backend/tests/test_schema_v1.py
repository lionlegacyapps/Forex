"""Hardened V1 schema integration tests against Supabase (transaction-rolled-back)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountType,
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
    ProposalSource,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    StrategyAccountAssignment,
    StrategyStatus,
    TimeInForce,
    TradeProposal,
    TradeProposalStatus,
    TradeSide,
    TradingMode,
)


def _account(name: str = "Acct") -> BrokerAccount:
    return BrokerAccount(
        name=name,
        broker="alpaca",
        account_type=AccountType.CASH,
    )


def test_broker_account_defaults_paper_and_disabled(db_session: Session) -> None:
    account = _account("Paper-Disabled")
    db_session.add(account)
    db_session.flush()
    assert account.trading_mode == TradingMode.PAPER
    assert account.is_enabled is False


def test_broker_account_type_required(db_session: Session) -> None:
    account = BrokerAccount(name="NoType", broker="alpaca")  # type: ignore[call-arg]
    # account_type omitted — DB/ORM must reject
    db_session.add(account)
    with pytest.raises((IntegrityError, TypeError, ValueError)):
        db_session.flush()


def test_assignment_defaults_paper_disabled_and_duplicate_rejected(db_session: Session) -> None:
    account = _account("Assign-Acct")
    strategy = Strategy(name="Assign-Strat", strategy_type="trend", version="1.0.0")
    db_session.add_all([account, strategy])
    db_session.flush()

    assignment = StrategyAccountAssignment(
        strategy_id=strategy.id,
        broker_account_id=account.id,
    )
    db_session.add(assignment)
    db_session.flush()
    assert assignment.trading_mode == TradingMode.PAPER
    assert assignment.is_enabled is False

    with db_session.begin_nested():
        db_session.add(
            StrategyAccountAssignment(
                strategy_id=strategy.id,
                broker_account_id=account.id,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_trade_proposal_quantity_and_stop_fields(db_session: Session) -> None:
    account = _account("Prop-Acct")
    strategy = Strategy(name="Prop-Strat", strategy_type="mr", version="1.0.0")
    db_session.add_all([account, strategy])
    db_session.flush()

    with db_session.begin_nested():
        bad = TradeProposal(
            strategy_id=strategy.id,
            broker_account_id=account.id,
            source=ProposalSource.STRATEGY,
            symbol="EURUSD",
            asset_class=AssetClass.FOREX,
            side=TradeSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0"),
        )
        db_session.add(bad)
        with pytest.raises(IntegrityError):
            db_session.flush()

    proposal = TradeProposal(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        source=ProposalSource.STRATEGY,
        symbol="EURUSD",
        asset_class=AssetClass.FOREX,
        side=TradeSide.BUY,
        order_type=OrderType.STOP_LIMIT,
        quantity=Decimal("1000"),
        stop_price=Decimal("1.0800"),
        limit_price=Decimal("1.0805"),
        stop_loss_price=Decimal("1.0700"),
    )
    db_session.add(proposal)
    db_session.flush()
    assert proposal.stop_price == Decimal("1.0800")
    assert proposal.stop_loss_price == Decimal("1.0700")
    assert proposal.status == TradeProposalStatus.PENDING


def test_order_tif_and_account_mismatch_rejected(db_session: Session) -> None:
    acct_a = _account("Ord-A")
    acct_b = BrokerAccount(name="Ord-B", broker="alpaca", account_type=AccountType.MARGIN)
    strategy = Strategy(name="Ord-Strat", strategy_type="breakout", version="1.0.0")
    db_session.add_all([acct_a, acct_b, strategy])
    db_session.flush()

    proposal = TradeProposal(
        strategy_id=strategy.id,
        broker_account_id=acct_a.id,
        source=ProposalSource.MANUAL,
        symbol="SPY",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
    )
    db_session.add(proposal)
    db_session.flush()

    good = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=acct_a.id,
        symbol="SPY",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        time_in_force=TimeInForce.GTC,
    )
    db_session.add(good)
    db_session.flush()
    assert good.time_in_force == TimeInForce.GTC
    assert good.status == OrderStatus.NEW

    with db_session.begin_nested():
        mismatch = Order(
            trade_proposal_id=proposal.id,
            broker_account_id=acct_b.id,  # wrong account vs proposal
            symbol="SPY",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        db_session.add(mismatch)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_multiple_executions_and_decimal_precision(db_session: Session) -> None:
    account = _account("Fill-Acct")
    db_session.add(account)
    db_session.flush()
    proposal = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.EXTERNAL,
        symbol="BTCUSD",
        asset_class=AssetClass.CRYPTO,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.12500000"),
        limit_price=Decimal("65000.12345678"),
    )
    db_session.add(proposal)
    db_session.flush()
    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        symbol="BTCUSD",
        asset_class=AssetClass.CRYPTO,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.12500000"),
        limit_price=Decimal("65000.12345678"),
        status=OrderStatus.PARTIALLY_FILLED,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add_all(
        [
            Execution(
                order_id=order.id,
                quantity=Decimal("0.05000000"),
                price=Decimal("65000.12345678"),
                commission=Decimal("0.01000000"),
            ),
            Execution(
                order_id=order.id,
                quantity=Decimal("0.07500000"),
                price=Decimal("65001.00000000"),
            ),
        ]
    )
    db_session.flush()
    db_session.refresh(order)
    assert len(order.executions) == 2
    assert order.executions[0].price == Decimal("65000.12345678")


def test_multi_strategy_same_symbol_positions(db_session: Session) -> None:
    account = _account("Pos-Acct")
    s1 = Strategy(name="Pos-S1", strategy_type="a", version="1")
    s2 = Strategy(name="Pos-S2", strategy_type="b", version="1")
    db_session.add_all([account, s1, s2])
    db_session.flush()
    db_session.add_all(
        [
            Position(
                broker_account_id=account.id,
                strategy_id=s1.id,
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("10"),
                average_entry_price=Decimal("100"),
            ),
            Position(
                broker_account_id=account.id,
                strategy_id=s2.id,
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("5"),
                average_entry_price=Decimal("101"),
            ),
        ]
    )
    db_session.flush()


def test_risk_policy_require_stop_loss_default_true(db_session: Session) -> None:
    policy = RiskPolicy(scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"))
    db_session.add(policy)
    db_session.flush()
    assert policy.require_stop_loss is True
    assert policy.is_enabled is True


def test_historical_fk_restrict_strategy_with_proposal(db_session: Session) -> None:
    account = _account("Hist-Acct")
    strategy = Strategy(name="Hist-Strat", strategy_type="x", version="1")
    db_session.add_all([account, strategy])
    db_session.flush()
    db_session.add(
        TradeProposal(
            strategy_id=strategy.id,
            broker_account_id=account.id,
            source=ProposalSource.STRATEGY,
            symbol="MSFT",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
    )
    db_session.flush()
    with db_session.begin_nested():
        db_session.delete(strategy)
        with pytest.raises(IntegrityError):
            db_session.flush()


def test_audit_and_market_memory_and_invalid_enum(db_session: Session) -> None:
    account = _account("Misc-Acct")
    strategy = Strategy(name="Misc-Strat", strategy_type="y", version="1")
    db_session.add_all([account, strategy])
    db_session.flush()
    proposal = TradeProposal(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        source=ProposalSource.AI,
        symbol="NVDA",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("2"),
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.add(
        AuditEvent(
            event_type="proposal.created",
            entity_type="trade_proposal",
            entity_id=proposal.id,
            actor_type="system",
            details={"ok": True},
        )
    )
    db_session.add(
        MarketMemoryEvent(
            symbol="NVDA",
            asset_class=AssetClass.EQUITY,
            event_type="context",
            market_context={"vol": "high"},
            source="test",
            strategy_id=strategy.id,
            trade_proposal_id=proposal.id,
        )
    )
    db_session.flush()

    # DB CHECK rejects invalid trading_mode (defense-in-depth beyond ORM Enum).
    nested = db_session.begin_nested()
    try:
        db_session.execute(
            text(
                "INSERT INTO broker_accounts"
                " (id, name, broker, account_type, trading_mode, is_enabled,"
                "  created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'BadModeRaw', 'alpaca', 'cash',"
                "  'xxxxx', false, now(), now())"
            )
        )
        nested.commit()
        pytest.fail("expected IntegrityError for invalid trading_mode")
    except IntegrityError:
        nested.rollback()
