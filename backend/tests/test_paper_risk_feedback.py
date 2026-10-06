"""Risk Engine feedback from paper accounting (daily loss, exposure, open slots)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import OrderType, Position, PositionStatus, RiskPolicy, RiskScopeType, TradeProposalStatus
from app.models.enums import AssetClass
from app.trading.execution.market_data import SimulationMarketData
from app.trading.proposals.schemas import CreateTradeProposalInput
from app.trading.proposals.service import TradeProposalService
from app.trading.risk import codes
from app.models import ProposalSource, TradeSide
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


@pytest.mark.asyncio
async def test_daily_loss_limit_blocks_next_trade(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="DL-Acct")
    make_global_policy(
        db_session,
        require_stop_loss=False,
        max_daily_loss=Decimal("50"),
    )
    market.set_price("AAPL", Decimal("100"))
    service = TradeProposalService(db_session, market_data=market)

    buy = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("100"),
            stop_loss_price=None,
        )
    )
    assert buy.submitted and buy.route and buy.route.details.get("filled")

    market.set_price("AAPL", Decimal("90"))
    sell = await service.create_and_process(
        CreateTradeProposalInput(
            broker_account_id=account.id,
            source=ProposalSource.MANUAL,
            symbol="AAPL",
            asset_class=AssetClass.EQUITY,
            side=TradeSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
        )
    )
    assert sell.submitted and sell.route and sell.route.details.get("filled")
    # Realized loss = (90-100)*10 = -100 <= -50

    blocked = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("90"),
            stop_loss_price=None,
            symbol="MSFT",
        )
    )
    # Need price for MSFT for other checks? limit has price. Daily loss should reject.
    assert blocked.status == TradeProposalStatus.RISK_REJECTED
    assert blocked.risk and blocked.risk.reason_code == codes.DAILY_LOSS_LIMIT_REACHED


@pytest.mark.asyncio
async def test_open_position_limit_add_vs_new(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="OPL2")
    make_global_policy(
        db_session, require_stop_loss=False, max_open_positions=1
    )
    market.set_price("AAPL", Decimal("10"))
    market.set_price("MSFT", Decimal("10"))
    service = TradeProposalService(db_session, market_data=market)

    first = await service.create_and_process(
        valid_limit_proposal(account, quantity=Decimal("1"), limit_price=Decimal("10"), stop_loss_price=None)
    )
    assert first.submitted

    # Add to same symbol — should pass open-position check
    add = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("10"),
            stop_loss_price=None,
            symbol="AAPL",
        )
    )
    assert add.risk and add.risk.approved

    # New symbol would open second position — reject
    other = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("1"),
            limit_price=Decimal("10"),
            stop_loss_price=None,
            symbol="MSFT",
        )
    )
    assert other.risk and other.risk.reason_code == codes.MAX_OPEN_POSITIONS_EXCEEDED


@pytest.mark.asyncio
async def test_max_total_exposure(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="Exp")
    db_session.add(
        RiskPolicy(
            scope_type=RiskScopeType.GLOBAL,
            scope_id=None,
            require_stop_loss=False,
            max_total_exposure=Decimal("1500"),
            is_enabled=True,
        )
    )
    db_session.flush()
    market.set_price("AAPL", Decimal("100"))
    service = TradeProposalService(db_session, market_data=market)

    ok = await service.create_and_process(
        valid_limit_proposal(
            account, quantity=Decimal("10"), limit_price=Decimal("100"), stop_loss_price=None
        )
    )
    assert ok.submitted  # 1000 exposure

    blocked = await service.create_and_process(
        valid_limit_proposal(
            account,
            quantity=Decimal("10"),
            limit_price=Decimal("100"),
            stop_loss_price=None,
            symbol="AAPL",
        )
    )
    # projected 1000 + 1000 = 2000 > 1500
    assert blocked.risk and blocked.risk.reason_code == codes.MAX_TOTAL_EXPOSURE_EXCEEDED


@pytest.mark.asyncio
async def test_market_order_value_with_and_without_sim_price(
    market: SimulationMarketData, db_session: Session
) -> None:
    account = make_simulation_account(db_session, name="MOV2")
    make_global_policy(
        db_session, require_stop_loss=False, max_order_value=Decimal("500")
    )
    service = TradeProposalService(db_session, market_data=market)

    # No sim price → NOT_EVALUATED for market
    payload = CreateTradeProposalInput(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
    )
    p = service.create_proposal(payload)
    d = service.evaluate_risk(p)
    assert d.approved is False
    assert d.reason_code in {
        codes.NOT_EVALUATED_MARKET_PRICE_REQUIRED,
        codes.PRICE_UNAVAILABLE,
    }

    market.set_price("AAPL", Decimal("100"))
    p2 = service.create_proposal(payload)
    d2 = service.evaluate_risk(p2)
    assert d2.approved is False
    assert d2.reason_code == codes.MAX_ORDER_VALUE_EXCEEDED
