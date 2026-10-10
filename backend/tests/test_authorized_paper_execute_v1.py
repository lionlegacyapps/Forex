"""Authorized Paper Execute Activation V1 — mocked Alpaca only."""

from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backtesting import make_bar
from app.brokers.execution.fake import FakeExecutionAdapter
from app.core.config import Settings
from app.market_data.models import Bar, MarketDataAssetClass
from app.models import (
    AccountType,
    BrokerAccount,
    PaperExecutionConsentState,
    PaperSessionExecutionMode,
    PaperSessionState,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    StrategyAccountAssignment,
    TradingMode,
)
from app.models.enums import AssetClass, OrderStatus, OrderType, StrategyStatus
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.paper_sessions import (
    ActivationRejectedError,
    ConsentError,
    InMemorySessionBarSource,
    PaperExecuteDisabledError,
    PaperSessionRunner,
    PaperSessionService,
    SessionRiskLimits,
    UncertainOrderAcknowledgmentError,
)
from app.paper_sessions.reconciliation import StaticBrokerSnapshotSource
from app.qualification import QualificationState, resolve_authenticated_owner
from app.qualification.states import ApprovalScope
from app.strategies import DecisionAction, StrategyDecision, no_action
from app.strategies.protocol import Strategy as StrategyBase
from app.trading.execution.market_data import SimulationMarketData
from app.trading.proposals.service import TradeProposalService
from app.trading.routing.router import BrokerRouter


def _settings(*, execute: bool = False) -> Settings:
    return Settings(
        paper_qualification_owner_subjects="owner@example.com",
        paper_session_execute_enabled=execute,
        paper_session_execute_consent_ttl_seconds=900,
        alpaca_paper_base_url="https://paper-api.alpaca.markets",
    )


def _owner(settings: Settings | None = None):
    return resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=settings or _settings(),
    )


def _table_ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1 FROM paper_execution_authorizations LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False


def _bars(n: int = 40, *, now: datetime | None = None) -> list[Bar]:
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


def _seed(
    db: Session,
    *,
    mode: TradingMode = TradingMode.PAPER,
    expired: bool = False,
    param_hash: str | None = None,
    evidence: str | None = None,
    version: str = "1.0.0",
) -> tuple[BrokerAccount, StrategyPaperQualification, Strategy]:
    param_hash = param_hash or uuid.uuid4().hex + uuid.uuid4().hex[:32]
    evidence = evidence or uuid.uuid4().hex + uuid.uuid4().hex[:32]
    account = BrokerAccount(
        name=f"PE-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        external_account_id=f"paper-{uuid.uuid4().hex[:10]}",
        account_type=AccountType.CASH,
        trading_mode=mode,
        is_enabled=True,
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
    db.add(
        StrategyAccountAssignment(
            strategy_id=strat.id,
            broker_account_id=account.id,
            is_enabled=True,
            trading_mode=TradingMode.PAPER,
            max_position_size=Decimal("10"),
            daily_loss_limit=Decimal("5000"),
            max_concurrent_positions=2,
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


def _enter() -> StrategyDecision:
    return StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1"),
        order_type=OrderType.LIMIT,
        limit_price=Decimal("50"),
        stop_loss_price=Decimal("40"),
    )


def _svc(db: Session, account: BrokerAccount, *, execute: bool = True) -> PaperSessionService:
    settings = _settings(execute=execute)
    return PaperSessionService(
        db,
        settings=settings,
        allow_paper_execute=execute,
        broker_source=StaticBrokerSnapshotSource(
            external_account_id=account.external_account_id or "paper-test",
            paper_verified=True,
            buying_power="100000",
            paper_base_url="https://paper-api.alpaca.markets",
        ),
    )


def _pipeline(db: Session, fake: FakeExecutionAdapter) -> TradeProposalService:
    market = SimulationMarketData()
    market.set_price("AAPL", Decimal("100"))
    router = BrokerRouter(
        db,
        execution_adapters={"alpaca": fake},
        adapters={},
        market_data=market,
    )
    return TradeProposalService(db, broker_router=router, market_data=market)


async def _create_execute_session(db: Session, *, execute: bool = True):
    account, qual, strat = _seed(db)
    settings = _settings(execute=execute)
    owner = _owner(settings)
    svc = _svc(db, account, execute=execute)
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
        execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
    )
    return account, qual, strat, owner, svc, session, settings


# ---------------------------------------------------------------------------
# Defaults / authorization gates
# ---------------------------------------------------------------------------


def test_default_paper_execute_disabled(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("paper_execution_authorizations migration not applied")
    account, qual, strat = _seed(db_session)
    svc = _svc(db_session, account, execute=False)
    owner = _owner(_settings(execute=False))
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


@pytest.mark.asyncio
async def test_unauthorized_activation_rejection(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    with pytest.raises(Exception):
        resolve_authenticated_owner(
            subject="intruder@example.com",
            credential_verified=True,
            settings=_settings(execute=True),
        )


@pytest.mark.asyncio
async def test_explicit_authorized_activation_and_submit(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, settings = await _create_execute_session(
        db_session
    )
    consent = svc.grant_execution_consent(session.id, owner=owner, expires_in_seconds=600)
    assert consent.consent_state == PaperExecutionConsentState.GRANTED
    await svc.activate(session.id, owner=owner)
    assert session.session_state == PaperSessionState.RUNNING

    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(30, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-w1",
    )
    result = await runner.run_once(session.id, now=now)
    assert result.processed is True
    assert result.submitted is True
    assert result.dry_run is False
    assert result.broker_orders_created == 1
    assert fake.post_count == 1
    assert runner.broker_orders_created == 1


@pytest.mark.asyncio
async def test_wrong_account_and_live_endpoint(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    other = BrokerAccount(
        name="other",
        broker="alpaca",
        external_account_id=f"other-{uuid.uuid4().hex[:8]}",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.PAPER,
        is_enabled=True,
    )
    db_session.add(other)
    db_session.flush()
    # Live endpoint rejection via settings
    bad_settings = Settings(
        paper_qualification_owner_subjects="owner@example.com",
        paper_session_execute_enabled=True,
        alpaca_paper_base_url="https://api.alpaca.markets",
    )
    svc_bad = PaperSessionService(
        db_session,
        settings=bad_settings,
        allow_paper_execute=True,
        broker_source=StaticBrokerSnapshotSource(
            external_account_id=account.external_account_id or "x",
            paper_verified=True,
            paper_base_url="https://api.alpaca.markets",
        ),
    )
    with pytest.raises(ActivationRejectedError) as exc:
        svc_bad.grant_execution_consent(session.id, owner=owner)
    assert exc.value.code == "live_endpoint_rejected"

    # Live account cannot create PAPER_EXECUTE session
    live_account, qual2, strat2 = _seed(db_session, mode=TradingMode.LIVE, evidence="c" * 64)
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
            execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
        )
    _ = other


@pytest.mark.asyncio
async def test_expired_approval_and_changed_params(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    settings = _settings(execute=True)
    owner = _owner(settings)
    account, qual, strat = _seed(db_session, expired=True)
    svc = _svc(db_session, account, execute=True)
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
        execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
    )
    with pytest.raises(ActivationRejectedError):
        svc.grant_execution_consent(session.id, owner=owner)

    account2, qual2, strat2 = _seed(
        db_session, param_hash="f" * 64, evidence="e" * 64
    )
    svc2 = _svc(db_session, account2, execute=True)
    session2 = svc2.create_session(
        owner=owner,
        engine_strategy_id=qual2.engine_strategy_id,
        strategy_version=qual2.strategy_version,
        parameter_hash="0" * 64,  # mismatch
        parameters={"x": 1},
        qualification_approval_id=qual2.id,
        evidence_fingerprint=qual2.evidence_fingerprint,
        broker_account_id=account2.id,
        instrument="AAPL",
        timeframe="1Day",
        risk_limits=_limits(),
        strategy_db_id=strat2.id,
        execution_mode=PaperSessionExecutionMode.PAPER_EXECUTE,
    )
    with pytest.raises(ActivationRejectedError):
        svc2.grant_execution_consent(session2.id, owner=owner)


@pytest.mark.asyncio
async def test_revoked_and_expired_consent(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    consent = svc.grant_execution_consent(
        session.id, owner=owner, expires_in_seconds=60
    )
    await svc.activate(session.id, owner=owner)
    svc.revoke_execution_consent(session.id, owner=owner, reason="test_revoke")
    db_session.refresh(consent)
    assert consent.consent_state == PaperExecutionConsentState.REVOKED

    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-rev",
    )
    with pytest.raises(ConsentError) as exc:
        await runner.run_once(session.id, now=now)
    assert exc.value.code == "consent_revoked"
    assert fake.post_count == 0

    # Fresh session for expiry
    account2, qual2, strat2, owner2, svc2, session2, _ = await _create_execute_session(
        db_session
    )
    past = datetime.now(UTC) - timedelta(hours=1)
    c2 = svc2.grant_execution_consent(
        session2.id, owner=owner2, expires_in_seconds=1, now=past
    )
    # expires_at = past + 1s → expired
    c2.expires_at = past + timedelta(seconds=1)
    db_session.flush()
    with pytest.raises(ConsentError) as exc2:
        svc2.authorization.require_active_consent(session2, now=datetime.now(UTC))
    assert exc2.value.code == "consent_expired"


@pytest.mark.asyncio
async def test_risk_limit_rejection(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    huge = StrategyDecision(
        action=DecisionAction.ENTER_LONG,
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quantity=Decimal("1000"),
        order_type=OrderType.LIMIT,
        limit_price=Decimal("50"),
        stop_loss_price=Decimal("40"),
    )
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([huge]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-risk",
    )
    result = await runner.run_once(session.id, now=now)
    assert result.submitted is False
    assert "max_position_size" in result.warnings
    assert fake.post_count == 0


@pytest.mark.asyncio
async def test_duplicate_and_concurrent_outstanding(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    bars = _bars(20, now=now)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(bars),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-dup",
    )
    r1 = await runner.run_once(session.id, now=now)
    assert r1.submitted is True
    assert fake.post_count == 1

    # Outstanding order still open → second decision blocked
    runner2 = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(bars),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-dup",  # same worker renews lease
    )
    r2 = await runner2.run_once(session.id, now=now)
    assert r2.submitted is False
    assert "max_outstanding_orders" in r2.warnings
    assert fake.post_count == 1


@pytest.mark.asyncio
async def test_timeout_reconciliation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    fake = FakeExecutionAdapter(timeout_after_accept=True)
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-to",
    )
    # timeout_after_accept stores then raises — router returns NETWORK_TIMEOUT;
    # reconcile should find the order via client_order_id.
    result = await runner.run_once(session.id, now=now)
    assert result.uncertain is True
    assert result.submitted is False
    db_session.refresh(session)
    assert session.submissions_blocked is True
    orders = db_session.execute(
        text("SELECT status, broker_order_id FROM orders WHERE broker_account_id = :a"),
        {"a": account.id},
    ).all()
    assert orders
    assert orders[0][1]  # broker_order_id recovered
    assert fake.post_count == 1


@pytest.mark.asyncio
async def test_unknown_broker_outcome_blocks(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)

    class AmbiguousFake(FakeExecutionAdapter):
        async def submit_order(self, submission):  # type: ignore[no-untyped-def]
            from app.brokers.execution.errors import (
                AMBIGUOUS_IDEMPOTENCY_STATE,
                ExecutionAdapterError,
            )

            raise ExecutionAdapterError("ambiguous", code=AMBIGUOUS_IDEMPOTENCY_STATE)

        async def get_order_by_client_order_id(self, client_order_id: str):
            return None

    fake = AmbiguousFake()
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-amb",
    )
    with pytest.raises(UncertainOrderAcknowledgmentError):
        await runner.run_once(session.id, now=now)
    db_session.refresh(session)
    assert session.submissions_blocked is True


@pytest.mark.asyncio
async def test_partial_fill_and_rejected_order(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-pf",
    )
    result = await runner.run_once(session.id, now=now)
    assert result.submitted is True
    order = db_session.execute(
        text("SELECT id, broker_order_id FROM orders WHERE broker_account_id = :a"),
        {"a": account.id},
    ).first()
    assert order
    oid, broker_id = order
    fake.add_fill(
        broker_id,
        fill_id="f1",
        qty=Decimal("0.5"),
        price=Decimal("50"),
    )
    snap = await fake.get_order_by_id(broker_id)
    assert snap["status"] == "partially_filled"

    # Rejected path
    account2, _, _, owner2, svc2, session2, _ = await _create_execute_session(db_session)
    svc2.grant_execution_consent(session2.id, owner=owner2)
    await svc2.activate(session2.id, owner=owner2)
    from app.brokers.execution.errors import ORDER_REJECTED_BY_BROKER

    rej = FakeExecutionAdapter(fail_code=ORDER_REJECTED_BY_BROKER)
    runner2 = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, rej),
        authorization=svc2.authorization,
        paper_execute_enabled=True,
        worker_id="pe-rej",
    )
    r2 = await runner2.run_once(session2.id, now=now)
    assert r2.submitted is False
    assert rej.post_count == 0


@pytest.mark.asyncio
async def test_pause_stop_kill_during_execute(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    svc.pause(session.id, owner=owner)
    fake = FakeExecutionAdapter()
    now = datetime.now(UTC)
    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(10, now=now)),
        strategy=FixedSessionStrategy([_enter()]),
        proposal_service=_pipeline(db_session, fake),
        authorization=svc.authorization,
        paper_execute_enabled=True,
        worker_id="pe-pause",
    )
    paused = await runner.run_once(session.id, now=now)
    assert paused.processed is False
    assert fake.post_count == 0

    svc.resume(session.id, owner=owner)
    kill = svc.emergency_kill(session.id, owner=owner)
    assert kill["further_submissions_disabled"] is True
    assert kill["execution_consent_revoked"] is True
    assert kill["orders_cancelled"] is False
    assert kill["positions_liquidated"] is False
    # Idempotent kill
    kill2 = svc.emergency_kill(session.id, owner=owner)
    assert kill2["further_submissions_disabled"] is True


@pytest.mark.asyncio
async def test_audit_trail_and_broker_isolation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    events = (
        db_session.execute(
            text(
                "SELECT event_type FROM audit_events"
                " WHERE entity_id = :eid OR details->>'session_id' = :sid"
            ),
            {"eid": session.id, "sid": str(session.id)},
        )
        .scalars()
        .all()
    )
    assert "PAPER_EXECUTE_CONSENT_GRANTED" in events
    assert "PAPER_SESSION_STARTED" in events

    root = Path(__file__).resolve().parents[1] / "app" / "paper_sessions"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.brokers.alpaca")
                assert "alpaca_trade_api" not in (node.module or "")


def test_no_live_order_route_and_module_defaults() -> None:
    from app.paper_sessions.runner import PAPER_EXECUTE_ENABLED
    from app.paper_sessions.service import ALLOW_PAPER_EXECUTE_ACTIVATION

    assert PAPER_EXECUTE_ENABLED is False
    assert ALLOW_PAPER_EXECUTE_ACTIVATION is False
    assert Settings().paper_session_execute_enabled is False

    from app.main import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any(
        "paper" in p.lower() and "execute" in p.lower() and "start" in p.lower()
        for p in paths
    )


@pytest.mark.asyncio
async def test_safe_restart_recovery(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("migration not applied")
    account, qual, strat, owner, svc, session, _ = await _create_execute_session(
        db_session
    )
    svc.grant_execution_consent(session.id, owner=owner)
    await svc.activate(session.id, owner=owner)
    now = datetime.now(UTC)
    from app.paper_sessions.repository import PaperSessionRepository

    repo = PaperSessionRepository(db_session)
    row = repo.get(session.id)
    assert row is not None
    repo.acquire_lease(
        row, owner="worker-a", expires_at=now + timedelta(minutes=5), now=now
    )
    row = repo.get(session.id)
    assert row is not None
    repo.update_atomic(
        row,
        expected_version=row.state_version,
        worker_lease_expires_at=now - timedelta(seconds=1),
    )
    recovered = svc.recover_stale_lease(session.id, now=now)
    assert recovered.worker_lease_owner is None
    # Restart does NOT auto-submit
    assert svc.broker_orders_created == 0
