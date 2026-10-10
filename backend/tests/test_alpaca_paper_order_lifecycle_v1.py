"""Alpaca Paper Order Lifecycle V1 — offline unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.broker_state.models import BrokerOrderSnapshot, ReconciliationCategory
from app.broker_state.reconciliation import ReconciliationEngine
from app.brokers.execution.cancellation import CancellationRequest, ControlledCancellationService
from app.brokers.execution.client_order_id import build_client_order_id
from app.brokers.execution.fake import FakeExecutionAdapter
from app.brokers.execution.fill_sync import AlpacaFillSyncService, internal_filled_quantity
from app.brokers.execution.order_status_sync import OrderStatusSyncService
from app.brokers.execution.status_map import (
    is_cancellable_status,
    is_terminal_status,
    map_alpaca_order_status,
)
from app.models import (
    AssetClass,
    OrderStatus,
    OrderType,
    ProposalSource,
    TimeInForce,
    TradeProposalStatus,
    TradeSide,
)
from app.models.enums import TradingMode
from app.models.execution import Execution
from app.models.order import Order
from app.models.position import Position
from app.models.trade_proposal import TradeProposal
from tests.pipeline_helpers import make_simulation_account, make_strategy


def _make_order(
    session: Session,
    account,
    *,
    qty: Decimal = Decimal("10"),
    broker_order_id: str = "brk-1",
    status: OrderStatus = OrderStatus.SUBMITTED,
) -> Order:
    proposal = TradeProposal(
        broker_account_id=account.id,
        source=ProposalSource.MANUAL,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=qty,
        limit_price=Decimal("100"),
        status=TradeProposalStatus.SUBMITTED,
    )
    session.add(proposal)
    session.flush()
    order = Order(
        trade_proposal_id=proposal.id,
        broker_account_id=account.id,
        broker_order_id=broker_order_id,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=TradeSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=qty,
        limit_price=Decimal("100"),
        time_in_force=TimeInForce.DAY,
        status=status,
        submitted_at=datetime.now(UTC),
    )
    session.add(order)
    session.flush()
    return order


def test_status_mapping_and_terminal() -> None:
    assert map_alpaca_order_status("accepted").value == "submitted"
    assert map_alpaca_order_status("pending_cancel").value == "submitted"
    assert map_alpaca_order_status("partially_filled").value == "partially_filled"
    assert map_alpaca_order_status("filled").value == "filled"
    assert map_alpaca_order_status("canceled").value == "cancelled"
    assert map_alpaca_order_status("rejected").value == "rejected"
    assert map_alpaca_order_status("expired").value == "expired"
    assert is_terminal_status(OrderStatus.FILLED)
    assert is_terminal_status(OrderStatus.CANCELLED)
    assert is_cancellable_status(OrderStatus.SUBMITTED)
    assert not is_cancellable_status(OrderStatus.FILLED)


def test_adapter_has_no_cancel_all_or_liquidate() -> None:
    from app.brokers.execution.alpaca_paper import AlpacaPaperExecutionAdapter

    adapter = AlpacaPaperExecutionAdapter(api_key="k", api_secret="s")
    for name in (
        "cancel_order",
        "cancel_all_orders",
        "close_position",
        "close_all_positions",
        "liquidate",
    ):
        assert not hasattr(adapter, name)
    assert hasattr(adapter, "request_paper_cancel")  # lifecycle-scoped
    assert not hasattr(adapter, "client")
    src = Path("app/brokers/execution/alpaca_paper.py").read_text(encoding="utf-8")
    assert "cancel_all" not in src.lower() or "forbidden" in src.lower()


@pytest.mark.asyncio
async def test_status_transitions_via_sync(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Status", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="s1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["s1"] = {
        "id": "s1",
        "status": "accepted",
        "qty": "10",
        "filled_qty": "0",
        "symbol": "AAPL",
    }
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)

    r = await sync.sync_order(order)
    assert r.ok
    assert order.status == OrderStatus.SUBMITTED

    fake.set_broker_status("s1", "partially_filled", filled_qty="4", filled_avg_price="100")
    fake.add_fill("s1", fill_id="f1", qty=Decimal("4"), price=Decimal("100"))
    # add_fill already set status; re-assert
    r2 = await sync.sync_order(order)
    assert r2.fills_recorded == 1
    assert order.status == OrderStatus.PARTIALLY_FILLED

    fake.add_fill("s1", fill_id="f2", qty=Decimal("6"), price=Decimal("101"))
    r3 = await sync.sync_order(order)
    assert r3.fills_recorded == 1
    assert order.status == OrderStatus.FILLED
    assert internal_filled_quantity(db_session, order.id) == Decimal("10")


@pytest.mark.asyncio
async def test_partial_fills_idempotent_and_accounting(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Fills", broker="alpaca")
    make_strategy(db_session, name="LC-Fills-Strat")
    order = _make_order(db_session, account, qty=Decimal("10"), broker_order_id="pf1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["pf1"] = {"id": "pf1", "status": "accepted", "qty": "10", "filled_qty": "0"}
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)

    fake.add_fill("pf1", fill_id="fill-a", qty=Decimal("4"), price=Decimal("50"))
    await sync.sync_order(order)
    assert db_session.query(Execution).filter_by(order_id=order.id).count() == 1
    pos = db_session.query(Position).filter_by(broker_account_id=account.id, symbol="AAPL").one()
    assert pos.quantity == Decimal("4")

    # Same fill again — no duplicate
    await sync.sync_order(order)
    assert db_session.query(Execution).filter_by(order_id=order.id).count() == 1
    assert pos.quantity == Decimal("4")

    fake.add_fill("pf1", fill_id="fill-b", qty=Decimal("6"), price=Decimal("55"))
    await sync.sync_order(order)
    assert db_session.query(Execution).filter_by(order_id=order.id).count() == 2
    db_session.refresh(pos)
    assert pos.quantity == Decimal("10")
    assert order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_aggregate_delta_fill_avoids_double_count(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Agg", broker="alpaca")
    order = _make_order(db_session, account, qty=Decimal("10"), broker_order_id="agg1")
    fill_sync = AlpacaFillSyncService(db_session)
    # First aggregate at 4
    fill_sync.apply_broker_order_snapshot(
        order,
        {"id": "agg1", "status": "partially_filled", "filled_qty": "4", "filled_avg_price": "10"},
        fills=None,
    )
    assert internal_filled_quantity(db_session, order.id) == Decimal("4")
    # Later aggregate at 10 → delta 6 only
    fill_sync.apply_broker_order_snapshot(
        order,
        {"id": "agg1", "status": "filled", "filled_qty": "10", "filled_avg_price": "10"},
        fills=None,
    )
    assert internal_filled_quantity(db_session, order.id) == Decimal("10")
    assert db_session.query(Execution).filter_by(order_id=order.id).count() == 2


@pytest.mark.asyncio
async def test_rejected_and_expired(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Rej", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="rej1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["rej1"] = {
        "id": "rej1",
        "status": "rejected",
        "qty": "1",
        "filled_qty": "0",
        "reject_reason": "insufficient qty",
    }
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)
    r = await sync.sync_order(order)
    assert r.ok
    assert order.status == OrderStatus.REJECTED

    order2 = _make_order(db_session, account, broker_order_id="exp1")
    fake.broker_orders["exp1"] = {"id": "exp1", "status": "expired", "qty": "1", "filled_qty": "0"}
    r2 = await sync.sync_order(order2)
    assert order2.status == OrderStatus.EXPIRED


@pytest.mark.asyncio
async def test_illegal_backward_transition(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Back", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="b1", status=OrderStatus.FILLED)
    fake = FakeExecutionAdapter()
    fake.broker_orders["b1"] = {"id": "b1", "status": "new", "qty": "1", "filled_qty": "1", "filled_avg_price": "1"}
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)
    r = await sync.sync_order(order)
    assert order.status == OrderStatus.FILLED  # unchanged
    assert r.illegal_transition is True


@pytest.mark.asyncio
async def test_malformed_and_unavailable_leave_state(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Fail", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="m1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["m1"] = {"id": "m1", "status": "accepted", "qty": "1", "filled_qty": "0"}
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)

    fake.get_order_should_fail = True
    r = await sync.sync_order(order)
    assert r.ok is False
    assert order.status == OrderStatus.SUBMITTED

    fake.get_order_should_fail = False
    fake.malformed_get = True
    r2 = await sync.sync_order(order)
    assert r2.ok is False
    assert order.status == OrderStatus.SUBMITTED


@pytest.mark.asyncio
async def test_repeated_identical_sync_idempotent(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Idem", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="i1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["i1"] = {"id": "i1", "status": "accepted", "qty": "10", "filled_qty": "0"}
    fake.add_fill("i1", fill_id="only", qty=Decimal("10"), price=Decimal("5"))
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)
    await sync.sync_order(order)
    exec_count = db_session.query(Execution).filter_by(order_id=order.id).count()
    await sync.sync_order(order)
    await sync.sync_order(order)
    assert db_session.query(Execution).filter_by(order_id=order.id).count() == exec_count
    assert order.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_controlled_cancel_success(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Cancel", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="c1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["c1"] = {"id": "c1", "status": "accepted", "qty": "1", "filled_qty": "0"}
    svc = ControlledCancellationService(db_session, broker=fake)
    result = await svc.cancel(
        CancellationRequest(
            internal_order_id=order.id,
            broker_order_id="c1",
            broker_account_id=account.id,
        )
    )
    assert result.ok and result.cancelled
    assert order.status == OrderStatus.CANCELLED
    assert fake.cancel_count == 1


@pytest.mark.asyncio
async def test_cannot_cancel_filled_or_rejected_or_other_account(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-NoCancel", broker="alpaca")
    other = make_simulation_account(db_session, name="LC-Other", broker="alpaca")
    fake = FakeExecutionAdapter()
    svc = ControlledCancellationService(db_session, broker=fake)

    filled = _make_order(db_session, account, broker_order_id="cf", status=OrderStatus.FILLED)
    fake.broker_orders["cf"] = {"id": "cf", "status": "filled", "qty": "1", "filled_qty": "1"}
    r1 = await svc.cancel(
        CancellationRequest(internal_order_id=filled.id, broker_order_id="cf", broker_account_id=account.id)
    )
    assert r1.ok is False or r1.cancelled is False
    assert r1.reason_code in {"ORDER_NOT_CANCELLABLE", None} or r1.filled_instead

    rejected = _make_order(db_session, account, broker_order_id="cr", status=OrderStatus.REJECTED)
    fake.broker_orders["cr"] = {"id": "cr", "status": "rejected", "qty": "1", "filled_qty": "0"}
    r2 = await svc.cancel(
        CancellationRequest(internal_order_id=rejected.id, broker_order_id="cr", broker_account_id=account.id)
    )
    assert r2.cancelled is False

    open_o = _make_order(db_session, account, broker_order_id="co")
    fake.broker_orders["co"] = {"id": "co", "status": "accepted", "qty": "1", "filled_qty": "0"}
    r3 = await svc.cancel(
        CancellationRequest(internal_order_id=open_o.id, broker_order_id="co", broker_account_id=other.id)
    )
    assert r3.ok is False
    assert r3.reason_code == "ORDER_ACCOUNT_MISMATCH"
    assert fake.cancel_count == 0


@pytest.mark.asyncio
async def test_cancel_fill_race(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Race", broker="alpaca")
    order = _make_order(db_session, account, qty=Decimal("2"), broker_order_id="race1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["race1"] = {
        "id": "race1",
        "status": "accepted",
        "qty": "2",
        "filled_qty": "0",
        "limit_price": "40",
    }
    fake.cancel_race_fill = True
    svc = ControlledCancellationService(db_session, broker=fake)
    result = await svc.cancel(
        CancellationRequest(
            internal_order_id=order.id,
            broker_order_id="race1",
            broker_account_id=account.id,
        )
    )
    assert result.ok
    assert result.filled_instead is True
    assert result.cancelled is False
    assert order.status == OrderStatus.FILLED
    assert internal_filled_quantity(db_session, order.id) == Decimal("2")


@pytest.mark.asyncio
async def test_live_mode_cancel_forbidden(db_session: Session) -> None:
    account = make_simulation_account(
        db_session, name="LC-Live", broker="alpaca", trading_mode=TradingMode.LIVE
    )
    order = _make_order(db_session, account, broker_order_id="lv1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["lv1"] = {"id": "lv1", "status": "accepted", "qty": "1", "filled_qty": "0"}
    svc = ControlledCancellationService(db_session, broker=fake)
    result = await svc.cancel(
        CancellationRequest(internal_order_id=order.id, broker_order_id="lv1", broker_account_id=account.id)
    )
    assert result.ok is False
    assert result.reason_code == "LIVE_BROKER_ACCESS_FORBIDDEN"
    assert fake.cancel_count == 0


@pytest.mark.asyncio
async def test_poll_until_terminal_bounded(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Poll", broker="alpaca")
    order = _make_order(db_session, account, broker_order_id="p1")
    fake = FakeExecutionAdapter()
    fake.broker_orders["p1"] = {"id": "p1", "status": "accepted", "qty": "1", "filled_qty": "0"}
    sync = OrderStatusSyncService(db_session, broker=fake, reconcile=False)

    async def _flip():
        # After first sync, mark cancelled for subsequent polls
        fake.set_broker_status("p1", "canceled")

    # First call accepted; then cancel
    r1 = await sync.sync_order(order)
    assert not r1.terminal
    await _flip()
    r2 = await sync.poll_until_terminal(
        order, interval_seconds=0.01, timeout_seconds=1.0, max_iterations=5
    )
    assert r2.terminal
    assert order.status == OrderStatus.CANCELLED


def test_reconciliation_fill_and_position_mismatch(db_session: Session) -> None:
    account = make_simulation_account(db_session, name="LC-Recon", broker="alpaca")
    order = _make_order(db_session, account, qty=Decimal("5"), broker_order_id="rq1")
    # No executions but broker says filled 5
    report = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id=None,
        broker_positions=[],
        broker_orders=[
            BrokerOrderSnapshot(
                broker_order_id="rq1",
                symbol="AAPL",
                side="buy",
                order_type="limit",
                quantity=Decimal("5"),
                filled_quantity=Decimal("5"),
                status="filled",
            )
        ],
    )
    cats = {f.category for f in report.findings}
    assert ReconciliationCategory.MISSING_EXECUTION in cats or ReconciliationCategory.FILL_QUANTITY_MISMATCH in cats
    assert report.mutations == 0

    # Position mismatch
    strategy = make_strategy(db_session, name="LC-Recon-S")
    from app.models.enums import PositionStatus

    db_session.add(
        Position(
            broker_account_id=account.id,
            strategy_id=strategy.id,
            symbol="MSFT",
            asset_class=AssetClass.EQUITY,
            quantity=Decimal("3"),
            average_entry_price=Decimal("1"),
            status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    from app.broker_state.models import BrokerPositionSnapshot

    report2 = ReconciliationEngine(db_session).reconcile(
        broker_account_id=account.id,
        broker="alpaca",
        external_account_id=None,
        broker_positions=[
            BrokerPositionSnapshot(
                symbol="MSFT",
                quantity=Decimal("9"),
                side="long",
                timestamp=datetime.now(UTC),
            )
        ],
        broker_orders=[],
    )
    assert any(f.category == ReconciliationCategory.POSITION_QUANTITY_MISMATCH for f in report2.findings)


@pytest.mark.asyncio
async def test_no_public_execution_or_cancel_routes() -> None:
    from app.api.router import api_router

    paths = []
    for route in api_router.routes:
        paths.append(getattr(route, "path", ""))
    joined = " ".join(paths).lower()
    assert "execute" not in joined
    assert "cancel" not in joined
    assert "/orders" not in joined
