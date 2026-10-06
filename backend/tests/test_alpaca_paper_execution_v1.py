"""Alpaca Paper Execution Adapter V1 — offline attack matrix + idempotency."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.errors import (
    AMBIGUOUS_IDEMPOTENCY_STATE,
    BROKER_ACCOUNT_DISABLED,
    INSUFFICIENT_BROKER_BUYING_POWER,
    LIVE_BROKER_ACCESS_FORBIDDEN,
    NETWORK_TIMEOUT,
    PAPER_ACCOUNT_NOT_VERIFIED,
    PIPELINE_PRECONDITION_FAILED,
    PRICE_UNAVAILABLE,
    STALE_MARKET_DATA,
    TRADING_BLOCKED,
    UNSUPPORTED_ASSET_CLASS,
    ExecutionAdapterError,
)
from app.brokers.execution.fake import FakeExecutionAdapter
from app.brokers.execution.fill_sync import AlpacaFillSyncService
from app.brokers.execution.types import ExecutionSubmission
from app.models import (
    AssetClass,
    OrderStatus,
    OrderType,
    ProposalSource,
    TradeProposalStatus,
    TradeSide,
)
from app.models.enums import TradingMode
from app.models.execution import Execution
from app.models.order import Order
from app.models.trade_proposal import TradeProposal
from app.trading.proposals.service import TradeProposalService
from app.trading.routing.router import BrokerRouter
from tests.pipeline_helpers import (
    make_assignment,
    make_global_policy,
    make_simulation_account,
    make_strategy,
    valid_limit_proposal,
)


def _submission(**overrides) -> ExecutionSubmission:
    oid = uuid.uuid4()
    base = dict(
        trade_proposal_id=uuid.uuid4(),
        proposal_status="routed",
        risk_approved=True,
        validated=True,
        routed=True,
        broker_account_id=uuid.uuid4(),
        broker="alpaca",
        trading_mode="paper",
        account_enabled=True,
        internal_order_id=oid,
        client_order_id=build_client_order_id(oid),
        symbol="AAPL",
        asset_class="equity",
        side="buy",
        order_type="limit",
        quantity=Decimal("1"),
        limit_price=Decimal("1.00"),
        stop_price=None,
        time_in_force="day",
    )
    base.update(overrides)
    return ExecutionSubmission(**base)


def _account_json(**overrides):
    base = {
        "id": "acct-paper-1",
        "status": "ACTIVE",
        "currency": "USD",
        "cash": "100000",
        "buying_power": "100000",
        "equity": "100000",
        "portfolio_value": "100000",
        "trading_blocked": False,
        "account_blocked": False,
    }
    base.update(overrides)
    return base


def test_adapter_has_no_cancel_replace_close() -> None:
    adapter = AlpacaPaperExecutionAdapter(api_key="k", api_secret="s")
    for name in (
        "cancel_order",
        "cancel_all_orders",
        "replace_order",
        "modify_order",
        "close_position",
        "close_all_positions",
        "liquidate",
    ):
        assert not hasattr(adapter, name)
    assert not hasattr(adapter, "client")
    src = Path("app/brokers/execution/alpaca_paper.py").read_text(encoding="utf-8")
    assert "TradingClient(" not in src
    assert re.search(r"(?m)^\s*from\s+alpaca(\.|\s)", src) is None
    # Single-order DELETE is allowed for controlled cancel; cancel-all must remain forbidden
    assert 'path == "/v2/orders"' in src or "cancel_all_orders is forbidden" in src
    assert "close_all_positions" not in src.lower()
    # Must not expose generic BrokerAdapter-style cancel_order API name as public method
    assert not hasattr(adapter, "cancel_order")
    assert not hasattr(adapter, "cancel_all_orders")


def test_live_endpoint_rejected_at_construction() -> None:
    with pytest.raises(ExecutionAdapterError) as exc:
        AlpacaPaperExecutionAdapter(
            api_key="k",
            api_secret="s",
            base_url="https://api.alpaca.markets",
        )
    assert exc.value.code == LIVE_BROKER_ACCESS_FORBIDDEN


@pytest.mark.asyncio
async def test_pipeline_preconditions_enforced() -> None:
    adapter = AlpacaPaperExecutionAdapter(api_key="k", api_secret="s")
    bad = _submission(risk_approved=False)
    with pytest.raises(ExecutionAdapterError) as exc:
        await adapter.submit_order(bad)
    assert exc.value.code == PIPELINE_PRECONDITION_FAILED

    bad2 = _submission(validated=False)
    with pytest.raises(ExecutionAdapterError) as exc2:
        await adapter.submit_order(bad2)
    assert exc2.value.code == PIPELINE_PRECONDITION_FAILED

    bad3 = _submission(proposal_status="pending")
    with pytest.raises(ExecutionAdapterError) as exc3:
        await adapter.submit_order(bad3)
    assert exc3.value.code == PIPELINE_PRECONDITION_FAILED

    bad4 = _submission(trading_mode="live")
    with pytest.raises(ExecutionAdapterError) as exc4:
        await adapter.submit_order(bad4)
    assert exc4.value.code == LIVE_BROKER_ACCESS_FORBIDDEN

    bad5 = _submission(account_enabled=False)
    with pytest.raises(ExecutionAdapterError) as exc5:
        await adapter.submit_order(bad5)
    assert exc5.value.code == BROKER_ACCOUNT_DISABLED

    bad6 = _submission(asset_class="option")
    with pytest.raises(ExecutionAdapterError) as exc6:
        await adapter.submit_order(bad6)
    assert exc6.value.code == UNSUPPORTED_ASSET_CLASS


@pytest.mark.asyncio
async def test_idempotent_submit_after_timeout_posts_once() -> None:
    """Broker accepts order; response lost; retry recovers — POST count = 1."""
    state = {"posted": False, "order": None}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/account":
            return httpx.Response(200, json=_account_json())
        if path.startswith("/v2/orders:by_client_order_id/"):
            if state["order"] is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json=state["order"])
        if path == "/v2/orders" and request.method == "POST":
            assert state["posted"] is False
            state["posted"] = True
            body = request.read()
            import json

            payload = json.loads(body.decode())
            state["order"] = {
                "id": "brk-1",
                "client_order_id": payload["client_order_id"],
                "status": "accepted",
                "filled_qty": "0",
                "submitted_at": "2026-10-06T12:00:00Z",
                "symbol": payload["symbol"],
            }
            raise httpx.TimeoutException("lost response after accept")
        if path.startswith("/v2/orders/") and request.method == "GET":
            return httpx.Response(200, json=state["order"])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    adapter = AlpacaPaperExecutionAdapter(
        api_key="k",
        api_secret="s",
        transport=transport,
        skip_buying_power_check=True,
    )
    sub = _submission()
    # First call: POST then timeout → recover via client_order_id
    result = await adapter.submit_order(sub)
    assert result.broker_order_id == "brk-1"
    assert result.recovered_existing is True
    assert adapter.submit_post_count == 1

    # Second call: finds existing, no additional POST
    result2 = await adapter.submit_order(sub)
    assert result2.broker_order_id == "brk-1"
    assert result2.recovered_existing is True
    assert adapter.submit_post_count == 1


@pytest.mark.asyncio
async def test_trading_blocked_and_insufficient_bp() -> None:
    def blocked(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=_account_json(trading_blocked=True))
        return httpx.Response(404)

    adapter = AlpacaPaperExecutionAdapter(
        api_key="k",
        api_secret="s",
        transport=httpx.MockTransport(blocked),
    )
    with pytest.raises(ExecutionAdapterError) as exc:
        await adapter.submit_order(_submission())
    assert exc.value.code == TRADING_BLOCKED

    def low_bp(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/account":
            return httpx.Response(200, json=_account_json(buying_power="0.5"))
        if request.url.path.startswith("/v2/orders:by_client_order_id/"):
            return httpx.Response(404, json={})
        return httpx.Response(404)

    adapter2 = AlpacaPaperExecutionAdapter(
        api_key="k",
        api_secret="s",
        transport=httpx.MockTransport(low_bp),
    )
    with pytest.raises(ExecutionAdapterError) as exc2:
        await adapter2.submit_order(_submission(quantity=Decimal("10"), limit_price=Decimal("100")))
    assert exc2.value.code == INSUFFICIENT_BROKER_BUYING_POWER


@pytest.mark.asyncio
async def test_paper_verification_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cash": "1"})  # missing id

    adapter = AlpacaPaperExecutionAdapter(
        api_key="k",
        api_secret="s",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ExecutionAdapterError) as exc:
        await adapter.submit_order(_submission())
    assert exc.value.code == PAPER_ACCOUNT_NOT_VERIFIED


@pytest.mark.asyncio
async def test_router_alpaca_path_with_fake_adapter(db_session: Session) -> None:
    account = make_simulation_account(
        db_session, name="Alpaca-Exec-Acct", broker="alpaca", enabled=True
    )
    strategy = make_strategy(db_session, name="Alpaca-Exec-Strat")
    make_assignment(db_session, strategy=strategy, account=account)
    make_global_policy(db_session, require_stop_loss=False)

    fake = FakeExecutionAdapter()
    router = BrokerRouter(
        db_session,
        execution_adapters={"alpaca": fake},
        adapters={},  # no simulation for this account
    )
    svc = TradeProposalService(db_session, broker_router=router)
    result = await svc.create_and_process(
        valid_limit_proposal(
            account,
            strategy_id=strategy.id,
            quantity=Decimal("1"),
            limit_price=Decimal("10"),
            stop_loss_price=None,
        )
    )
    assert result.submitted is True
    assert result.broker_order_id
    assert fake.post_count == 1
    order = db_session.get(Order, uuid.UUID(result.route.order_id))
    assert order is not None
    assert order.broker_order_id == result.broker_order_id
    assert order.status == OrderStatus.SUBMITTED


@pytest.mark.asyncio
async def test_attack_matrix_zero_alpaca_posts(db_session: Session) -> None:
    """Zero broker POSTs for disabled / live / risk-rejected / not validated / etc."""
    fake = FakeExecutionAdapter()
    router = BrokerRouter(db_session, execution_adapters={"alpaca": fake}, adapters={})
    policy = make_global_policy(db_session, require_stop_loss=False)
    svc = TradeProposalService(db_session, broker_router=router)

    # Disabled account
    disabled = make_simulation_account(
        db_session, name="Dis-Alpaca", broker="alpaca", enabled=False
    )
    r1 = await svc.create_and_process(
        valid_limit_proposal(disabled, stop_loss_price=None)
    )
    assert r1.submitted is False
    assert fake.post_count == 0

    # Live mode account
    live = make_simulation_account(
        db_session,
        name="Live-Alpaca",
        broker="alpaca",
        enabled=True,
        trading_mode=TradingMode.LIVE,
    )
    r2 = await svc.create_and_process(valid_limit_proposal(live, stop_loss_price=None))
    assert r2.submitted is False
    assert fake.post_count == 0

    # Risk rejected (require stop, omit stop)
    policy.require_stop_loss = True
    db_session.flush()
    paper = make_simulation_account(
        db_session, name="Risk-Rej-Alpaca", broker="alpaca", enabled=True
    )
    r3 = await svc.create_and_process(
        valid_limit_proposal(paper, stop_loss_price=None)
    )
    assert r3.submitted is False
    assert fake.post_count == 0

    # Unsupported broker (with stop so risk can pass)
    other = make_simulation_account(
        db_session, name="Other-Broker", broker="tradovate", enabled=True
    )
    r4 = await svc.create_and_process(
        valid_limit_proposal(other, stop_loss_price=Decimal("90"))
    )
    assert r4.submitted is False
    assert fake.post_count == 0

    # Direct adapter misuse without pipeline proof
    with pytest.raises(ExecutionAdapterError) as exc:
        await fake.submit_order(
            _submission(
                risk_approved=False,
                routed=False,
                validated=False,
                proposal_status="pending",
            )
        )
    assert exc.value.code == PIPELINE_PRECONDITION_FAILED
    assert fake.post_count == 0


@pytest.mark.asyncio
async def test_duplicate_submission_idempotent_via_router(db_session: Session) -> None:
    account = make_simulation_account(
        db_session, name="Idem-Alpaca", broker="alpaca", enabled=True
    )
    make_global_policy(db_session, require_stop_loss=False)
    fake = FakeExecutionAdapter()
    router = BrokerRouter(db_session, execution_adapters={"alpaca": fake}, adapters={})
    svc = TradeProposalService(db_session, broker_router=router)
    first = await svc.create_and_process(
        valid_limit_proposal(account, stop_loss_price=None, quantity=Decimal("1"), limit_price=Decimal("5"))
    )
    assert first.submitted is True
    assert fake.post_count == 1

    # Manual second submit with same client_order_id recovers without new POST
    order = db_session.get(Order, uuid.UUID(first.route.order_id))
    assert order is not None
    sub = _submission(
        trade_proposal_id=order.trade_proposal_id,
        broker_account_id=account.id,
        internal_order_id=order.id,
        client_order_id=build_client_order_id(order.id),
        quantity=order.quantity,
        limit_price=order.limit_price,
    )
    recovered = await fake.submit_order(sub)
    assert recovered.recovered_existing is True
    assert fake.post_count == 1


def test_fill_sync_records_execution(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Fill-Sync", broker="alpaca")
    proposal = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("2"),
        limit_price=Decimal("10"),
        status=TradeProposalStatus.SUBMITTED,
    )
    db_session.add(proposal)
    db_session.flush()
    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        broker_order_id="brk-fill-1",
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("2"),
        limit_price=Decimal("10"),
        status=OrderStatus.SUBMITTED,
        submitted_at=datetime.now(UTC),
    )
    db_session.add(order)
    db_session.flush()

    sync = AlpacaFillSyncService(db_session)
    result = sync.apply_broker_order_snapshot(
        order,
        {
            "id": "brk-fill-1",
            "status": "filled",
            "filled_qty": "2",
            "filled_avg_price": "10.5",
            "filled_at": "2026-10-06T15:00:00Z",
        },
    )
    assert result["fills_recorded"] == 1
    assert order.status == OrderStatus.FILLED
    execs = db_session.query(Execution).filter_by(order_id=order.id).all()
    assert len(execs) == 1
    assert execs[0].price == Decimal("10.5")
    assert execs[0].accounting_applied is True

    # Idempotent second sync
    result2 = sync.apply_broker_order_snapshot(
        order,
        {
            "id": "brk-fill-1",
            "status": "filled",
            "filled_qty": "2",
            "filled_avg_price": "10.5",
        },
    )
    assert result2["fills_recorded"] == 0


@pytest.mark.asyncio
async def test_simulation_regression_untouched(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="Sim-Still-Works", enabled=True)
    make_global_policy(db_session, require_stop_loss=False)
    from app.trading.execution.market_data import SimulationMarketData

    md = SimulationMarketData()
    md.set_price("AAPL", Decimal("100"))
    svc = TradeProposalService(db_session, market_data=md)
    result = await svc.create_and_process(
        valid_limit_proposal(account, stop_loss_price=None, limit_price=Decimal("100"))
    )
    assert result.submitted is True
    assert result.broker_order_id and result.broker_order_id.startswith("sim_")
