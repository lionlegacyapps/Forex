"""OPTIONAL mutating Alpaca PAPER order test.

Requires BOTH credentials AND:
  ALLOW_ALPACA_PAPER_ORDER_TEST=true

Without the explicit flag: SKIP — credentials alone are not permission to submit.

Places at most ONE far-from-market limit order on paper-api only, then cancels
that specific order via test-only cleanup (DELETE limited to that broker_order_id).
"""

from __future__ import annotations

import os
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import Session

from app.broker_state.readers.alpaca_paper import ALPACA_PAPER_BASE_URL, assert_paper_base_url
from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter
from app.brokers.execution.client_order_id import build_client_order_id
from app.core.config import get_settings
from app.models.enums import TradingMode
from app.trading.proposals.service import TradeProposalService
from app.trading.routing.router import BrokerRouter
from tests.pipeline_helpers import (
    make_assignment,
    make_global_policy,
    make_simulation_account,
    make_strategy,
    valid_limit_proposal,
)


def _allowed() -> bool:
    return os.getenv("ALLOW_ALPACA_PAPER_ORDER_TEST", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _credentials() -> tuple[str, str] | None:
    get_settings.cache_clear()
    settings = get_settings()
    key = (settings.alpaca_api_key or os.getenv("ALPACA_API_KEY") or "").strip()
    secret = (settings.alpaca_api_secret or os.getenv("ALPACA_API_SECRET") or "").strip()
    if not key or not secret:
        return None
    return key, secret


async def _test_only_cancel(broker_order_id: str, *, api_key: str, api_secret: str) -> None:
    """Tightly scoped cleanup — cancels ONLY the given paper broker order id."""
    base = assert_paper_base_url(ALPACA_PAPER_BASE_URL)
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.delete(f"{base}/v2/orders/{broker_order_id}", headers=headers)


@pytest.mark.asyncio
async def test_alpaca_paper_order_submit_optional(db_session: Session) -> None:
    if not _allowed():
        pytest.skip("ALLOW_ALPACA_PAPER_ORDER_TEST not set — refusing to place paper order")

    creds = _credentials()
    if creds is None:
        pytest.skip("ALPACA credentials not configured")

    key, secret = creds
    adapter = AlpacaPaperExecutionAdapter(
        api_key=key,
        api_secret=secret,
        timeout_seconds=20.0,
        skip_buying_power_check=False,
    )
    assert not hasattr(adapter, "cancel_order")

    account = make_simulation_account(
        db_session,
        name="Alpaca-Paper-Mut-Test",
        broker="alpaca",
        enabled=True,
        trading_mode=TradingMode.PAPER,
    )
    strategy = make_strategy(db_session, name="Alpaca-Mut-Strat")
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session, require_stop_loss=False)

    router = BrokerRouter(
        db_session,
        execution_adapters={"alpaca": adapter},
        adapters={},
    )
    svc = TradeProposalService(db_session, broker_router=router)

    # Far-from-market buy limit — unlikely to fill
    result = await svc.create_and_process(
        valid_limit_proposal(
            account,
            strategy_id=strategy.id,
            symbol="AAPL",
            quantity=Decimal("1"),
            limit_price=Decimal("1.00"),
            stop_loss_price=None,
        )
    )
    assert result.submitted is True
    assert result.broker_order_id
    assert result.route is not None
    assert result.route.details.get("live") is False
    assert result.route.details.get("paper") is True

    # Visible via read path / client_order_id correlation
    from app.models.order import Order
    import uuid

    order = db_session.get(Order, uuid.UUID(result.route.order_id))
    assert order is not None
    coid = build_client_order_id(order.id)
    found = await adapter.get_order_by_client_order_id(coid)
    assert found is not None
    assert found["id"] == result.broker_order_id

    # Cleanup ONLY this order
    await _test_only_cancel(result.broker_order_id, api_key=key, api_secret=secret)
