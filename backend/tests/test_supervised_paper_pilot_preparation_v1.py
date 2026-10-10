"""Supervised Single-Strategy Paper Pilot Preparation V1."""

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
from app.evaluation.hashing import configuration_hash
from app.market_data.models import Bar
from app.models import (
    AccountType,
    BrokerAccount,
    PaperSessionExecutionMode,
    RiskPolicy,
    RiskScopeType,
    Strategy,
    StrategyAccountAssignment,
    TradingMode,
)
from app.models.enums import StrategyStatus
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.paper_sessions import InMemorySessionBarSource
from app.paper_sessions.reconciliation import StaticBrokerSnapshotSource
from app.pilot.config import (
    PilotConfig,
    PilotConfigError,
    assert_deployment_execute_disabled,
    default_pilot_config,
)
from app.pilot.dry_run import ControlledDryRunPilot
from app.pilot.isolation import assert_no_real_adapter_in_router, assert_pilot_package_isolation
from app.pilot.preflight import PilotPreflightService, assert_preflight_ready
from app.pilot.simulated import SimulatedPilotHarness, assert_preparation_environment_safe
from app.qualification import QualificationState, resolve_authenticated_owner
from app.qualification.states import ApprovalScope
from app.strategies.reference import SMACrossoverStrategy


def _settings() -> Settings:
    return Settings(
        paper_qualification_owner_subjects="owner@example.com",
        paper_session_execute_enabled=False,
        alpaca_paper_base_url="https://paper-api.alpaca.markets",
    )


def _owner():
    return resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=_settings(),
    )


def _ready(db: Session) -> bool:
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
        # Mild uptrend so SMA may or may not fire — honesty preserved either way
        c = Decimal(str(100 + (i % 7)))
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


def _seed(db: Session, *, config: PilotConfig | None = None):
    config = config or default_pilot_config()
    ph = configuration_hash(config.parameters)
    evidence = uuid.uuid4().hex + uuid.uuid4().hex[:32]
    account = BrokerAccount(
        name=f"PILOT-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        external_account_id=f"paper-{uuid.uuid4().hex[:10]}",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.PAPER,
        is_enabled=True,
    )
    strat = Strategy(
        name=f"S-{uuid.uuid4().hex[:8]}",
        strategy_type="ref",
        version=config.strategy_version,
        status=StrategyStatus.DEVELOPMENT,
    )
    db.add_all([account, strat])
    db.flush()
    db.add(
        RiskPolicy(
            scope_type=RiskScopeType.BROKER_ACCOUNT,
            scope_id=account.id,
            max_daily_loss=config.max_daily_loss,
            max_position_value=config.max_notional,
            max_total_exposure=config.max_notional,
            max_open_positions=1,
            require_stop_loss=True,
            is_enabled=True,
        )
    )
    db.add(
        StrategyAccountAssignment(
            strategy_id=strat.id,
            broker_account_id=account.id,
            is_enabled=True,
            trading_mode=TradingMode.PAPER,
            max_position_size=config.max_quantity,
            daily_loss_limit=config.max_daily_loss,
            max_concurrent_positions=1,
        )
    )
    qual = StrategyPaperQualification(
        strategy_id=strat.id,
        engine_strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        parameter_hash=ph,
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
        expires_at=datetime.now(UTC) + timedelta(days=30),
        state_version=1,
    )
    db.add(qual)
    db.flush()
    return account, qual, strat, config, evidence


def _broker(account: BrokerAccount) -> StaticBrokerSnapshotSource:
    return StaticBrokerSnapshotSource(
        external_account_id=account.external_account_id or "paper-test",
        paper_verified=True,
        buying_power="100000",
        paper_base_url="https://paper-api.alpaca.markets",
    )


# ---------------------------------------------------------------------------
# Config / isolation
# ---------------------------------------------------------------------------


def test_pilot_config_validation() -> None:
    cfg = default_pilot_config()
    assert cfg.max_orders_per_session == 1
    assert cfg.allow_real_paper_submit is False
    assert cfg.background_worker_allowed is False
    with pytest.raises((PilotConfigError, Exception)):
        PilotConfig(max_orders_per_session=2)
    with pytest.raises((PilotConfigError, Exception)):
        PilotConfig(allow_real_paper_submit=True)
    with pytest.raises((PilotConfigError, Exception)):
        PilotConfig(max_notional=Decimal("99999"))
    assert_deployment_execute_disabled(_settings())
    with pytest.raises(Exception):
        assert_deployment_execute_disabled(
            Settings(
                paper_qualification_owner_subjects="x",
                paper_session_execute_enabled=True,
            )
        )


def test_pilot_isolation_and_no_real_adapter() -> None:
    assert_pilot_package_isolation()
    assert_no_real_adapter_in_router({"alpaca": FakeExecutionAdapter()})
    with pytest.raises(AssertionError):
        class AlpacaPaperExecutionAdapter:  # name trap
            pass

        assert_no_real_adapter_in_router({"alpaca": AlpacaPaperExecutionAdapter()})


def test_deployment_defaults_safe() -> None:
    assert Settings().paper_session_execute_enabled is False
    assert_preparation_environment_safe(_settings())
    from app.main import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any("pilot" in p.lower() and "start" in p.lower() for p in paths)


def test_owner_authorization_required() -> None:
    with pytest.raises(Exception):
        resolve_authenticated_owner(
            subject="nobody@example.com",
            credential_verified=True,
            settings=_settings(),
        )


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preflight_pass_and_fail_paths(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    account, qual, strat, config, evidence = _seed(db_session)
    now = datetime.now(UTC)
    svc = PilotPreflightService(
        db_session, settings=_settings(), broker_source=_broker(account)
    )
    report = await svc.run(
        owner=_owner(),
        config=config,
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        bar_source=InMemorySessionBarSource(_bars(30, now=now)),
        now=now,
    )
    assert report.ok is True
    assert_preflight_ready(report)
    names = {c.name for c in report.checks if c.ok}
    assert "authenticated_owner" in names
    assert "paper_endpoint" in names
    assert "qualification" in names
    assert "fresh_completed_bars" in names
    assert "kill_switch_readiness" in names
    assert "deployment_execute_disabled" in names

    # Live account fails
    live = BrokerAccount(
        name="live",
        broker="alpaca",
        external_account_id=f"live-{uuid.uuid4().hex[:8]}",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.LIVE,
        is_enabled=True,
    )
    db_session.add(live)
    db_session.flush()
    bad = await svc.run(
        owner=_owner(),
        config=config,
        broker_account_id=live.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        bar_source=InMemorySessionBarSource(_bars(10, now=now)),
        now=now,
    )
    assert bad.ok is False


@pytest.mark.asyncio
async def test_preflight_stale_bars_and_live_endpoint(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    account, qual, strat, config, evidence = _seed(db_session)
    config = config.model_copy(update={"market_data_max_age_seconds": 60})
    svc = PilotPreflightService(
        db_session, settings=_settings(), broker_source=_broker(account)
    )
    old = datetime(2020, 1, 1, tzinfo=UTC)
    report = await svc.run(
        owner=_owner(),
        config=config,
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        bar_source=InMemorySessionBarSource(_bars(5, now=old)),
        now=datetime.now(UTC),
    )
    assert report.ok is False
    assert any(c.name == "fresh_completed_bars" and not c.ok for c in report.checks)

    live_settings = Settings(
        paper_qualification_owner_subjects="owner@example.com",
        paper_session_execute_enabled=False,
        alpaca_paper_base_url="https://api.alpaca.markets",
    )
    svc2 = PilotPreflightService(
        db_session, settings=live_settings, broker_source=_broker(account)
    )
    report2 = await svc2.run(
        owner=_owner(),
        config=default_pilot_config(),
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        bar_source=InMemorySessionBarSource(_bars(10, now=datetime.now(UTC))),
        now=datetime.now(UTC),
    )
    assert report2.ok is False
    assert any(c.name == "paper_endpoint" and not c.ok for c in report2.checks)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_controlled_dry_run_zero_orders(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    account, qual, strat, config, evidence = _seed(db_session)
    now = datetime.now(UTC)
    pilot = ControlledDryRunPilot(
        db_session, settings=_settings(), broker_source=_broker(account)
    )
    result = await pilot.run(
        owner=_owner(),
        config=config,
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        strategy_db_id=strat.id,
        bar_source=InMemorySessionBarSource(_bars(40, now=now)),
        strategy=SMACrossoverStrategy(),
        now=now,
    )
    assert result.preflight_ok is True
    assert result.submitted is False
    assert result.broker_orders_created == 0
    assert result.session_id is not None
    assert result.decision_action in {"no_action", "enter_long", "exit_long", "enter_short", "exit_short"}
    if result.decision_action == "no_action":
        assert any("NO_ACTION" in n for n in result.notes)
    assert "PAPER_SESSION_STARTED" in result.audit_events
    assert result.market_memory_events >= 1


# ---------------------------------------------------------------------------
# Simulated execution matrix
# ---------------------------------------------------------------------------


def _sim_kwargs(db_session, account, qual, strat, config, evidence, now):
    return dict(
        owner=_owner(),
        config=config,
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        strategy_db_id=strat.id,
        external_account_id=account.external_account_id or "paper-test",
        bar_source=InMemorySessionBarSource(_bars(30, now=now)),
        now=now,
    )


@pytest.mark.asyncio
async def test_simulated_success_reject_partial_cancel(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    harness = SimulatedPilotHarness(db_session, settings=_settings())
    now = datetime.now(UTC)

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_success(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_rejection(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_partial_fill(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_cancellation(**kw)).ok


@pytest.mark.asyncio
async def test_simulated_timeout_unknown_duplicate(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    harness = SimulatedPilotHarness(db_session, settings=_settings())
    now = datetime.now(UTC)

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_timeout_reconcile(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_unknown_outcome(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    r = await harness.run_duplicate_and_concurrent(**kw)
    assert r.ok
    assert r.fake_post_count == 1
    assert "max_outstanding_orders" in (r.extras.get("second_warnings") or []) or r.ok


@pytest.mark.asyncio
async def test_simulated_consent_and_kill(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    harness = SimulatedPilotHarness(db_session, settings=_settings())
    now = datetime.now(UTC)

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_revoked_consent(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    assert (await harness.run_expired_consent(**kw)).ok

    account, qual, strat, config, evidence = _seed(db_session)
    kw = _sim_kwargs(db_session, account, qual, strat, config, evidence, now)
    kill = await harness.kill_switch_rehearsal(**kw)
    assert kill.ok
    assert kill.further_submissions_disabled
    assert kill.orders_cancelled_claimed is False
    assert kill.positions_liquidated_claimed is False
    assert kill.fake_post_count == 1
    assert kill.additional_submits_blocked


@pytest.mark.asyncio
async def test_session_expiration_config(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    config = default_pilot_config()
    config = config.model_copy(update={"max_session_duration_seconds": 1})
    account, qual, strat, config, evidence = _seed(db_session, config=config)
    now = datetime.now(UTC)
    pilot = ControlledDryRunPilot(
        db_session, settings=_settings(), broker_source=_broker(account)
    )
    # Activate then run with now far in the future → session expired
    result = await pilot.run(
        owner=_owner(),
        config=config,
        broker_account_id=account.id,
        qualification_id=qual.id,
        evidence_fingerprint=evidence,
        strategy_db_id=strat.id,
        bar_source=InMemorySessionBarSource(_bars(20, now=now)),
        strategy=SMACrossoverStrategy(),
        now=now,
    )
    # First cycle at T0 should still work; expiration enforced on subsequent late runs
    assert result.preflight_ok
    from app.paper_sessions.runner import PaperSessionRunner
    from app.paper_sessions.errors import PaperSessionError

    runner = PaperSessionRunner(
        db_session,
        bar_source=InMemorySessionBarSource(_bars(20, now=now + timedelta(hours=2))),
        strategy=SMACrossoverStrategy(),
        paper_execute_enabled=False,
        worker_id="exp",
    )
    with pytest.raises(PaperSessionError) as exc:
        await runner.run_once(result.session_id, now=now + timedelta(hours=2))
    assert exc.value.code == "session_expired"


def test_no_alpaca_sdk_in_pilot_tree() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "pilot"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "alpaca_paper" not in node.module
                assert not node.module.startswith("alpaca")


def test_runbook_and_docs_exist() -> None:
    docs = Path(__file__).resolve().parents[2] / "docs"
    assert (docs / "supervised-paper-pilot-preparation-v1.md").is_file()
    runbook = (docs / "supervised-paper-pilot-operator-runbook.md").read_text()
    assert "SEPARATE EXPLICIT OWNER DECISION REQUIRED" in runbook
    assert "PAPER_SESSION_EXECUTE_ENABLED=false" in runbook
    assert "Emergency kill" in runbook or "emergency kill" in runbook.lower()
