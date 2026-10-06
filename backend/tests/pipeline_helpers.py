"""Shared helpers for trading safety pipeline tests."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    AccountType,
    AssetClass,
    BrokerAccount,
    OrderType,
    ProposalSource,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    StrategyAccountAssignment,
    StrategyStatus,
    TradeSide,
    TradingMode,
)
from app.trading.proposals.schemas import CreateTradeProposalInput


def make_simulation_account(
    session: Session,
    *,
    name: str = "Sim-Acct",
    enabled: bool = True,
    trading_mode: TradingMode = TradingMode.PAPER,
    broker: str = "simulation",
) -> BrokerAccount:
    account = BrokerAccount(
        name=name,
        broker=broker,
        account_type=AccountType.CASH,
        trading_mode=trading_mode,
        is_enabled=enabled,
    )
    session.add(account)
    session.flush()
    return account


def make_strategy(
    session: Session,
    *,
    name: str = "Pipe-Strat",
    status: StrategyStatus = StrategyStatus.PAPER,
    version: str = "1.0.0",
) -> Strategy:
    strategy = Strategy(
        name=name,
        strategy_type="test",
        version=version,
        status=status,
    )
    session.add(strategy)
    session.flush()
    return strategy


def make_assignment(
    session: Session,
    *,
    strategy: Strategy,
    account: BrokerAccount,
    enabled: bool = True,
    trading_mode: TradingMode = TradingMode.PAPER,
    max_position_size: Decimal | None = None,
    max_concurrent_positions: int | None = None,
) -> StrategyAccountAssignment:
    assignment = StrategyAccountAssignment(
        strategy_id=strategy.id,
        broker_account_id=account.id,
        is_enabled=enabled,
        trading_mode=trading_mode,
        max_position_size=max_position_size,
        max_concurrent_positions=max_concurrent_positions,
    )
    session.add(assignment)
    session.flush()
    return assignment


def make_global_policy(
    session: Session,
    *,
    require_stop_loss: bool = True,
    max_order_value: Decimal | None = None,
    max_open_positions: int | None = None,
    max_daily_loss: Decimal | None = None,
) -> RiskPolicy:
    policy = RiskPolicy(
        scope_type=RiskScopeType.GLOBAL,
        scope_id=None,
        require_stop_loss=require_stop_loss,
        max_order_value=max_order_value,
        max_open_positions=max_open_positions,
        max_daily_loss=max_daily_loss,
        is_enabled=True,
    )
    session.add(policy)
    session.flush()
    return policy


def valid_limit_proposal(
    account: BrokerAccount,
    *,
    strategy_id=None,
    quantity: Decimal = Decimal("10"),
    limit_price: Decimal = Decimal("100"),
    stop_loss_price: Decimal | None = Decimal("90"),
    symbol: str = "AAPL",
    order_type: OrderType = OrderType.LIMIT,
    side: TradeSide = TradeSide.BUY,
    stop_price: Decimal | None = None,
    idempotency_key: str | None = None,
) -> CreateTradeProposalInput:
    return CreateTradeProposalInput(
        broker_account_id=account.id,
        strategy_id=strategy_id,
        source=ProposalSource.MANUAL if strategy_id is None else ProposalSource.STRATEGY,
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price if order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} else None,
        stop_price=stop_price,
        stop_loss_price=stop_loss_price,
        idempotency_key=idempotency_key,
    )
