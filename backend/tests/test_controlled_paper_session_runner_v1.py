"""Controlled Paper Session Runner V1 — test matrix."""

from __future__ import annotations

import ast
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backtesting import make_bar
from app.core.config import Settings
from app.evaluation.hashing import configuration_hash
from app.market_data.models import Bar, MarketDataAssetClass
from app.models import (
    AccountType,
    BrokerAccount,
    PaperSessionExecutionMode,
    PaperSessionState,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    TradingMode,
)
from app.models.enums import StrategyStatus
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.paper_sessions import (
    ActivationRejectedError,
    InMemorySessionBarSource,
    PaperExecuteDisabledError,
    PaperSessionRunner,
    PaperSessionService,
    SessionRiskLimits,
)
from app.paper_sessions.reconciliation import StaticBrokerSnapshotSource
from app.paper_sessions.states import assert_transition
from app.qualification import (
    QualificationState,
    resolve_authenticated_owner,
)
from app.qualification.states import ApprovalScope
from app.strategies import DecisionAction, StrategyDecision, no_action
from app.strategies.protocol import Strategy as StrategyBase
from app.models.enums import AssetClass, OrderType


def _owner():
    return resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=Settings(paper_qualification_owner_subjects="owner@example.com"),
    )


def _table_ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1 FROM paper_trading_sessions LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False


def _ts(day: int) -> datetime:
    return datetime(2024, 6, 1, 16, 0, tzinfo=UTC) + timedelta(days=day - 1)


def _bars(n: int = 40, *, now: datetime | None = None) -> list[Bar]:
    """Bars ending near ``now`` so freshness checks pass."""
    end = now or datetime.now(UTC)
    out: list[Bar] = []
    for i in range(n):
        c = Decimal(str(100 + i))
        ts = end - timedelta(days=n - i)
        out.append(
            make_bar(
                "AAPL",
                ts,
                open=c,
                high=c + Decimal("1"),
                low=c - Decimal("1"),
                close=c,
            )
        )
    return out


def _limits() -> SessionRiskLimits:
    return SessionRiskLimits(
        max_position_size=Decimal("10"),
        max_notional_exposure=Decimal("100000"),
        max_daily_loss=Decimal("5000"),
        max_orders_per_session=20,
        max_concurrent_positions=2,
        allowed_instrument="AAPL",
        require_stop_loss=False,
        market_data_max_age_seconds=86400 * 40,
        max_session_duration_seconds=86400,
    )


def _broker_source(account: BrokerAccount, *, paper_verified: bool = True) -> StaticBrokerSnapshotSource:
    """Match seeded account identity so pre-activation reconciliation can pass."""
    return StaticBrokerSnapshotSource(
        external_account_id=account.external_account_id or "paper-test",
        paper_verified=paper_verified,
    )


def _seed_account_and_approval(
    db: Session,
    *,
    enabled: bool = True,
    mode: TradingMode = TradingMode.PAPER,
    expired: bool = False,
    param_hash: str = "a" * 64,
    evidence: str = "b" * 64,
    version: str = "1.0.0",
) -> tuple[BrokerAccount, StrategyPaperQualification, Strategy]:
    account = BrokerAccount(
        name=f"PS-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        external_account_id=f"paper-{uuid.uuid4().hex[:10]}",
        account_type=AccountType.CASH,
        trading_mode=mode,
        is_enabled=enabled,
    )
    strat = Strategy(
        name=f"S-{uuid.uuid4().hex[:8]}",
        strategy_type="ref",
        version=version,
        status=StrategyStatus.DEVELOPMENT,
    )
    db.add_all([account, strat])
    db.flush()
    db.add(
        RiskPolicy(
            scope_type=RiskScopeType.BROKER_ACCOUNT,
            scope_id=account.id,
            max_daily_loss=Decimal("5000"),
            max_position_value=Decimal("100000"),
            max_total_exposure=Decimal("100000"),
            max_open_positions=5,
            require_stop_loss=False,
            is_enabled=True,
        )
    )
    expires = datetime.now(UTC) - timedelta(days=1) if expired else datetime.now(UTC) + timedelta(days=30)
    qual = StrategyPaperQualification(
        strategy_id=strat.id,
        engine_strategy_id="fixed_session",
        strategy_version=version,
        parameter_hash=param_hash,
        evidence_fingerprint=evidence,
        evaluation_id="e" * 64,
        dataset_fingerprint="d" * 64,
        policy_version="paper_qualification_policy_v1",
        qualification_state=QualificationState.APPROVED_FOR_PAPER,
        approval_scope=ApprovalScope.PAPER_ONLY,
        recommendation="eligible_for_review",
        report={},
        hard_blockers=[],
        warnings=[],
        approved_by_actor_type="owner",
        approved_by_actor_reference="owner@example.com",
        approved_at=datetime.now(UTC) - timedelta(hours=1),
        expires_at=expires,
        state_version=1,
    )
    db.add(qual)
    db.flush()
    return account, qual, strat


class FixedSessionStrategy(StrategyBase):
    def __init__(self, decisions: list[StrategyDecision]) -> None:
        self._decisions = list(decisions)
        self._i = 0

    @property
    def strategy_id(self) -> str:
        return "fixed_session"

    @property
    def name(self) -> str:
        return "Fixed Session"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_asset_classes(self):
        return frozenset({AssetClass.EQUITY})

    @property
    def required_timeframes(self):
        return frozenset({"1Day"})

    def evaluate(self, context) -> StrategyDecision:
        _ = context
        if self._i >= len(self._decisions):
            return no_action()
        d = self._decisions[self._i]
        self._i += 1
        return d


def _enter_decision() -> StrategyDecision:
    return StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        stop_loss_price=Decimal("90"),
    )


# ---------------------------------------------------------------------------
# State machine / defaults
# ---------------------------------------------------------------------------


def test_inactive_default_and_transitions() -> None:
    assert PaperSessionState.CREATED.value == "created"
    assert_transition(PaperSessionState.CREATED, PaperSessionState.READY)
    assert_transition(PaperSessionState.RUNNING, PaperSessionState.PAUSING)
    with pytest.raises(Exception):
        assert_transition(PaperSessionState.STOPPED, PaperSessionState.RUNNING)


# ---------------------------------------------------------------------------
# Activation gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_and_missing_approval(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    with pytest.raises(Exception):
        resolve_authenticated_owner(
            subject="x",
            credential_verified=False,
            settings=Settings(paper_qualification_owner_subjects="owner@example.com"),
        )
    account, qual, strat = _seed_account_and_approval(db_session)
    # Wipe approval state
    qual.qualification_state = QualificationState.DRAFT
    db_session.flush()
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    owner = _owner()
    params = {"quantity": "1"}
    ph = configuration_hash(params)
    # evidence fingerprint on qual won't match if we change hashes — use qual fields
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters=params,
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    assert session.session_state == PaperSessionState.CREATED
    with pytest.raises(ActivationRejectedError):
        await svc.activate(session.id, owner=owner)


@pytest.mark.asyncio
async def test_expired_approval_and_live_account(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session, expired=True)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    with pytest.raises(ActivationRejectedError):
        await svc.activate(session.id, owner=owner)

    live_account, qual2, strat2 = _seed_account_and_approval(
        db_session, mode=TradingMode.LIVE, evidence="c" * 64, param_hash="d" * 64
    )
    with pytest.raises(ActivationRejectedError):
        svc.create_session(
            owner=owner,
            engine_strategy_id=qual2.engine_strategy_id,
            strategy_version=qual2.strategy_version,
            parameter_hash=qual2.parameter_hash,
            parameters={},
            qualification_approval_id=qual2.id,
            evidence_fingerprint=qual2.evidence_fingerprint,
            broker_account_id=live_account.id,
            instrument="AAPL",
            timeframe="1Day",
            risk_limits=_limits(),
            strategy_db_id=strat2.id,
        )


@pytest.mark.asyncio
async def test_changed_parameters_rejection(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash="f" * 64,  # mismatch vs approval
        parameters={"x": 1},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    with pytest.raises(ActivationRejectedError):
        await svc.activate(session.id, owner=owner)


@pytest.mark.asyncio
async def test_missing_risk_limits_and_paper_execute_disabled(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    with pytest.raises(PaperExecuteDisabledError):
        svc.create_session(
            owner=owner,
            engine_strategy_id=qual.engine_strategy_id,
            strategy_version=qual.strategy_version,
            parameter_hash=qual.parameter_hash,
            parameters={},
            qualification_approval_id=qual.id,
            evidence_fingerprint=qual.evidence_fingerprint,
            broker_account_id=account.id,
            instrument="AAPL",
            timeframe="1Day",
            risk_limits=_limits(),
            strategy_db_id=strat.id,
            execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
        )


# ---------------------------------------------------------------------------
# Happy path DRY_RUN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_zero_orders_and_no_action(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    assert session.session_state == PaperSessionState.RUNNING
    assert session.execution_mode == PaperSessionExecutionMode.DRY_RUN

    now = datetime.now(UTC)
    bars = _bars(30, now=now)
    source = InMemorySessionBarSource(bars)
    strategy = FixedSessionStrategy([no_action()] * 5)
    runner = PaperSessionRunner(
        db_session, bar_source=source, strategy=strategy, worker_id="w1"
    )
    result = await runner.run_once(session.id, now=now)
    assert result.processed is True
    assert result.decision_action == DecisionAction.NO_ACTION.value
    assert result.submitted is False
    assert result.broker_orders_created == 0
    assert runner.broker_orders_created == 0
    assert svc.broker_orders_created == 0


@pytest.mark.asyncio
async def test_proposal_risk_validator_dry_run(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    now = datetime.now(UTC)
    source = InMemorySessionBarSource(_bars(30, now=now))
    strategy = FixedSessionStrategy([_enter_decision()])
    runner = PaperSessionRunner(
        db_session, bar_source=source, strategy=strategy, worker_id="w2"
    )
    result = await runner.run_once(session.id, now=now)
    assert result.processed is True
    assert result.proposal_id is not None
    assert result.submitted is False
    assert result.dry_run is True
    assert result.broker_orders_created == 0


@pytest.mark.asyncio
async def test_duplicate_bar_protection(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    now = datetime.now(UTC)
    source = InMemorySessionBarSource(_bars(20, now=now))
    # Always NO_ACTION so decision identity stable for same bar
    strategy = FixedSessionStrategy([])  # always no_action via empty
    runner = PaperSessionRunner(
        db_session, bar_source=source, strategy=strategy, worker_id="w3"
    )
    r1 = await runner.run_once(session.id, now=now)
    assert r1.processed is True
    # Rewind cursor to re-process the same bar → duplicate protection
    from app.paper_sessions.repository import PaperSessionRepository

    row = PaperSessionRepository(db_session).get(session.id)
    assert row is not None
    PaperSessionRepository(db_session).update_atomic(
        row,
        expected_version=row.state_version,
        last_processed_bar_at=None,
    )
    strategy2 = FixedSessionStrategy([])
    runner2 = PaperSessionRunner(
        db_session, bar_source=source, strategy=strategy2, worker_id="w3"
    )
    r2 = await runner2.run_once(session.id, now=now)
    assert r2.skipped_duplicate is True


@pytest.mark.asyncio
async def test_stale_market_data(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    limits = _limits()
    limits = limits.model_copy(update={"market_data_max_age_seconds": 60})
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=limits,
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    old = datetime(2020, 1, 1, tzinfo=UTC)
    source = InMemorySessionBarSource(_bars(10, now=old))
    runner = PaperSessionRunner(
        db_session,
        bar_source=source,
        strategy=FixedSessionStrategy([]),
        worker_id="w4",
    )
    with pytest.raises(Exception):
        await runner.run_once(session.id, now=datetime.now(UTC))


@pytest.mark.asyncio
async def test_incomplete_bars(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    now = datetime.now(UTC)
    bad = Bar(
        symbol="AAPL",
        open=Decimal("10"),
        high=Decimal("9"),  # invalid
        low=Decimal("8"),
        close=Decimal("9"),
        volume=Decimal("1"),
        timestamp=now - timedelta(minutes=1),
        timeframe="1Day",
        provider="test",
        asset_class=MarketDataAssetClass.EQUITY,
    )
    source = InMemorySessionBarSource([bad])
    runner = PaperSessionRunner(
        db_session,
        bar_source=source,
        strategy=FixedSessionStrategy([]),
        worker_id="w5",
    )
    with pytest.raises(Exception):
        await runner.run_once(session.id, now=now)


# ---------------------------------------------------------------------------
# Pause / stop / kill / concurrency / recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_resume_stop_kill(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    session = svc.pause(session.id, owner=owner)
    assert session.session_state == PaperSessionState.PAUSED
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(10, now=now)),
        strategy=FixedSessionStrategy([_enter_decision()]),
        worker_id="w6",
    )
    paused_result = await runner.run_once(session.id, now=now)
    assert paused_result.processed is False
    assert "session_paused" in paused_result.warnings

    session = svc.resume(session.id, owner=owner)
    assert session.session_state == PaperSessionState.RUNNING
    kill = svc.emergency_kill(session.id, owner=owner)
    assert kill["further_submissions_disabled"] is True
    assert kill["orders_cancelled"] is False
    assert kill["positions_liquidated"] is False
    db_session.refresh(session)
    assert session.session_state == PaperSessionState.STOPPED


@pytest.mark.asyncio
async def test_concurrent_worker_and_crash_recovery(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    await svc.activate(session.id, owner=owner)
    now = datetime.now(UTC)
    from app.paper_sessions.repository import PaperSessionRepository

    repo = PaperSessionRepository(db_session)
    row = repo.get(session.id)
    assert row is not None
    repo.acquire_lease(
        row,
        owner="worker-a",
        expires_at=now + timedelta(minutes=5),
        now=now,
    )
    with pytest.raises(Exception):
        repo.acquire_lease(
            repo.get(session.id),  # type: ignore[arg-type]
            owner="worker-b",
            expires_at=now + timedelta(minutes=5),
            now=now,
        )
    # Expire lease and recover
    row = repo.get(session.id)
    assert row is not None
    repo.update_atomic(
        row,
        expected_version=row.state_version,
        worker_lease_expires_at=now - timedelta(seconds=1),
    )
    recovered = svc.recover_stale_lease(session.id, now=now)
    assert recovered.worker_lease_owner is None


@pytest.mark.asyncio
async def test_conflicting_session_and_memory_audit(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    s1 = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    with pytest.raises(ActivationRejectedError):
        svc.create_session(
            owner=owner,
            engine_strategy_id=qual.engine_strategy_id,
            strategy_version=qual.strategy_version,
            parameter_hash=qual.parameter_hash,
            parameters={},
            qualification_approval_id=qual.id,
            evidence_fingerprint=qual.evidence_fingerprint,
            broker_account_id=account.id,
            instrument="AAPL",
            timeframe="1Day",
            risk_limits=_limits(),
            strategy_db_id=strat.id,
        )
    await svc.activate(s1.id, owner=owner)
    events = (
        db_session.execute(
            text(
                "SELECT event_type FROM audit_events"
                " WHERE entity_id = :eid ORDER BY created_at"
            ),
            {"eid": s1.id},
        )
        .scalars()
        .all()
    )
    assert "PAPER_SESSION_STARTED" in events
    mem = db_session.execute(
        text(
            "SELECT count(*) FROM market_memory_events"
            " WHERE event_type = 'paper_session_event'"
        )
    ).scalar()
    assert mem and mem >= 1


@pytest.mark.asyncio
async def test_transaction_rollback(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_trading_sessions migration not applied")
    owner = _owner()
    account, qual, strat = _seed_account_and_approval(db_session)
    svc = PaperSessionService(
        db_session, broker_source=_broker_source(account)
    )
    nested = db_session.begin_nested()
    session = svc.create_session(
        owner=owner,
        engine_strategy_id=qual.engine_strategy_id,
        strategy_version=qual.strategy_version,
        parameter_hash=qual.parameter_hash,
        parameters={},
        qualification_approval_id=qual.id,
        evidence_fingerprint=qual.evidence_fingerprint,
        broker_account_id=account.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat.id,
    )
    sid = session.id
    nested.rollback()
    assert db_session.get(type(session), sid) is None


def test_broker_isolation_and_no_public_start_route() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "paper_sessions"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.brokers.alpaca")
                assert node.module.split(".")[0] not in {"alpaca", "alpaca_trade_api"}
    from app.main import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any("paper" in p.lower() and "session" in p.lower() and "start" in p.lower() for p in paths)


def test_paper_execute_path_disabled_constant() -> None:
    from app.paper_sessions.runner import PAPER_EXECUTE_ENABLED
    from app.paper_sessions.service import ALLOW_PAPER_EXECUTE_ACTIVATION

    assert PAPER_EXECUTE_ENABLED is False
    assert ALLOW_PAPER_EXECUTE_ACTIVATION is False
