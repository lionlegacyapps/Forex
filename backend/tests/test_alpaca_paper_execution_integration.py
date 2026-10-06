"""OPTIONAL mutating Alpaca PAPER order test.

Requires BOTH credentials AND:
  ALLOW_ALPACA_PAPER_ORDER_TEST=true

Without the explicit flag: SKIP — credentials alone are not permission to submit.

Places at most ONE far-from-market limit order on paper-api only, then cancels
that specific order via test-only cleanup (DELETE limited to that broker_order_id).
"""

from __future__ import annotations

import os
import uuid
from decimal import ROUND_DOWN, Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker_state.models import BrokerOrderSnapshot
from app.broker_state.readers.alpaca_paper import (
    ALPACA_PAPER_BASE_URL,
    AlpacaPaperAccountReader,
    assert_paper_base_url,
)
from app.broker_state.reconciliation import ReconciliationEngine
from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.fill_sync import AlpacaFillSyncService
from app.brokers.execution.status_map import map_alpaca_order_status
from app.core.config import get_settings
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.market_data.service import MarketDataService
from app.models.audit_event import AuditEvent
from app.models.enums import OrderStatus, TradingMode
from app.models.order import Order
from app.trading.execution.order_transitions import assert_order_transition
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


def _round_tick(price: Decimal) -> Decimal:
    """Round DOWN to $0.01 increment (valid for AAPL)."""
    return price.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


async def _test_only_cancel(broker_order_id: str, *, api_key: str, api_secret: str) -> None:
    """Tightly scoped cleanup — cancels ONLY the given paper broker order id."""
    base = assert_paper_base_url(ALPACA_PAPER_BASE_URL)
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.delete(f"{base}/v2/orders/{broker_order_id}", headers=headers)
        if response.status_code not in {200, 204}:
            raise AssertionError(
                f"Test cleanup cancel failed HTTP {response.status_code} for {broker_order_id}"
            )


@pytest.mark.asyncio
async def test_alpaca_paper_order_submit_optional(db_session: Session) -> None:
    if not _allowed():
        pytest.skip("ALLOW_ALPACA_PAPER_ORDER_TEST not set — refusing to place paper order")

    creds = _credentials()
    if creds is None:
        pytest.skip("ALPACA credentials not configured")

    key, secret = creds

    # --- Pre-flight: paper host lock ---
    paper_url = assert_paper_base_url(ALPACA_PAPER_BASE_URL)
    assert "paper-api.alpaca.markets" in paper_url
    assert paper_url.rstrip("/") == "https://paper-api.alpaca.markets"

    reader = AlpacaPaperAccountReader(api_key=key, api_secret=secret, timeout_seconds=20.0)
    account_snap = await reader.get_account()
    assert account_snap.paper_verified is True
    assert account_snap.account_blocked is False
    assert account_snap.trading_blocked is False
    assert account_snap.buying_power is not None
    assert account_snap.buying_power > 0

    # Fresh market data for AAPL
    md_provider = AlpacaMarketDataProvider(api_key=key, api_secret=secret, timeout_seconds=15.0)
    mds = MarketDataService(md_provider, enforce_freshness=True)
    quote = await mds.get_quote("AAPL", enforce_freshness=True)
    ref = await mds.get_reference_price("AAPL", enforce_freshness=True)
    assert ref.price > 0
    reference_price = ref.price
    bid = quote.bid_price

    # Limit ~20% below reference, rounded down to $0.01
    raw_limit = reference_price * Decimal("0.80")
    limit_price = _round_tick(raw_limit)
    assert limit_price > 0
    assert limit_price < reference_price
    if bid is not None:
        assert limit_price < bid, "Limit must be below current bid (non-marketable)"

    # Buying power for 1 share at limit
    assert account_snap.buying_power >= limit_price

    adapter = AlpacaPaperExecutionAdapter(
        api_key=key,
        api_secret=secret,
        timeout_seconds=20.0,
        market_data_service=mds,
        skip_buying_power_check=False,
    )
    assert not hasattr(adapter, "cancel_order")
    assert not hasattr(adapter, "client")

    account = make_simulation_account(
        db_session,
        name="Alpaca-Paper-Mut-Test",
        broker="alpaca",
        enabled=True,
        trading_mode=TradingMode.PAPER,
    )
    assert account.broker == "alpaca"
    assert account.trading_mode == TradingMode.PAPER
    assert account.is_enabled is True

    strategy = make_strategy(db_session, name="Alpaca-Mut-Strat")
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session, require_stop_loss=False)

    router = BrokerRouter(
        db_session,
        execution_adapters={"alpaca": adapter},
        adapters={},
    )
    svc = TradeProposalService(
        db_session,
        broker_router=router,
        market_data_service=mds,
    )

    # Persist prices for the report artifact (no secrets)
    os.environ["__TEST_REF_PRICE"] = str(reference_price)
    os.environ["__TEST_LIMIT_PRICE"] = str(limit_price)
    os.environ["__TEST_BID"] = str(bid) if bid is not None else ""

    result = await svc.create_and_process(
        valid_limit_proposal(
            account,
            strategy_id=strategy.id,
            symbol="AAPL",
            quantity=Decimal("1"),
            limit_price=limit_price,
            stop_loss_price=None,
        )
    )

    # Risk + validation must have passed for submission
    assert result.risk is not None and result.risk.approved is True
    assert result.validation is not None and result.validation.valid is True
    assert result.submitted is True
    assert result.broker_order_id
    assert result.route is not None
    assert result.route.details.get("live") is False
    assert result.route.details.get("paper") is True

    order = db_session.get(Order, uuid.UUID(result.route.order_id))
    assert order is not None
    assert order.broker_account_id == account.id
    assert order.trade_proposal_id == result.proposal_id
    assert order.broker_order_id == result.broker_order_id
    assert order.symbol == "AAPL"
    assert order.side.value == "buy"
    assert order.quantity == Decimal("1")
    assert order.order_type.value == "limit"
    assert order.time_in_force.value == "day"
    assert order.limit_price == limit_price
    assert order.submitted_at is not None

    coid = build_client_order_id(order.id)
    # Primary read-path: fetch by broker_order_id
    found = await adapter.get_order_by_id(result.broker_order_id)
    assert found is not None
    assert found["id"] == result.broker_order_id
    assert str(found.get("client_order_id") or "") == coid
    assert str(found.get("symbol") or "").upper() == "AAPL"
    assert str(found.get("side") or "").lower() == "buy"
    assert Decimal(str(found.get("qty"))) == Decimal("1")
    assert str(found.get("type") or "").lower() == "limit"
    assert str(found.get("time_in_force") or "").lower() == "day"

    # Secondary: client_order_id correlation via adapter lookup (list fallback)
    by_coid = await adapter.get_order_by_client_order_id(coid)
    assert by_coid is not None
    assert by_coid["id"] == result.broker_order_id

    filled_qty = Decimal(str(found.get("filled_qty") or "0"))
    broker_status = str(found.get("status") or "").lower()
    unexpectedly_filled = filled_qty > 0 or broker_status == "filled"
    os.environ["__TEST_FILLED"] = "1" if unexpectedly_filled else "0"
    os.environ["__TEST_BROKER_STATUS"] = broker_status

    # Reconciliation before cleanup
    broker_orders = [
        BrokerOrderSnapshot(
            broker_order_id=result.broker_order_id,
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("1"),
            filled_quantity=filled_qty,
            status=map_alpaca_order_status(broker_status).value,
            limit_price=limit_price,
        )
    ]
    report = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id=account_snap.external_account_id,
        broker_positions=[],
        broker_orders=broker_orders,
    )
    assert report.mutations == 0
    order_findings = [f for f in report.findings if f.broker_order_id == result.broker_order_id]
    assert any(f.category.value == "MATCH" for f in order_findings)

    if unexpectedly_filled:
        payload = await adapter.get_order_by_id(result.broker_order_id)
        AlpacaFillSyncService(db_session).apply_broker_order_snapshot(order, payload)
        db_session.flush()
        pytest.fail(
            "UNEXPECTED PAPER FILL: order filled despite far-from-market limit; "
            "fill synced to internal accounting; no offsetting trade placed"
        )

    # Cleanup ONLY this broker_order_id
    await _test_only_cancel(result.broker_order_id, api_key=key, api_secret=secret)

    cancelled = await adapter.get_order_by_id(result.broker_order_id)
    cancel_status = str(cancelled.get("status") or "").lower()
    assert cancel_status in {"canceled", "cancelled"}
    os.environ["__TEST_CANCEL_STATUS"] = cancel_status

    mapped = map_alpaca_order_status(cancel_status)
    if order.status != mapped and order.status == OrderStatus.SUBMITTED:
        assert_order_transition(order.status, mapped)
        order.status = mapped
        db_session.flush()

    report2 = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id=account_snap.external_account_id,
        broker_positions=[],
        broker_orders=[
            BrokerOrderSnapshot(
                broker_order_id=result.broker_order_id,
                symbol="AAPL",
                side="buy",
                order_type="limit",
                quantity=Decimal("1"),
                filled_quantity=Decimal("0"),
                status=mapped.value,
                limit_price=limit_price,
            )
        ],
    )
    assert report2.mutations == 0
    after = [f for f in report2.findings if f.broker_order_id == result.broker_order_id]
    assert any(f.category.value == "MATCH" for f in after)

    # Audit events present (no secrets)
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.entity_id.in_([order.id, result.proposal_id]))
    ).all()
    types = {e.event_type for e in events}
    assert "ALPACA_PAPER_PRE_SUBMIT_CHECK" in types or "ORDER_ROUTED" in types
    assert "ALPACA_PAPER_ORDER_SUBMITTED" in types or "ALPACA_PAPER_ORDER_ACCEPTED" in types
    for ev in events:
        blob = str(ev.details or {})
        assert "APCA-" not in blob
        assert secret not in blob
        assert key not in blob

    os.environ["__TEST_BROKER_ORDER_ID"] = result.broker_order_id
    os.environ["__TEST_CLIENT_ORDER_ID"] = coid
    os.environ["__TEST_PAPER_ORDERS"] = "1"
    os.environ["__TEST_LIVE_ORDERS"] = "0"
