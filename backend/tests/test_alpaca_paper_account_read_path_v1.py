"""Alpaca Paper Account Read-Path V1 — offline unit tests."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from app.broker_state.errors import (
    AUTHENTICATION_FAILED,
    BROKER_UNAVAILABLE,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    MALFORMED_RESPONSE,
    NETWORK_TIMEOUT,
    PAPER_ACCOUNT_NOT_VERIFIED,
    RATE_LIMITED,
    BrokerStateError,
)
from app.broker_state.models import (
    AccountSnapshot,
    BrokerAssetClass,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    ReconciliationCategory,
)
from app.broker_state.reader import BrokerAccountReader
from app.broker_state.readers.alpaca_paper import (
    ALPACA_PAPER_BASE_URL,
    AlpacaPaperAccountReader,
    assert_paper_base_url,
)
from app.broker_state.readers.fake import FakeBrokerAccountReader
from app.broker_state.reconciliation import ReconciliationEngine
from app.broker_state.registration import register_alpaca_paper_account
from app.broker_state.risk_bridge import VerifiedBrokerState
from app.broker_state.service import BrokerStateService
from app.models import (
    AssetClass,
    OrderStatus,
    OrderType,
    PositionStatus,
    ProposalSource,
    TimeInForce,
    TradeProposalStatus,
    TradeSide,
)
from app.models.order import Order
from app.models.position import Position
from app.models.trade_proposal import TradeProposal
from app.trading.risk.engine import RiskEngine
from tests.pipeline_helpers import make_simulation_account, make_strategy


def _account_json(**overrides):
    base = {
        "id": "acct-paper-1",
        "account_number": "PA123",
        "status": "ACTIVE",
        "currency": "USD",
        "cash": "100000.25",
        "equity": "100500.50",
        "buying_power": "200000.00",
        "portfolio_value": "100500.50",
        "trading_blocked": False,
        "account_blocked": False,
    }
    base.update(overrides)
    return base


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_assert_paper_base_url_accepts_paper_only() -> None:
    assert assert_paper_base_url(ALPACA_PAPER_BASE_URL) == ALPACA_PAPER_BASE_URL
    with pytest.raises(BrokerStateError) as exc:
        assert_paper_base_url("https://api.alpaca.markets")
    assert exc.value.code == LIVE_BROKER_ACCESS_FORBIDDEN
    with pytest.raises(BrokerStateError) as exc2:
        assert_paper_base_url("https://live.example.com")
    assert exc2.value.code == LIVE_BROKER_ACCESS_FORBIDDEN


def test_alpaca_reader_rejects_live_endpoint_at_construction() -> None:
    with pytest.raises(BrokerStateError) as exc:
        AlpacaPaperAccountReader(
            api_key="k",
            api_secret="s",
            base_url="https://api.alpaca.markets",
        )
    assert exc.value.code == LIVE_BROKER_ACCESS_FORBIDDEN


def test_alpaca_reader_has_no_execution_methods() -> None:
    reader = AlpacaPaperAccountReader(api_key="k", api_secret="s")
    banned = [
        "place_order",
        "submit_order",
        "cancel_order",
        "cancel_all_orders",
        "replace_order",
        "modify_order",
        "close_position",
        "close_all_positions",
        "liquidate",
    ]
    for name in banned:
        assert not hasattr(reader, name)
    assert not hasattr(reader, "client")
    assert isinstance(reader, BrokerAccountReader)
    # Source audit: no mutating HTTP verbs as callable API surface
    src = Path("app/broker_state/readers/alpaca_paper.py").read_text(encoding="utf-8")
    assert "client.post" not in src.lower()
    assert "client.delete" not in src.lower()
    assert "client.patch" not in src.lower()
    assert "client.put" not in src.lower()
    assert re.search(r"(?m)^\s*from\s+alpaca(\.|\s)", src) is None
    assert re.search(r"(?m)^\s*import\s+alpaca(\.|\s|$)", src) is None
    assert re.search(r"(?m)^\s*from\s+alpaca\.trading", src) is None
    assert "TradingClient(" not in src
    assert "import TradingClient" not in src


@pytest.mark.asyncio
async def test_account_normalization_decimal_and_paper_verified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "paper-api.alpaca.markets" in str(request.url)
        assert request.url.path == "/v2/account"
        return httpx.Response(200, json=_account_json())

    reader = AlpacaPaperAccountReader(
        api_key="k",
        api_secret="s",
        transport=_mock_transport(handler),
    )
    snap = await reader.get_account()
    assert snap.paper_verified is True
    assert snap.external_account_id == "acct-paper-1"
    assert isinstance(snap.cash, Decimal)
    assert snap.cash == Decimal("100000.25")
    assert isinstance(snap.buying_power, Decimal)
    assert snap.equity == Decimal("100500.50")


@pytest.mark.asyncio
async def test_positions_and_orders_normalization_empty_and_multiple() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        calls.append(request.url.path)
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=_account_json())
        if request.url.path == "/v2/positions":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "AAPL",
                        "qty": "10",
                        "side": "long",
                        "avg_entry_price": "150.1",
                        "current_price": "155",
                        "market_value": "1550",
                        "unrealized_pl": "49",
                        "unrealized_plpc": "0.03",
                        "asset_class": "us_equity",
                    },
                    {
                        "symbol": "MSFT",
                        "qty": "2",
                        "side": "short",
                        "avg_entry_price": "300",
                        "current_price": "290",
                        "market_value": "-580",
                        "unrealized_pl": "20",
                        "unrealized_plpc": "0.03",
                        "asset_class": "us_equity",
                    },
                ],
            )
        if request.url.path == "/v2/orders":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "ord-1",
                        "symbol": "AAPL",
                        "side": "buy",
                        "type": "limit",
                        "qty": "5",
                        "filled_qty": "0",
                        "limit_price": "140",
                        "status": "new",
                        "time_in_force": "day",
                        "submitted_at": "2026-10-06T12:00:00Z",
                    },
                    {
                        "id": "ord-2",
                        "symbol": "MSFT",
                        "side": "sell",
                        "type": "market",
                        "qty": "1",
                        "filled_qty": "1",
                        "status": "filled",
                        "filled_at": "2026-10-06T12:01:00Z",
                    },
                ],
            )
        if request.url.path == "/v2/account/activities":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "fill-1",
                        "activity_type": "FILL",
                        "symbol": "MSFT",
                        "side": "sell",
                        "qty": "1",
                        "price": "300",
                        "order_id": "ord-2",
                        "transaction_time": "2026-10-06T12:01:00Z",
                    }
                ],
            )
        return httpx.Response(404, json={"message": "nope"})

    reader = AlpacaPaperAccountReader(
        api_key="k",
        api_secret="s",
        transport=_mock_transport(handler),
    )
    positions = await reader.get_positions()
    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert isinstance(positions[0].quantity, Decimal)
    assert positions[0].average_entry_price == Decimal("150.1")
    assert positions[1].side == "short"

    orders = await reader.get_orders()
    assert len(orders) == 2
    assert orders[0].broker_order_id == "ord-1"
    assert isinstance(orders[0].quantity, Decimal)

    # Empty positions
    def empty_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=_account_json())
        if request.url.path == "/v2/positions":
            return httpx.Response(200, json=[])
        if request.url.path == "/v2/orders":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    empty_reader = AlpacaPaperAccountReader(
        api_key="k",
        api_secret="s",
        transport=_mock_transport(empty_handler),
    )
    assert await empty_reader.get_positions() == []
    assert await empty_reader.get_orders() == []

    fills = await reader.get_trade_activity()
    assert len(fills) == 1
    assert fills[0].price == Decimal("300")
    assert all(p.startswith("/v2/") for p in calls)
    assert not any("POST" in c for c in calls)


@pytest.mark.asyncio
async def test_http_error_modes() -> None:
    async def expect(code: str, status: int | None = None, exc_cls=None):
        def handler(request: httpx.Request) -> httpx.Response:
            if exc_cls is httpx.TimeoutException:
                raise httpx.TimeoutException("timeout")
            if exc_cls is httpx.ConnectError:
                raise httpx.ConnectError("down")
            return httpx.Response(status or 500, json={"message": "x"})

        reader = AlpacaPaperAccountReader(
            api_key="k",
            api_secret="s",
            transport=_mock_transport(handler),
        )
        with pytest.raises(BrokerStateError) as err:
            await reader.get_account()
        assert err.value.code == code

    await expect(AUTHENTICATION_FAILED, status=401)
    await expect(RATE_LIMITED, status=429)
    await expect(BROKER_UNAVAILABLE, status=503)
    await expect(NETWORK_TIMEOUT, exc_cls=httpx.TimeoutException)
    await expect(BROKER_UNAVAILABLE, exc_cls=httpx.ConnectError)


@pytest.mark.asyncio
async def test_malformed_response_and_paper_verification_failure() -> None:
    def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})

    reader = AlpacaPaperAccountReader(
        api_key="k",
        api_secret="s",
        transport=_mock_transport(bad_json),
    )
    with pytest.raises(BrokerStateError) as exc:
        await reader.get_account()
    assert exc.value.code == MALFORMED_RESPONSE

    def missing_id(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cash": "1", "status": "ACTIVE"})

    reader2 = AlpacaPaperAccountReader(
        api_key="k",
        api_secret="s",
        transport=_mock_transport(missing_id),
    )
    with pytest.raises(BrokerStateError) as exc2:
        await reader2.get_account()
    assert exc2.value.code == PAPER_ACCOUNT_NOT_VERIFIED


@pytest.mark.asyncio
async def test_broker_state_service_provider_selection() -> None:
    fake = FakeBrokerAccountReader()
    svc = BrokerStateService(fake)
    assert svc.provider_name == "fake"
    snap = await svc.get_account_snapshot()
    assert snap.cash == Decimal("100000")
    assert await svc.get_positions() == []
    assert await svc.get_open_orders() == []


def test_broker_state_service_has_no_execution_methods() -> None:
    svc = BrokerStateService(FakeBrokerAccountReader())
    for name in ("place_order", "cancel_order", "modify_order", "close_position"):
        assert not hasattr(svc, name)


def test_risk_engine_accepts_verified_broker_state(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Risk-BrokerState")
    snap = AccountSnapshot(
        broker="alpaca",
        external_account_id="x",
        account_status="ACTIVE",
        cash=Decimal("1"),
        timestamp=datetime.now(UTC),
        paper_verified=True,
    )
    state = VerifiedBrokerState(account=snap)
    engine = RiskEngine(db_session, broker_state=state)
    assert engine.broker_state is state
    assert engine.broker_state.paper_verified is True


def test_registration_keeps_disabled(db_session: Session) -> None:
    snap = AccountSnapshot(
        broker="alpaca",
        external_account_id="ext-99",
        account_status="ACTIVE",
        cash=Decimal("50000"),
        timestamp=datetime.now(UTC),
        paper_verified=True,
    )
    row = register_alpaca_paper_account(db_session, snapshot=snap, name="Alpaca-Paper-1")
    assert row.broker == "alpaca"
    assert row.external_account_id == "ext-99"
    assert row.trading_mode.value == "paper"
    assert row.is_enabled is False
    # credentials never on model
    assert not hasattr(row, "api_key")


def test_reconciliation_matrix(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Recon-Acct", broker="alpaca")
    strategy = make_strategy(db_session, name="Recon-Strat")
    now = datetime.now(UTC)

    # Internal AAPL long 10; broker AAPL long 10 → MATCH
    # Internal TSLA 5; broker missing → MISSING_BROKER_POSITION
    # Broker NVDA; internal missing → MISSING_INTERNAL_POSITION
    # Internal MSFT long 3; broker short 3 → SIDE mismatch
    # Internal AMD 2; broker AMD 5 → QTY mismatch
    db_session.add_all(
        [
            Position(
                broker_account_id=account.id,
                strategy_id=strategy.id,
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("10"),
                average_entry_price=Decimal("100"),
                status=PositionStatus.OPEN,
            ),
            Position(
                broker_account_id=account.id,
                strategy_id=strategy.id,
                symbol="TSLA",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("5"),
                average_entry_price=Decimal("200"),
                status=PositionStatus.OPEN,
            ),
            Position(
                broker_account_id=account.id,
                strategy_id=strategy.id,
                symbol="MSFT",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("3"),
                average_entry_price=Decimal("300"),
                status=PositionStatus.OPEN,
            ),
            Position(
                broker_account_id=account.id,
                strategy_id=strategy.id,
                symbol="AMD",
                asset_class=AssetClass.EQUITY,
                quantity=Decimal("2"),
                average_entry_price=Decimal("100"),
                status=PositionStatus.OPEN,
            ),
        ]
    )
    # Orders
    proposal = TradeProposal(
        broker_account_id=account.id,
        strategy_id=strategy.id,
        source=ProposalSource.STRATEGY,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("100"),
        status=TradeProposalStatus.SUBMITTED,
    )
    db_session.add(proposal)
    db_session.flush()
    for oid in ("br-match", "br-missing", "br-status"):
        db_session.add(
            Order(
                trade_proposal_id=proposal.id,
                broker_account_id=account.id,
                broker_order_id=oid,
                symbol="AAPL",
                asset_class=AssetClass.EQUITY,
                side=TradeSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal("1"),
                limit_price=Decimal("100"),
                time_in_force=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED,
            )
        )
    db_session.flush()

    broker_positions = [
        BrokerPositionSnapshot(
            symbol="AAPL",
            quantity=Decimal("10"),
            side="long",
            timestamp=now,
        ),
        BrokerPositionSnapshot(
            symbol="NVDA",
            quantity=Decimal("1"),
            side="long",
            timestamp=now,
        ),
        BrokerPositionSnapshot(
            symbol="MSFT",
            quantity=Decimal("3"),
            side="short",
            timestamp=now,
        ),
        BrokerPositionSnapshot(
            symbol="AMD",
            quantity=Decimal("5"),
            side="long",
            timestamp=now,
        ),
    ]
    broker_orders = [
        BrokerOrderSnapshot(
            broker_order_id="br-match",
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("1"),
            status="submitted",
        ),
        BrokerOrderSnapshot(
            broker_order_id="br-unknown",
            symbol="QQQ",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
            status="new",
        ),
        BrokerOrderSnapshot(
            broker_order_id="br-status",
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("1"),
            status="filled",
        ),
    ]

    report = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id="ext",
        broker_positions=broker_positions,
        broker_orders=broker_orders,
    )
    assert report.mutations == 0
    cats = {f.category for f in report.findings}
    assert ReconciliationCategory.MATCH in cats
    assert ReconciliationCategory.MISSING_INTERNAL_POSITION in cats
    assert ReconciliationCategory.MISSING_BROKER_POSITION in cats
    assert ReconciliationCategory.POSITION_SIDE_MISMATCH in cats
    assert ReconciliationCategory.POSITION_QUANTITY_MISMATCH in cats
    assert ReconciliationCategory.UNKNOWN_BROKER_ORDER in cats
    assert ReconciliationCategory.MISSING_BROKER_ORDER in cats
    assert ReconciliationCategory.ORDER_STATUS_MISMATCH in cats

    # Zero mutations: positions unchanged
    still = db_session.query(Position).filter_by(broker_account_id=account.id).count()
    assert still == 4


def test_reconciliation_exact_match_empty(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Recon-Empty")
    report = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id=None,
        broker_positions=[],
        broker_orders=[],
    )
    assert report.mutations == 0
    assert report.findings == []
    assert report.is_clean
