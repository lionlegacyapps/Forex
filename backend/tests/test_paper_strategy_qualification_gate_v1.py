"""Paper Strategy Qualification Gate V1 — test matrix."""

from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backtesting import BacktestCostModel, make_bar
from app.backtesting.metrics import PerformanceMetrics
from app.core.config import Settings
from app.evaluation.models import DatasetIdentity, ResearchProvenance, SplitRole
from app.evaluation.walkforward import (
    SplitSpec,
    WalkForwardHarness,
    WindowMode,
)
from app.evaluation.walkforward.harness import WalkForwardResult
from app.evaluation.walkforward.reporting import PeriodReport, RoleAggregate
from app.evaluation.walkforward.robustness import RobustnessReport
from app.models import AccountType, BrokerAccount, Strategy, TradingMode
from app.models.enums import StrategyStatus
from app.qualification import (
    ConcurrentStateError,
    IllegalTransitionError,
    PaperEligibilityService,
    PaperQualificationService,
    QualificationCriteria,
    QualificationRecommendation,
    QualificationState,
    UnauthorizedApprovalError,
    evidence_fingerprint,
    resolve_authenticated_owner,
    review_walk_forward_evidence,
)
from app.qualification.states import assert_transition
from app.strategies.reference.sma_crossover import SMACrossoverStrategy


def _ts(day: int) -> datetime:
    return datetime(2024, 1, 1, 16, 0, tzinfo=UTC) + timedelta(days=day - 1)


def _bars(n: int = 90) -> list:
    out = []
    for i in range(n):
        c = Decimal(str(100 + i))
        out.append(
            make_bar(
                "AAPL",
                _ts(i + 1),
                open=c,
                high=c + Decimal("1"),
                low=c - Decimal("1"),
                close=c,
            )
        )
    return out


def _metrics(*, trades: int = 12, net: str = "100", dd: str = "10") -> PerformanceMetrics:
    return PerformanceMetrics(
        starting_capital=Decimal("100000"),
        ending_equity=Decimal("100000") + Decimal(net),
        net_pnl=Decimal(net),
        total_return_pct=Decimal(net) / Decimal("1000"),
        number_of_trades=trades,
        winning_trades=max(0, trades // 2),
        losing_trades=max(0, trades - trades // 2),
        win_rate=Decimal("50"),
        average_win=Decimal("10"),
        average_loss=Decimal("-10"),
        profit_factor=Decimal("1.2"),
        max_drawdown=Decimal(dd),
        max_drawdown_pct=Decimal("1"),
        expectancy=Decimal("1"),
    )


def _synthetic_wf(
    *,
    oos_trades: int = 12,
    oos_windows: int = 2,
    zero_cost: bool = False,
    net: str = "100",
    dd: str = "10",
    harness_id: str = "h" * 64,
    strategy_id: str = "sma_crossover",
    version: str = "1.0.0",
    config_hash: str = "c" * 64,
    dataset_fp: str = "d" * 64,
    paper_eligible: bool = False,
    promotion_blocked: bool = True,
) -> WalkForwardResult:
    from app.evaluation.models import StrategyEvaluationRecord

    costs = (
        {"slippage_bps": "0", "commission_per_share": "0", "commission_flat": "0"}
        if zero_cost
        else {"slippage_bps": "5", "commission_per_share": "0", "commission_flat": "1"}
    )
    evals: list[PeriodReport] = []
    for role in (SplitRole.TRAIN, SplitRole.VALIDATION, SplitRole.OUT_OF_SAMPLE):
        trades = oos_trades if role == SplitRole.OUT_OF_SAMPLE else 5
        m = _metrics(trades=trades, net=net, dd=dd)
        rec = StrategyEvaluationRecord(
            evaluation_id=f"e-{role.value}",
            strategy_id=strategy_id,
            strategy_name="SMA",
            strategy_version=version,
            configuration_hash=config_hash,
            parameters={"fast_period": 5},
            dataset=DatasetIdentity(
                symbol="AAPL",
                timeframe="1Day",
                fingerprint=dataset_fp,
                bar_count=90,
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
        # Duplicate OOS period reports to simulate window count
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

    oos_total = oos_trades * oos_windows
    aggregates = [
        RoleAggregate(
            role=SplitRole.TRAIN,
            window_count=1,
            total_trades=5,
            total_net_pnl=Decimal("10"),
            compounded_return_pct=Decimal("1"),
        ),
        RoleAggregate(
            role=SplitRole.VALIDATION,
            window_count=1,
            total_trades=5,
            total_net_pnl=Decimal("5"),
            compounded_return_pct=Decimal("0.5"),
        ),
        RoleAggregate(
            role=SplitRole.OUT_OF_SAMPLE,
            window_count=oos_windows,
            total_trades=oos_total,
            total_net_pnl=Decimal(net) * oos_windows,
            compounded_return_pct=Decimal("2"),
            max_drawdown_worst=Decimal(dd),
        ),
    ]
    return WalkForwardResult(
        harness_id=harness_id,
        strategy_id=strategy_id,
        strategy_version=version,
        configuration_hash=config_hash,
        dataset_fingerprint=dataset_fp,
        symbol="AAPL",
        timeframe="1Day",
        mode="rolling",
        parameters={"fast_period": 5},
        windows=[],
        period_reports=evals,
        aggregates=aggregates,
        robustness=RobustnessReport(oos_window_count=oos_windows),
        paper_eligible=paper_eligible,
        promotion_blocked=promotion_blocked,
        broker_orders_created=0,
        evaluated_at=datetime.now(UTC),
    )


def _owner(settings: Settings | None = None):
    cfg = settings or Settings(
        paper_qualification_owner_subjects="owner@example.com",
    )
    return resolve_authenticated_owner(
        subject="owner@example.com",
        credential_verified=True,
        settings=cfg,
    )


def _table_ready(db_session: Session) -> bool:
    try:
        db_session.execute(text("SELECT 1 FROM strategy_paper_qualifications LIMIT 1"))
        return True
    except Exception:
        db_session.rollback()
        return False


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_default_unapproved_state() -> None:
    assert QualificationState.DRAFT.value == "draft"
    assert QualificationState.APPROVED_FOR_PAPER != QualificationState.DRAFT


def test_legal_and_illegal_transitions() -> None:
    assert_transition(QualificationState.DRAFT, QualificationState.EVALUATION_REQUIRED)
    assert_transition(
        QualificationState.REVIEW_REQUIRED, QualificationState.APPROVED_FOR_PAPER
    )
    with pytest.raises(IllegalTransitionError):
        assert_transition(QualificationState.DRAFT, QualificationState.APPROVED_FOR_PAPER)
    with pytest.raises(IllegalTransitionError):
        assert_transition(
            QualificationState.REJECTED, QualificationState.APPROVED_FOR_PAPER
        )


# ---------------------------------------------------------------------------
# Evidence validation
# ---------------------------------------------------------------------------


def test_missing_oos_and_insufficient_trades() -> None:
    wf = _synthetic_wf(oos_trades=0, oos_windows=0)
    # Force empty OOS aggregate
    wf.aggregates = [a for a in wf.aggregates if a.role != SplitRole.OUT_OF_SAMPLE]
    wf.period_reports = [p for p in wf.period_reports if p.role != SplitRole.OUT_OF_SAMPLE]
    report = review_walk_forward_evidence(wf)
    assert report.recommendation == QualificationRecommendation.INSUFFICIENT_EVIDENCE
    codes = {f.code for f in report.hard_blockers}
    assert "missing_oos_evidence" in codes or "insufficient_oos_windows" in codes


def test_insufficient_trade_samples_hard_blocker() -> None:
    wf = _synthetic_wf(oos_trades=2, oos_windows=1)
    report = review_walk_forward_evidence(wf)
    assert any(f.code == "insufficient_oos_trades" for f in report.hard_blockers)
    assert report.recommendation == QualificationRecommendation.INSUFFICIENT_EVIDENCE


def test_excessive_drawdown_hard_blocker() -> None:
    wf = _synthetic_wf(dd="999999")
    report = review_walk_forward_evidence(
        wf, criteria=QualificationCriteria(max_drawdown_abs=Decimal("100"))
    )
    assert any(f.code == "excessive_drawdown" for f in report.hard_blockers)
    assert report.recommendation == QualificationRecommendation.REJECT_RECOMMENDED


def test_unrealistic_zero_cost_hard_blocker() -> None:
    wf = _synthetic_wf(zero_cost=True)
    report = review_walk_forward_evidence(wf)
    assert any(f.code == "unrealistic_zero_cost_assumptions" for f in report.hard_blockers)


def test_missing_reproducibility_metadata() -> None:
    wf = _synthetic_wf(harness_id="")
    report = review_walk_forward_evidence(wf)
    assert any(f.code == "missing_reproducibility_metadata" for f in report.hard_blockers)


def test_eligible_for_review_with_valid_evidence() -> None:
    wf = _synthetic_wf()
    report = review_walk_forward_evidence(wf)
    assert not report.has_hard_blockers
    assert report.recommendation == QualificationRecommendation.ELIGIBLE_FOR_REVIEW


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_unauthorized_approval_rejection() -> None:
    with pytest.raises(UnauthorizedApprovalError):
        resolve_authenticated_owner(
            subject="owner@example.com",
            credential_verified=False,
            settings=Settings(paper_qualification_owner_subjects="owner@example.com"),
        )
    with pytest.raises(UnauthorizedApprovalError):
        resolve_authenticated_owner(
            subject="intruder@example.com",
            credential_verified=True,
            settings=Settings(paper_qualification_owner_subjects="owner@example.com"),
        )
    with pytest.raises(UnauthorizedApprovalError):
        resolve_authenticated_owner(
            subject="owner@example.com",
            credential_verified=True,
            settings=Settings(paper_qualification_owner_subjects=""),
        )


# ---------------------------------------------------------------------------
# Persistence + workflow
# ---------------------------------------------------------------------------


def test_approval_workflow_and_audit(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    assert row.qualification_state == QualificationState.DRAFT

    # Idempotent create
    row2 = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    assert row2.id == row.id

    row, report = svc.submit_walk_forward_evidence(row.id, wf)
    assert report.recommendation == QualificationRecommendation.ELIGIBLE_FOR_REVIEW
    assert row.qualification_state == QualificationState.REVIEW_REQUIRED

    owner = _owner()
    approved = svc.approve(row.id, owner=owner)
    assert approved.qualification_state == QualificationState.APPROVED_FOR_PAPER
    assert approved.approval_scope.value == "paper_only"
    assert approved.approved_by_actor_reference == "owner@example.com"
    assert approved.expires_at is not None

    events = (
        db_session.execute(
            text(
                "SELECT event_type FROM audit_events"
                " WHERE entity_id = :eid ORDER BY created_at"
            ),
            {"eid": approved.id},
        )
        .scalars()
        .all()
    )
    assert "PAPER_QUALIFICATION_APPROVED" in events
    assert svc.broker_orders_created == 0


def test_approval_blocked_by_hard_blockers(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf(zero_cost=True, oos_trades=20)
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, report = svc.submit_walk_forward_evidence(row.id, wf)
    assert report.has_hard_blockers
    # Stay evaluated — not review_required
    assert row.qualification_state == QualificationState.EVALUATED
    with pytest.raises(Exception):
        svc.approve(row.id, owner=_owner())


def test_parameter_and_version_invalidation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    row = svc.approve(row.id, owner=_owner())
    assert row.qualification_state == QualificationState.APPROVED_FOR_PAPER

    row = svc.invalidate_for_change(
        row.id, reason="parameter_change", new_parameter_hash="f" * 64
    )
    assert row.qualification_state == QualificationState.EVALUATION_REQUIRED

    # Re-approve path requires new evidence + review — cannot reuse silently
    with pytest.raises(Exception):
        svc.approve(row.id, owner=_owner())


def test_evidence_change_invalidation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    row = svc.approve(row.id, owner=_owner())
    row = svc.invalidate_for_change(
        row.id, reason="evidence_replaced", new_evidence_fingerprint="a" * 64
    )
    assert row.qualification_state == QualificationState.EVALUATION_REQUIRED


def test_strategy_version_change_invalidation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    row = svc.approve(row.id, owner=_owner())
    row = svc.invalidate_for_change(
        row.id, reason="version_bump", new_strategy_version="2.0.0"
    )
    assert row.qualification_state == QualificationState.EVALUATION_REQUIRED


def test_expiration_and_revocation(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    past = datetime.now(UTC) - timedelta(days=1)
    row = svc.approve(row.id, owner=_owner(), expires_at=past, now=past - timedelta(hours=1))
    row = svc.expire_if_needed(row.id, now=datetime.now(UTC))
    assert row.qualification_state == QualificationState.EXPIRED

    # Fresh approval then revoke
    wf2 = _synthetic_wf(harness_id="b" * 64, config_hash="e" * 64, dataset_fp="f" * 64)
    efp2 = evidence_fingerprint(
        harness_id=wf2.harness_id,
        strategy_id=wf2.strategy_id,
        strategy_version=wf2.strategy_version,
        parameter_hash=wf2.configuration_hash,
        dataset_fingerprint=wf2.dataset_fingerprint,
    )
    row = svc.create_draft(
        engine_strategy_id=wf2.strategy_id,
        strategy_version=wf2.strategy_version,
        parameter_hash=wf2.configuration_hash,
        evidence_fingerprint=efp2,
        evaluation_id=wf2.harness_id,
        dataset_fingerprint=wf2.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf2)
    row = svc.approve(row.id, owner=_owner())
    row = svc.revoke(row.id, owner=_owner(), reason="operator_revoke")
    assert row.qualification_state == QualificationState.REVOKED
    # Cannot silently reactivate
    with pytest.raises(Exception):
        svc.approve(row.id, owner=_owner())


def test_manual_rejection_with_reason(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    row = svc.reject(row.id, owner=_owner(), reason="not_acceptable")
    assert row.qualification_state == QualificationState.REJECTED
    assert row.rejection_reason == "not_acceptable"


def test_concurrent_state_changes(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    # Stale version simulate
    stale_version = row.state_version - 1
    from app.qualification.repository import QualificationRepository

    with pytest.raises(ConcurrentStateError):
        QualificationRepository(db_session).transition_atomic(
            row,
            expected_version=stale_version,
            new_state=QualificationState.APPROVED_FOR_PAPER,
        )


def test_paper_only_scope_and_live_account_rejection(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    row = svc.approve(row.id, owner=_owner())
    assert row.approval_scope.value == "paper_only"

    live = BrokerAccount(
        name=f"Live-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.LIVE,
        is_enabled=True,
    )
    paper = BrokerAccount(
        name=f"Paper-{uuid.uuid4().hex[:8]}",
        broker="alpaca",
        account_type=AccountType.CASH,
        trading_mode=TradingMode.PAPER,
        is_enabled=False,
    )
    db_session.add_all([live, paper])
    db_session.flush()

    elig = PaperEligibilityService(db_session)
    live_check = elig.check(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        broker_account_id=live.id,
    )
    assert live_check.eligible is False
    assert "live_account_rejected" in live_check.reasons
    assert live_check.live_trading_authorized is False
    assert live_check.orders_authorized_by_check is False
    assert live_check.account_enabled_by_check is False

    paper_check = elig.check(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        broker_account_id=paper.id,
    )
    assert paper_check.eligible is True
    assert paper_check.account_is_enabled is False
    assert "account_not_enabled" in paper_check.reasons


def test_no_automatic_promotion_strategy_status_unchanged(db_session: Session) -> None:
    if not _table_ready(db_session):
        pytest.skip("strategy_paper_qualifications migration not applied")

    strat = Strategy(
        name=f"Qual-{uuid.uuid4().hex[:8]}",
        strategy_type="ref",
        version="1.0.0",
        status=StrategyStatus.DEVELOPMENT,
    )
    db_session.add(strat)
    db_session.flush()
    wf = _synthetic_wf()
    efp = evidence_fingerprint(
        harness_id=wf.harness_id,
        strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        dataset_fingerprint=wf.dataset_fingerprint,
    )
    svc = PaperQualificationService(db_session)
    row = svc.create_draft(
        engine_strategy_id=wf.strategy_id,
        strategy_version=wf.strategy_version,
        parameter_hash=wf.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=wf.harness_id,
        dataset_fingerprint=wf.dataset_fingerprint,
        strategy_db_id=strat.id,
    )
    row, _ = svc.submit_walk_forward_evidence(row.id, wf)
    svc.approve(row.id, owner=_owner())
    db_session.refresh(strat)
    assert strat.status == StrategyStatus.DEVELOPMENT


def test_walk_forward_integration_compatible() -> None:
    bars = _bars(80)
    result = WalkForwardHarness(
        costs=BacktestCostModel(commission_flat=Decimal("1"), slippage_bps=Decimal("5"))
    ).run(
        strategy=SMACrossoverStrategy(),
        bars=bars,
        timeframe="1Day",
        spec=SplitSpec(
            mode=WindowMode.FIXED,
            train_pct=0.5,
            validation_pct=0.25,
            oos_pct=0.25,
            warmup_bars=10,
        ),
        parameters={"fast_period": 5, "slow_period": 12, "quantity": "1"},
    )
    # Lower trade threshold for real short series
    report = review_walk_forward_evidence(
        result,
        criteria=QualificationCriteria(min_oos_trade_count=0, min_oos_windows=1),
    )
    assert report.evaluation_id == result.harness_id
    assert report.evidence_fingerprint


def test_broker_isolation_ast() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "qualification"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.brokers.alpaca")
                assert not node.module.startswith("app.brokers.router")
                assert node.module.split(".")[0] not in {"alpaca", "alpaca_trade_api"}


def test_no_public_approval_route() -> None:
    from app.main import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any("qualif" in p.lower() and "approv" in p.lower() for p in paths)
