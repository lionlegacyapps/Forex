"""Paper execution fill logic and position accounting tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssetClass,
    Execution,
    Order,
    OrderStatus,
    OrderType,
    Position,
    PositionStatus,
    ProposalSource,
    TradeProposal,
    TradeProposalStatus,
    TradeSide,
)
from app.trading.execution.fill_logic import evaluate_fill
from app.trading.execution.market_data import SimulationMarketData
from app.trading.execution.order_transitions import assert_order_transition, can_order_transition
from app.trading.execution.position_accounting import PositionAccountingService
from app.trading.execution.service import PaperExecutionService
from app.trading.proposals.service import TradeProposalService
from tests.pipeline_helpers import (
    make_global_policy,
    make_simulation_account,
    valid_limit_proposal,
)


@pytest.fixture()
def market() -> SimulationMarketData:
    md = SimulationMarketData()
    yield md
    md.clear_all()


def _submitted_order(
    session: Session,
    account,
    *,
    side: TradeSide = TradeSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    qty: Decimal = Decimal("10"),
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    symbol: str = "AAPL",
) -> Order:
    proposal = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        side=side,
        order_type=order_type,
        quantity=qty,
        limit_price=limit_price,
        stop_price=stop_price,
        status=TradeProposalStatus.SUBMITTED,
    )
    session.add(proposal)
    session.flush()
    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        broker_order_id=f"sim_test_{proposal.id}",
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        side=side,
        order_type=order_type,
        quantity=qty,
        limit_price=limit_price,
        stop_price=stop_price,
        status=OrderStatus.SUBMITTED,
    )
    session.add(order)
    session.flush()
    return order


def test_fill_rules_limit_stop(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Fill-Rules")
    buy_limit = _submitted_order(
        db_session,
        account,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("100"),
    )
    assert evaluate_fill(buy_limit, Decimal("99")).eligible is True
    assert evaluate_fill(buy_limit, Decimal("101")).eligible is False

    sell_limit = _submitted_order(
        db_session,
        account,
        side=TradeSide.SELL,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("100"),
        symbol="MSFT",
    )
    assert evaluate_fill(sell_limit, Decimal("101")).eligible is True
    assert evaluate_fill(sell_limit, Decimal("99")).eligible is False

    buy_stop = _submitted_order(
        db_session,
        account,
        order_type=OrderType.STOP,
        stop_price=Decimal("100"),
        symbol="GOOG",
    )
    assert evaluate_fill(buy_stop, Decimal("100")).eligible is True
    assert evaluate_fill(buy_stop, Decimal("99")).eligible is False

    sell_stop = _submitted_order(
        db_session,
        account,
        side=TradeSide.SELL,
        order_type=OrderType.STOP,
        stop_price=Decimal("100"),
        symbol="AMZN",
    )
    assert evaluate_fill(sell_stop, Decimal("100")).eligible is True
    assert evaluate_fill(sell_stop, Decimal("101")).eligible is False

    stop_limit = _submitted_order(
        db_session,
        account,
        order_type=OrderType.STOP_LIMIT,
        stop_price=Decimal("100"),
        limit_price=Decimal("101"),
        symbol="META",
    )
    assert evaluate_fill(stop_limit, Decimal("100.5")).eligible is True
    assert evaluate_fill(stop_limit, Decimal("99")).eligible is False
    assert evaluate_fill(stop_limit, Decimal("102")).eligible is False


def test_price_unavailable_no_fill(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="NoPx")
    order = _submitted_order(db_session, account)
    svc = PaperExecutionService(db_session, market_data=market)
    result = svc.process_submitted_order(order)
    assert result.filled is False
    assert result.reason_code == "PRICE_UNAVAILABLE"
    assert order.status == OrderStatus.SUBMITTED
    assert db_session.scalars(select(Execution)).first() is None


def test_market_buy_and_sell_fill(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="MktFill")
    market.set_price("AAPL", Decimal("100"))
    svc = PaperExecutionService(db_session, market_data=market)

    buy = _submitted_order(db_session, account, side=TradeSide.BUY)
    assert svc.process_submitted_order(buy).filled is True
    assert buy.status == OrderStatus.FILLED
    pos = db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)).one()
    assert pos.quantity == Decimal("10")
    assert pos.average_entry_price == Decimal("100")

    sell = _submitted_order(db_session, account, side=TradeSide.SELL, symbol="AAPL")
    fill = svc.process_submitted_order(sell)
    assert fill.filled is True
    assert fill.realized_pnl == Decimal("0")  # flat exit at same price
    pos = db_session.get(Position, pos.id)
    assert pos.status == PositionStatus.CLOSED


def test_long_add_partial_close_avg(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LongAvg")
    market.set_price("AAPL", Decimal("100"))
    svc = PaperExecutionService(db_session, market_data=market)
    svc.process_submitted_order(
        _submitted_order(db_session, account, qty=Decimal("10"))
    )
    market.set_price("AAPL", Decimal("120"))
    svc.process_submitted_order(
        _submitted_order(db_session, account, qty=Decimal("10"), symbol="AAPL")
    )
    pos = db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)).one()
    assert pos.quantity == Decimal("20")
    assert pos.average_entry_price == Decimal("110")

    market.set_price("AAPL", Decimal("130"))
    fill = svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.SELL, qty=Decimal("5"), symbol="AAPL")
    )
    # (130-110)*5 = 100
    assert fill.realized_pnl == Decimal("100")
    pos = db_session.get(Position, pos.id)
    assert pos.quantity == Decimal("15")
    assert pos.average_entry_price == Decimal("110")


def test_short_open_add_cover(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="ShortAvg")
    market.set_price("AAPL", Decimal("100"))
    svc = PaperExecutionService(db_session, market_data=market)
    svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.SELL, qty=Decimal("10"))
    )
    pos = db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)).one()
    assert pos.quantity == Decimal("-10")
    market.set_price("AAPL", Decimal("90"))
    svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.SELL, qty=Decimal("10"), symbol="AAPL")
    )
    pos = db_session.get(Position, pos.id)
    assert pos.quantity == Decimal("-20")
    assert pos.average_entry_price == Decimal("95")

    market.set_price("AAPL", Decimal("80"))
    fill = svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.BUY, qty=Decimal("5"), symbol="AAPL")
    )
    # (95-80)*5 = 75
    assert fill.realized_pnl == Decimal("75")


def test_long_to_short_and_short_to_long_reversal(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="Rev")
    market.set_price("AAPL", Decimal("100"))
    svc = PaperExecutionService(db_session, market_data=market)
    svc.process_submitted_order(_submitted_order(db_session, account, qty=Decimal("5")))
    market.set_price("AAPL", Decimal("120"))
    fill = svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.SELL, qty=Decimal("8"), symbol="AAPL")
    )
    # close 5: (120-100)*5 = 100; open short 3 @ 120
    assert fill.realized_pnl == Decimal("100")
    pos = db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)).one()
    assert pos.quantity == Decimal("-3")
    assert pos.average_entry_price == Decimal("120")

    market.set_price("AAPL", Decimal("100"))
    fill2 = svc.process_submitted_order(
        _submitted_order(db_session, account, side=TradeSide.BUY, qty=Decimal("8"), symbol="AAPL")
    )
    # close short 3: (120-100)*3 = 60; open long 5 @ 100
    assert fill2.realized_pnl == Decimal("60")
    pos = db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)).one()
    assert pos.quantity == Decimal("5")
    assert pos.average_entry_price == Decimal("100")


def test_unrealized_known_and_unknown(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="UPnl")
    market.set_price("AAPL", Decimal("100"))
    svc = PaperExecutionService(db_session, market_data=market)
    svc.process_submitted_order(_submitted_order(db_session, account, qty=Decimal("10")))
    pos = db_session.scalars(select(Position)).one()
    acct = PositionAccountingService(db_session)
    upnl = acct.mark_position(pos, Decimal("110"))
    assert upnl == Decimal("100")
    unknown = acct.mark_position(pos, None)
    assert unknown is None
    assert pos.current_price is None


def test_strategies_and_accounts_isolated(market: SimulationMarketData, db_session: Session) -> None:
    from tests.pipeline_helpers import make_assignment, make_strategy

    a1 = make_simulation_account(db_session, name="Iso-A1")
    a2 = make_simulation_account(db_session, name="Iso-A2")
    s1 = make_strategy(db_session, name="Iso-S1", version="1")
    s2 = make_strategy(db_session, name="Iso-S2", version="1")
    make_assignment(db_session, strategy=s1, account=a1)
    make_assignment(db_session, strategy=s2, account=a1)
    market.set_price("AAPL", Decimal("50"))
    svc = PaperExecutionService(db_session, market_data=market)

    def order_for(account, strategy_id, symbol="AAPL"):
        p = TradeProposal(
            broker_account_id=account.id,
            strategy_id=strategy_id,
            source=ProposalSource.STRATEGY if strategy_id is not None else ProposalSource.MANUAL,
            symbol=symbol,
            asset_class=AssetClass.EQUITY,
            side=TradeSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            status=TradeProposalStatus.SUBMITTED,
        )
        db_session.add(p)
        db_session.flush()
        o = Order(
            trade_proposal_id=p.id,
            broker_account_id=account.id,
            broker_order_id=f"sim_{p.id}",
            symbol=symbol,
            asset_class=AssetClass.EQUITY,
            side=TradeSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            status=OrderStatus.SUBMITTED,
        )
        db_session.add(o)
        db_session.flush()
        return o

    svc.process_submitted_order(order_for(a1, s1.id))
    svc.process_submitted_order(order_for(a1, s2.id))
    svc.process_submitted_order(order_for(a2, None))
    opens = list(db_session.scalars(select(Position).where(Position.status == PositionStatus.OPEN)))
    assert len(opens) == 3


def test_execution_idempotent(market: SimulationMarketData, db_session: Session) -> None:
    account = make_simulation_account(db_session, name="IdemExec")
    market.set_price("AAPL", Decimal("10"))
    order = _submitted_order(db_session, account, qty=Decimal("2"))
    svc = PaperExecutionService(db_session, market_data=market)
    assert svc.process_submitted_order(order).filled is True
    execution = db_session.scalars(select(Execution)).one()
    acct = PositionAccountingService(db_session)
    again = acct.apply_execution(
        execution, order=order, strategy_id=None, mark_price=Decimal("10")
    )
    assert again.already_applied is True
    pos = db_session.scalars(select(Position)).one()
    assert pos.quantity == Decimal("2")


def test_illegal_order_transitions() -> None:
    assert can_order_transition(OrderStatus.FILLED, OrderStatus.SUBMITTED) is False
    assert can_order_transition(OrderStatus.CANCELLED, OrderStatus.FILLED) is False
    with pytest.raises(Exception):
        assert_order_transition(OrderStatus.REJECTED, OrderStatus.SUBMITTED)


@pytest.mark.asyncio
async def test_buy_limit_pipeline_fill_and_no_fill(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="LimPipe")
    make_global_policy(db_session, require_stop_loss=False)
    market.set_price("AAPL", Decimal("100"))
    service = TradeProposalService(db_session, market_data=market)
    ok = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("100"),
            stop_loss_price=None,
        )
    )
    assert ok.submitted is True
    assert ok.route and ok.route.details.get("filled") is True

    market.set_price("AAPL", Decimal("101"))
    nofill = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("100"),
            stop_loss_price=None,
            symbol="AAPL",
        )
    )
    assert nofill.submitted is True
    assert nofill.route and nofill.route.details.get("filled") is False
