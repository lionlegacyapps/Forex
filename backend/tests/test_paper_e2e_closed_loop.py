"""End-to-end closed loop: execution → accounting → PnL → risk feedback."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssetClass,
    AuditEvent,
    OrderType,
    Position,
    PositionStatus,
    ProposalSource,
    TradeProposalStatus,
    TradeSide,
)
from app.trading.execution.daily_pnl import DailyPnlService
from app.trading.execution.market_data import SimulationMarketData
from app.trading.execution.position_accounting import PositionAccountingService
from app.trading.proposals.schemas import CreateTradeProposalInput
from app.trading.proposals.service import TradeProposalService
from app.trading.risk import codes
from tests.pipeline_helpers import make_global_policy, make_simulation_account, valid_limit_proposal


@pytest.fixture()
def market() -> SimulationMarketData:
    md = SimulationMarketData()
    yield md
    md.clear_all()


@pytest.mark.asyncio
async def test_closed_loop_pnl_then_daily_loss_block(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="Loop-Acct")
    make_global_policy(
        db_session,
        require_stop_loss=True,
        max_daily_loss=Decimal("50"),
    )
    market.set_price("AAPL", Decimal("100"))
    service = TradeProposalService(db_session, market_data=market)

    buy = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("100"),
            stop_loss_price=Decimal("90"),
        )
    )
    assert buy.submitted is True
    assert buy.broker_order_id and buy.broker_order_id.startswith("sim_")
    assert buy.route and buy.route.details.get("filled") is True

    pos = db_session.scalars(
        select(Position).where(Position.status == PositionStatus.OPEN)
    ).one()
    assert pos.quantity == Decimal("10")
    assert pos.average_entry_price == Decimal("100")

    market.set_price("AAPL", Decimal("110"))
    upnl = PositionAccountingService(db_session).mark_position(pos, Decimal("110"))
    assert upnl == Decimal("100")

    sell = await service.create_and_process(
        CreateTradeProposalInput(
            broker_account_id=account.id,
            source=ProposalSource.MANUAL,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
            stop_loss_price=Decimal("1"),  # required by policy; irrelevant for sell exit
        )
    )
    assert sell.submitted is True
    assert sell.route and sell.route.details.get("filled") is True

    pos = db_session.get(Position, pos.id)
    assert pos.status == PositionStatus.CLOSED
    assert pos.realized_pnl == Decimal("100")

    daily = DailyPnlService(db_session).realized_pnl(broker_account_id=account.id)
    assert daily.realized_pnl == Decimal("100")

    events = {e.event_type for e in db_session.scalars(select(AuditEvent)).all()}
    assert "SIM_ORDER_FILLED" in events
    assert "POSITION_OPENED" in events
    assert "POSITION_CLOSED" in events
    assert "EXECUTION_RECORDED" in events

    # Losing path reaches daily loss limit, then next proposal rejected.
    market.set_price("MSFT", Decimal("50"))
    loser_buy = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("50"),
            stop_loss_price=Decimal("40"),
            symbol="MSFT",
        )
    )
    assert loser_buy.submitted is True
    market.set_price("MSFT", Decimal("40"))
    loser_sell = await service.create_and_process(
        CreateTradeProposalInput(
            broker_account_id=account.id,
            source=ProposalSource.MANUAL,
            symbol="MSFT",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
            stop_loss_price=Decimal("1"),
        )
    )
    assert loser_sell.submitted is True
    # Day PnL: +100 + (40-50)*10 = +100 - 100 = 0 — need a loss that hits 50.
    # Adjust: sell already realized -100 on MSFT; combined day PnL = 0.
    # Force additional loss:
    market.set_price("TSLA", Decimal("20"))
    await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("20"),
            stop_loss_price=Decimal("10"),
            symbol="TSLA",
        )
    )
    market.set_price("TSLA", Decimal("10"))
    await service.create_and_process(
        CreateTradeProposalInput(
            broker_account_id=account.id,
            source=ProposalSource.MANUAL,
            symbol="TSLA",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
            stop_loss_price=Decimal("1"),
        )
    )
    # Day: 100 - 100 - 100 = -100 <= -50
    blocked = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("10"),
            stop_loss_price=Decimal("5"),
            symbol="NVDA",
        )
    )
    assert blocked.status == TradeProposalStatus.RISK_REJECTED
    assert blocked.risk and blocked.risk.reason_code == codes.DAILY_LOSS_LIMIT_REACHED
    assert blocked.submitted is False
