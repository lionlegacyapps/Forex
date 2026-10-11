"""Paper Pilot Onboarding & Blocker Remediation V1 — test matrix."""

from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.backtesting import make_bar
from app.backtesting.metrics import PerformanceMetrics
from app.broker_state.models import AccountSnapshot
from app.brokers.execution.fake import FakeExecutionAdapter
from app.core.config import Settings
from app.evaluation.hashing import configuration_hash
from app.evaluation.models import DatasetIdentity, ResearchProvenance, SplitRole
from app.evaluation.walkforward.harness import WalkForwardResult
from app.evaluation.walkforward.reporting import PeriodReport, RoleAggregate
from app.evaluation.walkforward.robustness import RobustnessReport
from app.market_data.errors import (
    AUTHENTICATION_FAILED,
    SUBSCRIPTION_FORBIDDEN,
    MarketDataError,
)
from app.market_data.models import Bar
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.models import AccountType, BrokerAccount, TradingMode
from app.models.enums import QualificationState, StrategyStatus
from app.models.strategy import Strategy
from app.onboarding import (
    OWNER_ALLOWLIST_SETUP_PROCEDURE,
    PaperPilotOnboardingWorkflow,
    owner_allowlist_status,
    persist_qualification_evidence,
    require_authenticated_owner,
    run_sma_crossover_walk_forward,
    verify_and_register_alpaca_paper_account,
)
from app.onboarding.errors import OnboardingBlockedError
from app.onboarding.market_data_check import verify_alpaca_market_data_access
from app.onboarding.qualification_evidence import DEFAULT_PILOT_COSTS, DEFAULT_PILOT_PARAMETERS
from app.paper_sessions.market_data import assert_bar_complete
from app.pilot.config import assert_deployment_execute_disabled, default_pilot_config
from app.pilot.dry_run import ControlledDryRunPilot
from app.pilot.isolation import assert_no_real_adapter_in_router
from app.qualification import (
    ApprovalScope,
    QualificationCriteria,
    resolve_authenticated_owner,
    review_walk_forward_evidence,
)
from app.qualification.errors import UnauthorizedApprovalError


def _ready(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1 FROM strategy_paper_qualifications LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False


def _settings(**kwargs: Any) -> Settings:
    base = dict(
        paper_qualification_owner_subjects="owner@example.com",
        paper_session_execute_enabled=False,
        alpaca_paper_base_url="https://paper-api.alpaca.markets",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_data_feed="iex",
        alpaca_api_key="test-key",
        alpaca_api_secret="test-secret",
    )
    base.update(kwargs)
    return Settings(**base)


def _owner(settings: Settings | None = None):
    cfg = settings or _settings()
    return resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=cfg,
    )


def _bars(n: int = 400) -> list[Bar]:
    """Alternating trend segments so SMA crossover can produce OOS trades."""
    out: list[Bar] = []
    price = Decimal("100")
    start = datetime(2023, 1, 3, 16, 0, tzinfo=UTC)
    for i in range(n):
        # Change direction every 25 bars to create crossovers
        direction = Decimal("1") if (i // 25) % 2 == 0 else Decimal("-1")
        price = price + direction * Decimal("0.8")
        if price < Decimal("20"):
            price = Decimal("20")
        ts = start + timedelta(days=i)
        out.append(
            make_bar(
                "AAPL",
                ts,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                timeframe="1Day",
            )
        )
    return out


def _snapshot(*, external_id: str = "pap-acct-7f21xxxx6b5f", paper: bool = True) -> AccountSnapshot:
    return AccountSnapshot(
        broker="alpaca",
        external_account_id=external_id,
        account_status="ACTIVE",
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        timestamp=datetime.now(UTC),
        paper_verified=paper,
    )


def _synthetic_wf(
    *,
    oos_trades: int = 12,
    oos_windows: int = 2,
    zero_cost: bool = False,
    harness_id: str | None = None,
    config_hash: str | None = None,
    dataset_fp: str | None = None,
) -> WalkForwardResult:
    from app.evaluation.models import StrategyEvaluationRecord

    costs = (
        {"slippage_bps": "0", "commission_per_share": "0", "commission_flat": "0"}
        if zero_cost
        else {"slippage_bps": "5", "commission_per_share": "0.005", "commission_flat": "0"}
    )
    strategy_id = "sma_crossover"
    version = "1.0.0"
    config_hash = config_hash or configuration_hash(DEFAULT_PILOT_PARAMETERS)
    dataset_fp = dataset_fp or ("d" * 64)
    harness_id = harness_id or ("h" * 64)
    evals: list[PeriodReport] = []
    for role in (SplitRole.TRAIN, SplitRole.VALIDATION, SplitRole.OUT_OF_SAMPLE):
        trades = oos_trades if role == SplitRole.OUT_OF_SAMPLE else 5
        m = PerformanceMetrics(
            starting_capital=Decimal("100000"),
            ending_equity=Decimal("100100"),
            net_pnl=Decimal("100"),
            total_return_pct=Decimal("0.1"),
            number_of_trades=trades,
            winning_trades=max(0, trades // 2),
            losing_trades=max(0, trades - trades // 2),
            win_rate=Decimal("50"),
            average_win=Decimal("10"),
            average_loss=Decimal("-10"),
            profit_factor=Decimal("1.2"),
            max_drawdown=Decimal("50"),
            max_drawdown_pct=Decimal("1"),
            expectancy=Decimal("1"),
        )
        rec = StrategyEvaluationRecord(
            evaluation_id=f"e-{role.value}",
            strategy_id=strategy_id,
            strategy_name="SMA",
            strategy_version=version,
            configuration_hash=config_hash,
            parameters=dict(DEFAULT_PILOT_PARAMETERS),
            dataset=DatasetIdentity(
                symbol="AAPL",
                timeframe="1Day",
                fingerprint=dataset_fp,
                bar_count=400,
            ),
            execution_assumptions={"external_broker": False},
            cost_assumptions=costs,
            research=ResearchProvenance(),
            evaluated_at=datetime.now(UTC),
            split_role=role,
            metrics=m,
            paper_eligible=False,
            promotion_blocked=True,
        )
        count = oos_windows if role == SplitRole.OUT_OF_SAMPLE else 1
        for i in range(count):
            evals.append(
                PeriodReport(
                    role=role,
                    window_index=i,
                    evaluation=rec,
                    net_return=m.total_return_pct,
                    win_rate=m.win_rate,
                    profit_factor=m.profit_factor,
                    expectancy=m.expectancy,
                    max_drawdown=m.max_drawdown,
                    trade_count=m.number_of_trades,
                    average_win=m.average_win,
                    average_loss=m.average_loss,
                    transaction_costs=Decimal("2"),
                )
            )
    return WalkForwardResult(
        harness_id=harness_id,
        strategy_id=strategy_id,
        strategy_version=version,
        configuration_hash=config_hash,
        dataset_fingerprint=dataset_fp,
        symbol="AAPL",
        timeframe="1Day",
        mode="rolling",
        parameters=dict(DEFAULT_PILOT_PARAMETERS),
        windows=[],
        period_reports=evals,
        aggregates=[
            RoleAggregate(
                role=SplitRole.OUT_OF_SAMPLE,
                window_count=oos_windows,
                total_trades=oos_trades * oos_windows,
                total_net_pnl=Decimal("200"),
                compounded_return_pct=Decimal("2"),
                max_drawdown_worst=Decimal("50"),
            )
        ],
        robustness=RobustnessReport(oos_window_count=oos_windows),
        paper_eligible=False,
        promotion_blocked=True,
        broker_orders_created=0,
        evaluated_at=datetime.now(UTC),
    )


class _FakePaperReader:
    def __init__(self, snapshot: AccountSnapshot) -> None:
        self._snapshot = snapshot

    async def get_account(self) -> AccountSnapshot:
        return self._snapshot


# ---------------------------------------------------------------------------
# Owner authorization
# ---------------------------------------------------------------------------


def test_owner_allowlist_empty_rejected() -> None:
    cfg = _settings(paper_qualification_owner_subjects="")
    status = owner_allowlist_status(cfg)
    assert status.configured is False
    with pytest.raises(OnboardingBlockedError) as exc:
        require_authenticated_owner(
            subject="anyone@example.com",
            credential_verified=True,
            settings=cfg,
        )
    assert exc.value.code == "owner_allowlist_empty"


def test_correct_owner_authorization() -> None:
    cfg = _settings()
    owner = require_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=cfg,
    )
    assert owner.subject == "owner@example.com"


def test_unauthorized_owner_rejection() -> None:
    cfg = _settings()
    with pytest.raises(UnauthorizedApprovalError):
        require_authenticated_owner(
            subject="intruder@example.com",
            credential_verified=True,
            settings=cfg,
        )
    with pytest.raises(UnauthorizedApprovalError):
        require_authenticated_owner(
            subject="owner@example.com",
            credential_verified=False,
            settings=cfg,
        )


def test_owner_setup_procedure_never_hardcodes_identity() -> None:
    assert "lionlegacyapps@gmail.com" not in OWNER_ALLOWLIST_SETUP_PROCEDURE
    assert "Invent a subject" in OWNER_ALLOWLIST_SETUP_PROCEDURE
    assert "fail-closed" in OWNER_ALLOWLIST_SETUP_PROCEDURE
    src = Path("app/onboarding/owner.py").read_text(encoding="utf-8")
    assert "lionlegacyapps" not in src
    assert "@gmail.com" not in src


# ---------------------------------------------------------------------------
# Broker registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_broker_registration_idempotent(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    cfg = _settings()
    owner = _owner(cfg)
    snap = _snapshot(external_id="idem-ext-001")
    reader = _FakePaperReader(snap)
    first = await verify_and_register_alpaca_paper_account(
        db_session, owner=owner, settings=cfg, reader=reader
    )
    second = await verify_and_register_alpaca_paper_account(
        db_session, owner=owner, settings=cfg, reader=reader
    )
    assert first.created_new is True
    assert second.created_new is False
    assert first.account_id == second.account_id
    assert first.is_enabled is False
    rows = db_session.scalars(
        select(BrokerAccount).where(BrokerAccount.external_account_id == "idem-ext-001")
    ).all()
    assert len(rows) == 1
    assert not hasattr(rows[0], "api_key")
    assert not hasattr(rows[0], "api_secret")


@pytest.mark.asyncio
async def test_live_account_registration_rejection(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    cfg = _settings(alpaca_paper_base_url="https://api.alpaca.markets")
    owner = _owner(_settings())
    with pytest.raises(OnboardingBlockedError) as exc:
        await verify_and_register_alpaca_paper_account(
            db_session, owner=owner, settings=cfg, reader=_FakePaperReader(_snapshot())
        )
    assert exc.value.code in {"paper_endpoint_rejected", "live_endpoint_rejected"}


@pytest.mark.asyncio
async def test_existing_live_row_conflict(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    cfg = _settings()
    owner = _owner(cfg)
    live = BrokerAccount(
        name=f"LIVE-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        external_account_id="conflict-ext",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.LIVE,
        is_enabled=False,
    )
    db_session.add(live)
    db_session.flush()
    with pytest.raises(OnboardingBlockedError) as exc:
        await verify_and_register_alpaca_paper_account(
            db_session,
            owner=owner,
            settings=cfg,
            reader=_FakePaperReader(_snapshot(external_id="conflict-ext")),
        )
    assert exc.value.code == "live_account_conflict"


@pytest.mark.asyncio
async def test_paper_not_verified_rejected(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    cfg = _settings()
    with pytest.raises(OnboardingBlockedError) as exc:
        await verify_and_register_alpaca_paper_account(
            db_session,
            owner=_owner(cfg),
            settings=cfg,
            reader=_FakePaperReader(_snapshot(paper=False)),
        )
    assert exc.value.code == "paper_not_verified"


# ---------------------------------------------------------------------------
# Qualification evidence
# ---------------------------------------------------------------------------


def test_zero_cost_evidence_rejection() -> None:
    wf = _synthetic_wf(zero_cost=True, oos_trades=20)
    report = review_walk_forward_evidence(wf)
    assert any(f.code == "unrealistic_zero_cost_assumptions" for f in report.hard_blockers)


def test_invalid_evidence_insufficient_trades() -> None:
    wf = _synthetic_wf(oos_trades=2, oos_windows=1)
    report = review_walk_forward_evidence(wf)
    assert any(f.code == "insufficient_oos_trades" for f in report.hard_blockers)


def test_missing_qualification_rejection(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    from app.qualification.eligibility import PaperEligibilityService

    svc = PaperEligibilityService(db_session)
    check = svc.check(
        engine_strategy_id="sma_crossover",
        strategy_version="1.0.0",
        parameter_hash=configuration_hash(DEFAULT_PILOT_PARAMETERS),
        evidence_fingerprint="e" * 64,
        broker_account_id=uuid.uuid4(),
    )
    assert check.eligible is False
    assert "no_qualification_record" in check.reasons


def test_expired_qualification_rejection(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    from app.models.strategy_paper_qualification import StrategyPaperQualification
    from app.qualification.eligibility import PaperEligibilityService

    strat = Strategy(
        name=f"Q-{uuid.uuid4().hex[:8]}",
        strategy_type="reference",
        version="1.0.0",
        status=StrategyStatus.DEVELOPMENT,
    )
    account = BrokerAccount(
        name=f"QA-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        external_account_id=f"ext-{uuid.uuid4().hex[:8]}",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.PAPER,
        is_enabled=True,
    )
    db_session.add_all([strat, account])
    db_session.flush()
    ph = configuration_hash(DEFAULT_PILOT_PARAMETERS)
    efp = "e" * 64
    row = StrategyPaperQualification(
        strategy_id=strat.id,
        engine_strategy_id="sma_crossover",
        strategy_version="1.0.0",
        parameter_hash=ph,
        evidence_fingerprint=efp,
        evaluation_id="h" * 64,
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
        approved_at=datetime.now(UTC) - timedelta(days=60),
        expires_at=datetime.now(UTC) - timedelta(days=1),
        state_version=1,
    )
    db_session.add(row)
    db_session.flush()
    check = PaperEligibilityService(db_session).check(
        engine_strategy_id="sma_crossover",
        strategy_version="1.0.0",
        parameter_hash=ph,
        evidence_fingerprint=efp,
        broker_account_id=account.id,
    )
    assert check.eligible is False
    assert any("expired" in r for r in check.reasons)


def test_persist_evidence_never_auto_approves(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    wf = _synthetic_wf(oos_trades=15, oos_windows=2)
    bundle = persist_qualification_evidence(db_session, wf)
    assert bundle.auto_approved is False
    assert bundle.qualification_state != QualificationState.APPROVED_FOR_PAPER.value
    assert bundle.qualification_id is not None


def test_walk_forward_uses_nonzero_costs_and_hashes() -> None:
    bars = _bars(300)
    result = run_sma_crossover_walk_forward(bars)
    assert result.broker_orders_created == 0
    assert result.configuration_hash
    assert result.dataset_fingerprint
    assert len(result.dataset_fingerprint) >= 32
    # Cost model embedded in harness path — review should not flag zero cost
    assert DEFAULT_PILOT_COSTS.commission_per_share > 0
    assert DEFAULT_PILOT_COSTS.slippage_bps > 0
    report = review_walk_forward_evidence(
        result,
        criteria=QualificationCriteria(min_oos_trade_count=0, min_oos_windows=0),
    )
    assert not any(f.code == "unrealistic_zero_cost_assumptions" for f in report.hard_blockers)


# ---------------------------------------------------------------------------
# Market data authentication / feed
# ---------------------------------------------------------------------------


def test_alpaca_default_feed_is_iex() -> None:
    p = AlpacaMarketDataProvider(api_key="k", api_secret="s")
    assert p.feed == "iex"
    assert Settings().alpaca_data_feed == "iex"


@pytest.mark.asyncio
async def test_market_data_subscription_forbidden_not_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AlpacaMarketDataProvider(api_key="k", api_secret="s", feed="sip")

    class _Resp:
        status_code = 403

        def json(self) -> dict:
            return {
                "message": "subscription does not permit querying recent SIP data"
            }

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            assert params and params.get("feed") == "sip"
            assert headers and "APCA-API-KEY-ID" in headers
            assert "APCA-API-SECRET-KEY" in headers
            return _Resp()

    monkeypatch.setattr("app.market_data.providers.alpaca.httpx.AsyncClient", _Client)
    with pytest.raises(MarketDataError) as exc:
        await provider.get_quote("AAPL")
    assert exc.value.code == SUBSCRIPTION_FORBIDDEN


@pytest.mark.asyncio
async def test_market_data_401_authentication_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AlpacaMarketDataProvider(api_key="k", api_secret="s", feed="iex")

    class _Resp:
        status_code = 401

        def json(self) -> dict:
            return {}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.market_data.providers.alpaca.httpx.AsyncClient", _Client)
    with pytest.raises(MarketDataError) as exc:
        await provider.get_quote("AAPL")
    assert exc.value.code == AUTHENTICATION_FAILED


@pytest.mark.asyncio
async def test_valid_market_data_response_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = AlpacaMarketDataProvider(api_key="k", api_secret="s", feed="iex")
    ts = datetime(2024, 6, 3, 16, 0, tzinfo=UTC)

    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {
                "bars": [
                    {
                        "t": ts.isoformat(),
                        "o": "100",
                        "h": "105",
                        "l": "99",
                        "c": "104",
                        "v": "1000",
                    }
                ]
            }

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            assert params.get("feed") == "iex"
            assert "1Day" in str(params.get("timeframe")) or params.get("timeframe") == "1Day"
            return _Resp()

    monkeypatch.setattr("app.market_data.providers.alpaca.httpx.AsyncClient", _Client)
    bars = await provider.get_bars(
        "AAPL",
        timeframe="1Day",
        start=ts - timedelta(days=5),
        end=ts,
    )
    assert len(bars) == 1
    assert bars[0].close == Decimal("104")
    assert_bar_complete(bars[0])


def test_completed_bar_validation() -> None:
    good = make_bar(
        "AAPL",
        datetime.now(UTC),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
    )
    assert_bar_complete(good)
    bad = make_bar(
        "AAPL",
        datetime.now(UTC),
        open=Decimal("10"),
        high=Decimal("8"),
        low=Decimal("9"),
        close=Decimal("11"),
    )
    with pytest.raises(Exception):
        assert_bar_complete(bad)


@pytest.mark.asyncio
async def test_verify_market_data_access_uses_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _settings()
    fake = AsyncMock()
    ts = datetime.now(UTC) - timedelta(days=1)
    fake.get_bars = AsyncMock(
        return_value=[
            make_bar(
                "AAPL",
                ts,
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("1.5"),
                timeframe="1Day",
            )
        ]
    )
    fake.feed = "iex"
    result = await verify_alpaca_market_data_access(settings=cfg, provider=fake)
    assert result.ok is True
    assert result.bars_returned == 1
    fake.get_bars.assert_awaited()


# ---------------------------------------------------------------------------
# Workflow / DRY_RUN / safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_empty_allowlist_fail_closed(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    wf = PaperPilotOnboardingWorkflow(
        db_session, settings=_settings(paper_qualification_owner_subjects="")
    )
    report = await wf.run(
        owner_subject="owner@example.com",
        credential_verified=True,
        skip_live_market_data=True,
        evaluation_bars=_bars(50),
    )
    assert report.blocked is True
    assert report.real_orders_created == 0
    assert report.manual_approval_status == "PENDING"
    assert any(s.step == "verify_authenticated_owner" and s.blocked for s in report.steps)


@pytest.mark.asyncio
async def test_idempotent_onboarding_no_auto_approve(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    cfg = _settings()
    snap = _snapshot(external_id="onboard-ext-1")

    async def _reg(*a, **k):
        from app.onboarding.account import PaperAccountRegistrationResult

        # Use real registration under the hood with fake reader
        return await verify_and_register_alpaca_paper_account(
            db_session,
            owner=_owner(cfg),
            settings=cfg,
            reader=_FakePaperReader(snap),
        )

    monkeypatch.setattr(
        "app.onboarding.workflow.verify_and_register_alpaca_paper_account",
        _reg,
    )
    workflow = PaperPilotOnboardingWorkflow(db_session, settings=cfg)
    bars = _bars(350)
    r1 = await workflow.run(
        owner_subject="owner@example.com",
        credential_verified=True,
        skip_live_market_data=True,
        evaluation_bars=bars,
    )
    r2 = await workflow.run(
        owner_subject="owner@example.com",
        credential_verified=True,
        skip_live_market_data=True,
        evaluation_bars=bars,
    )
    assert r1.account is not None
    assert r2.account is not None
    assert r1.account["account_id"] == r2.account["account_id"]
    assert r1.manual_approval_status == "PENDING"
    assert r2.manual_approval_status == "PENDING"
    assert r1.real_orders_created == 0
    assert r2.real_orders_created == 0
    # Preflight / dry-run blocked until approval
    assert any(
        s.step == "run_one_dry_run_session" and s.blocked for s in r1.steps
    )
    assert any(
        s.step == "obtain_explicit_manual_qualification_approval" and not s.ok
        for s in r1.steps
    )


@pytest.mark.asyncio
async def test_dry_run_zero_orders_and_execute_disabled(db_session: Session) -> None:
    if not _ready(db_session):
        pytest.skip("migrations not applied")
    from app.models import RiskPolicy, RiskScopeType, StrategyAccountAssignment
    from app.models.strategy_paper_qualification import StrategyPaperQualification
    from app.paper_sessions import InMemorySessionBarSource
    from app.paper_sessions.reconciliation import StaticBrokerSnapshotSource
    from app.strategies.reference import SMACrossoverStrategy

    cfg_settings = _settings()
    assert_deployment_execute_disabled(cfg_settings)
    config = default_pilot_config()
    ph = configuration_hash(config.parameters)
    account = BrokerAccount(
        name=f"DRY-{uuid.uuid4().hex[:8]}",
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
    db_session.add_all([account, strat])
    db_session.flush()
    db_session.add(
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
    db_session.add(
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
    efp = uuid.uuid4().hex + uuid.uuid4().hex[:32]
    qual = StrategyPaperQualification(
        strategy_id=strat.id,
        engine_strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        parameter_hash=ph,
        evidence_fingerprint=efp,
        evaluation_id="h" * 64,
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
    db_session.add(qual)
    db_session.flush()

    fake = FakeExecutionAdapter()
    assert_no_real_adapter_in_router({"alpaca": fake})
    now = datetime.now(UTC)
    bars = [
        make_bar(
            "AAPL",
            now - timedelta(days=40 - i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal(str(100 + (i % 7))),
        )
        for i in range(40)
    ]
    pilot = ControlledDryRunPilot(
        db_session,
        settings=cfg_settings,
        broker_source=StaticBrokerSnapshotSource(
            external_account_id=account.external_account_id or "paper-test",
            paper_verified=True,
            buying_power="100000",
            paper_base_url="https://paper-api.alpaca.markets",
        ),
    )
    owner = _owner(cfg_settings)
    result = await pilot.run(
        owner=owner,
        broker_account_id=account.id,
        config=config,
        qualification_id=qual.id,
        evidence_fingerprint=efp,
        strategy_db_id=strat.id,
        bar_source=InMemorySessionBarSource(bars),
        strategy=SMACrossoverStrategy(),
        now=now,
    )
    assert fake.post_count == 0
    assert result.submitted is False
    assert result.broker_orders_created == 0
    assert cfg_settings.paper_session_execute_enabled is False


def test_no_live_trading_and_execute_flag_default() -> None:
    s = Settings()
    assert s.paper_session_execute_enabled is False
    assert s.alpaca_paper_base_url == "https://paper-api.alpaca.markets"
    assert_deployment_execute_disabled(s)


def test_onboarding_package_has_no_order_submission() -> None:
    root = Path("app/onboarding")
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        text = src.lower()
        assert "place_order" not in text
        assert "/v2/orders" not in text
        assert "tradingclient" not in text
        # approve must not be called from qualification_evidence
        if path.name == "qualification_evidence.py":
            assert ".approve(" not in src


def test_default_pilot_parameters_match_config() -> None:
    cfg = default_pilot_config()
    assert cfg.strategy_id == "sma_crossover"
    assert cfg.strategy_version == "1.0.0"
    for key, value in DEFAULT_PILOT_PARAMETERS.items():
        assert cfg.parameters[key] == value
