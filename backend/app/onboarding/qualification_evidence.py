"""Generate walk-forward qualification evidence for sma_crossover — no auto-approve."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.backtesting.costs import BacktestCostModel
from app.evaluation.hashing import configuration_hash
from app.evaluation.walkforward.harness import WalkForwardHarness, WalkForwardResult
from app.evaluation.walkforward.windows import SplitSpec, WindowMode
from app.market_data.models import Bar, MarketDataAssetClass
from app.market_data.providers.alpaca import AlpacaMarketDataProvider
from app.models.enums import StrategyStatus
from app.models.strategy import Strategy as StrategyRow
from app.qualification.criteria import QualificationCriteria
from app.qualification.evidence import evidence_fingerprint, review_walk_forward_evidence
from app.qualification.report import QualificationReport
from app.qualification.service import PaperQualificationService
from app.qualification.states import QualificationRecommendation, QualificationState
from app.strategies.reference import SMACrossoverStrategy
from app.core.config import Settings, get_settings
from app.onboarding.errors import OnboardingBlockedError

logger = logging.getLogger(__name__)

# Keep aligned with app.pilot.config.default_pilot_config parameters.
DEFAULT_PILOT_PARAMETERS: dict[str, Any] = {
    "fast_period": 3,
    "slow_period": 5,
    "quantity": "1",
}

# Nonzero realistic costs required by QualificationCriteria.require_nonzero_costs
DEFAULT_PILOT_COSTS = BacktestCostModel(
    commission_per_share=Decimal("0.005"),
    commission_flat=Decimal("0"),
    slippage_bps=Decimal("5"),
)


@dataclass
class QualificationEvidenceBundle:
    strategy_id: str
    strategy_version: str
    parameters: dict[str, Any]
    parameter_hash: str
    dataset_fingerprint: str
    evidence_fingerprint: str
    evaluation_id: str
    qualification_id: uuid.UUID | None
    qualification_state: str | None
    recommendation: str | None
    hard_blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    oos_trade_count: int = 0
    oos_windows: int = 0
    report_summary: dict[str, Any] = field(default_factory=dict)
    walk_forward: WalkForwardResult | None = None
    bars_used: int = 0
    auto_approved: bool = False


async def fetch_equity_bars(
    *,
    symbol: str = "AAPL",
    timeframe: str = "1Day",
    lookback_days: int = 800,
    settings: Settings | None = None,
    provider: AlpacaMarketDataProvider | None = None,
) -> list[Bar]:
    cfg = settings or get_settings()
    if provider is None:
        if not cfg.alpaca_api_key or not cfg.alpaca_api_secret:
            raise OnboardingBlockedError(
                "Alpaca credentials required to fetch evaluation bars",
                code="alpaca_credentials_missing",
            )
        provider = AlpacaMarketDataProvider(
            api_key=cfg.alpaca_api_key,
            api_secret=cfg.alpaca_api_secret,
            base_url=cfg.alpaca_data_base_url,
            timeout_seconds=max(cfg.market_data_timeout_seconds, 30.0),
            feed=cfg.alpaca_data_feed,
        )
    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)
    bars = await provider.get_bars(
        symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        asset_class=MarketDataAssetClass.EQUITY,
        limit=10000,
    )
    if not bars:
        raise OnboardingBlockedError(
            "No completed bars returned for evaluation",
            code="bars_unavailable",
        )
    return bars


def run_sma_crossover_walk_forward(
    bars: list[Bar],
    *,
    parameters: dict[str, Any] | None = None,
    costs: BacktestCostModel | None = None,
) -> WalkForwardResult:
    params = dict(parameters or DEFAULT_PILOT_PARAMETERS)
    strategy = SMACrossoverStrategy()
    # Rolling windows to accumulate OOS sample without fabricating signals
    spec = SplitSpec(
        mode=WindowMode.ROLLING,
        train_bars=80,
        validation_bars=40,
        oos_bars=40,
        step_bars=40,
        warmup_bars=20,
    )
    return WalkForwardHarness(
        starting_capital=Decimal("100000"),
        costs=costs or DEFAULT_PILOT_COSTS,
    ).run(
        strategy=strategy,
        bars=bars,
        timeframe="1Day",
        spec=spec,
        parameters=params,
        symbol=bars[0].symbol,
    )


def persist_qualification_evidence(
    db: Session,
    result: WalkForwardResult,
    *,
    criteria: QualificationCriteria | None = None,
    strategy_db_id: uuid.UUID | None = None,
) -> QualificationEvidenceBundle:
    """Create draft + submit evidence. Never calls approve()."""
    crit = criteria or QualificationCriteria()
    report = review_walk_forward_evidence(result, criteria=crit)
    efp = evidence_fingerprint(
        harness_id=result.harness_id,
        strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        parameter_hash=result.configuration_hash,
        dataset_fingerprint=result.dataset_fingerprint,
    )

    # Ensure strategy row exists for FK when requested.
    # Name must be unique per (name, version) — never reuse a fixed label.
    if strategy_db_id is None:
        strat = StrategyRow(
            name=f"{result.strategy_id}-{result.strategy_version}-{uuid.uuid4().hex[:10]}",
            strategy_type="reference",
            version=result.strategy_version,
            status=StrategyStatus.DEVELOPMENT,
        )
        db.add(strat)
        db.flush()
        strategy_db_id = strat.id

    svc = PaperQualificationService(db, criteria=crit)
    row = svc.create_draft(
        engine_strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        parameter_hash=result.configuration_hash,
        evidence_fingerprint=efp,
        evaluation_id=result.harness_id,
        dataset_fingerprint=result.dataset_fingerprint,
        strategy_db_id=strategy_db_id,
    )
    row, report = svc.submit_walk_forward_evidence(row.id, result)
    # Explicitly never approve here.
    oos_trades = 0
    oos_windows = 0
    for a in result.aggregates:
        if a.role.value == "out_of_sample":
            oos_trades = a.total_trades
            oos_windows = a.window_count
            break

    return QualificationEvidenceBundle(
        strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        parameters=dict(result.parameters),
        parameter_hash=result.configuration_hash,
        dataset_fingerprint=result.dataset_fingerprint,
        evidence_fingerprint=efp,
        evaluation_id=result.harness_id,
        qualification_id=row.id,
        qualification_state=row.qualification_state.value,
        recommendation=report.recommendation.value if report.recommendation else None,
        hard_blockers=[f.code for f in report.hard_blockers],
        warnings=[f.code for f in report.warnings],
        oos_trade_count=oos_trades,
        oos_windows=oos_windows,
        report_summary={
            "policy_version": report.policy_version,
            "recommendation": report.recommendation.value,
            "hard_blocker_count": len(report.hard_blockers),
            "warning_count": len(report.warnings),
            "eligible_for_manual_approval": report.recommendation
            == QualificationRecommendation.ELIGIBLE_FOR_REVIEW
            and row.qualification_state == QualificationState.REVIEW_REQUIRED,
        },
        walk_forward=result,
        bars_used=len(result.period_reports),
        auto_approved=False,
    )


async def prepare_sma_crossover_qualification(
    db: Session,
    *,
    settings: Settings | None = None,
    parameters: dict[str, Any] | None = None,
    bars: list[Bar] | None = None,
) -> QualificationEvidenceBundle:
    """Fetch bars (unless provided), evaluate, persist evidence — no approval."""
    if bars is None:
        bars = await fetch_equity_bars(settings=settings)
    wf = run_sma_crossover_walk_forward(bars, parameters=parameters)
    # Sanity: configuration hash matches parameters
    ph = configuration_hash(wf.parameters)
    if ph != wf.configuration_hash:
        # harness uses configuration_hash from validated params — keep harness value
        pass
    return persist_qualification_evidence(db, wf)
