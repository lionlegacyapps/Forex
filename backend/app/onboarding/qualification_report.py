"""Human-readable strategy qualification report (no approval)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.evaluation.models import SplitRole
from app.market_data.models import Bar
from app.models.strategy_paper_qualification import StrategyPaperQualification
from app.onboarding.errors import OnboardingBlockedError
from app.onboarding.qualification_evidence import (
    fetch_equity_bars,
    run_sma_crossover_walk_forward,
)


DEFAULT_QUALIFICATION_ID = uuid.UUID("b46aa6ab-dcb4-41d7-b3e0-d4d5667d0573")


@dataclass
class QualificationReportBundle:
    qualification_id: uuid.UUID
    markdown: str
    metrics: dict[str, Any]
    hashes_match: bool


def load_qualification(
    db: Session, qualification_id: uuid.UUID
) -> StrategyPaperQualification:
    row = db.get(StrategyPaperQualification, qualification_id)
    if row is None:
        raise OnboardingBlockedError(
            f"Qualification {qualification_id} not found in target database",
            code="qualification_missing",
        )
    return row


def _dec(value: Any) -> str:
    if value is None:
        return "unavailable"
    return str(value)


def build_metrics_from_walk_forward(
    row: StrategyPaperQualification,
    bars: list[Bar],
    wf_result: Any,
) -> dict[str, Any]:
    report = row.report if isinstance(row.report, dict) else {}
    oos_periods = [p for p in wf_result.period_reports if p.role == SplitRole.OUT_OF_SAMPLE]
    oos_agg = next(a for a in wf_result.aggregates if a.role == SplitRole.OUT_OF_SAMPLE)
    windows: list[dict[str, Any]] = []
    for p in oos_periods:
        windows.append(
            {
                "window_index": p.window_index,
                "trade_count": p.trade_count,
                "net_pnl": _dec(p.evaluation.metrics.net_pnl),
                "net_return_pct": _dec(p.net_return),
                "win_rate_pct": _dec(p.win_rate),
                "profit_factor": _dec(p.profit_factor),
                "max_drawdown": _dec(p.max_drawdown),
                "average_win": _dec(p.average_win),
                "average_loss": _dec(p.average_loss),
                "transaction_costs": _dec(p.transaction_costs),
            }
        )

    aw_num = Decimal("0")
    aw_den = 0
    al_num = Decimal("0")
    al_den = 0
    wins = 0
    losses = 0
    for p in oos_periods:
        wins += p.evaluation.metrics.winning_trades
        losses += p.evaluation.metrics.losing_trades
        if p.average_win is not None and p.evaluation.metrics.winning_trades:
            aw_num += p.average_win * p.evaluation.metrics.winning_trades
            aw_den += p.evaluation.metrics.winning_trades
        if p.average_loss is not None and p.evaluation.metrics.losing_trades:
            al_num += p.average_loss * p.evaluation.metrics.losing_trades
            al_den += p.evaluation.metrics.losing_trades

    hashes_match = {
        "parameter_hash": wf_result.configuration_hash == row.parameter_hash,
        "dataset_fingerprint": wf_result.dataset_fingerprint == row.dataset_fingerprint,
        "evaluation_id": wf_result.harness_id == row.evaluation_id,
    }
    warning_codes = sorted(
        {
            w.get("code")
            for w in (row.warnings or [])
            if isinstance(w, dict) and w.get("code")
        }
    )
    return {
        "qualification_id": str(row.id),
        "strategy_id": row.engine_strategy_id,
        "strategy_version": row.strategy_version,
        "parameters": dict(wf_result.parameters),
        "parameter_hash": row.parameter_hash,
        "dataset_fingerprint": row.dataset_fingerprint,
        "evidence_fingerprint": row.evidence_fingerprint,
        "evaluation_id": row.evaluation_id,
        "evaluation_date_utc": report.get("generated_at"),
        "qualification_created_at": row.created_at.isoformat() if row.created_at else None,
        "state": row.qualification_state.value,
        "recommendation": row.recommendation,
        "approval_scope": row.approval_scope.value,
        "hard_blockers": row.hard_blockers or [],
        "warning_codes": warning_codes,
        "warnings": row.warnings or [],
        "informational": report.get("informational") or [],
        "cost_assumptions": report.get("cost_assumptions") or {},
        "historical_period": {
            "symbol": bars[0].symbol if bars else None,
            "timeframe": "1Day",
            "start": bars[0].timestamp.date().isoformat() if bars else None,
            "end": bars[-1].timestamp.date().isoformat() if bars else None,
            "bar_count": len(bars),
        },
        "split": {
            "mode": "rolling",
            "train_bars": 80,
            "validation_bars": 40,
            "oos_bars": 40,
            "step_bars": 40,
            "warmup_bars": 20,
        },
        "oos": {
            "windows": oos_agg.window_count,
            "trades": oos_agg.total_trades,
            "net_pnl": _dec(oos_agg.total_net_pnl),
            "net_return_pct": _dec(report.get("oos_return_pct")),
            "compounded_return_pct": _dec(oos_agg.compounded_return_pct),
            "trade_weighted_win_rate_pct": _dec(oos_agg.trade_weighted_win_rate),
            "winning_trades": wins,
            "losing_trades": losses,
            "average_win": _dec(aw_num / aw_den) if aw_den else "unavailable",
            "average_loss": _dec(al_num / al_den) if al_den else "unavailable",
            "transaction_costs_total": _dec(oos_agg.total_costs),
            "max_drawdown_worst": _dec(oos_agg.max_drawdown_worst),
            "profit_factor_stored": _dec(report.get("profit_factor")),
            "profit_factor_note": (
                "Stored aggregate profit_factor is not reliable when some windows "
                "have zero losses (serialized as 0E+7). Prefer window-level values."
            ),
        },
        "oos_windows": windows,
        "regime_notes": sorted(set(report.get("market_regime_notes") or [])),
        "robustness_findings": sorted(set(report.get("robustness_findings") or [])),
        "hashes_match_recompute": hashes_match,
        "approved": row.qualification_state.value == "approved_for_paper",
    }


def render_markdown(metrics: dict[str, Any]) -> str:
    oos = metrics["oos"]
    period = metrics["historical_period"]
    split = metrics["split"]
    lines = [
        "# Strategy Qualification Report (NOT APPROVED)",
        "",
        "> Historical evaluation evidence only. This is **not** a prediction of future",
        "> performance and **does not** authorize paper or live trading.",
        "",
        "## Identity",
        "",
        f"- **Strategy:** `{metrics['strategy_id']}@{metrics['strategy_version']}`",
        f"- **Qualification ID:** `{metrics['qualification_id']}`",
        f"- **State:** `{metrics['state']}`",
        f"- **Recommendation:** `{metrics['recommendation']}`",
        f"- **Approval scope:** `{metrics['approval_scope']}`",
        f"- **Evaluation date (UTC):** {metrics['evaluation_date_utc'] or 'unavailable'}",
        f"- **Record created (UTC):** {metrics['qualification_created_at'] or 'unavailable'}",
        "",
        "## Parameters",
        "",
        f"- **Configuration:** `{json.dumps(metrics['parameters'], sort_keys=True)}`",
        f"- **Parameter hash:** `{metrics['parameter_hash']}`",
        f"- **Dataset fingerprint:** `{metrics['dataset_fingerprint']}`",
        f"- **Evidence fingerprint:** `{metrics['evidence_fingerprint']}`",
        f"- **Evaluation / harness ID:** `{metrics['evaluation_id']}`",
        "",
        "## Historical testing period",
        "",
        f"- **Symbol / timeframe:** {period.get('symbol')} / {period.get('timeframe')}",
        f"- **Bars:** {period.get('bar_count')} completed daily bars",
        f"- **Range:** {period.get('start')} → {period.get('end')}",
        "",
        "## Train / validation / OOS split",
        "",
        f"- **Mode:** {split['mode']}",
        f"- **Train bars:** {split['train_bars']}",
        f"- **Validation bars:** {split['validation_bars']}",
        f"- **OOS bars:** {split['oos_bars']}",
        f"- **Step bars:** {split['step_bars']}",
        f"- **Warmup bars:** {split['warmup_bars']}",
        "",
        "## Out-of-sample summary",
        "",
        f"- **OOS windows:** {oos['windows']}",
        f"- **OOS trades:** {oos['trades']} (wins {oos['winning_trades']} / losses {oos['losing_trades']})",
        f"- **Net PnL (sum of OOS windows):** {oos['net_pnl']}",
        f"- **Net return (stored OOS aggregate %):** {oos['net_return_pct']}",
        f"- **Compounded return % (recomputed):** {oos['compounded_return_pct']}",
        f"- **Trade-weighted win rate %:** {oos['trade_weighted_win_rate_pct']}",
        f"- **Average win (trade-weighted):** {oos['average_win']}",
        f"- **Average loss (trade-weighted):** {oos['average_loss']}",
        f"- **Maximum drawdown (worst OOS window):** {oos['max_drawdown_worst']}",
        f"- **Transaction costs total (OOS):** {oos['transaction_costs_total']}",
        f"- **Profit factor (stored aggregate):** {oos['profit_factor_stored']}",
        f"- **Profit factor note:** {oos['profit_factor_note']}",
        "",
        "## Transaction cost assumptions",
        "",
        f"- `{json.dumps(metrics.get('cost_assumptions') or {}, sort_keys=True)}`",
        "",
        "## Regime performance notes",
        "",
    ]
    regimes = metrics.get("regime_notes") or []
    if regimes:
        for note in regimes:
            lines.append(f"- {note}")
    else:
        lines.append("- unavailable in stored report")
    lines.extend(["", "## Robustness findings", ""])
    findings = metrics.get("robustness_findings") or []
    if findings:
        for f in findings:
            lines.append(f"- {f}")
    else:
        lines.append("- none recorded")

    lines.extend(["", "## Window-by-window OOS consistency", ""])
    windows = metrics.get("oos_windows") or []
    if not windows:
        lines.append(
            "_Window rows omitted because a live recompute no longer matches the "
            "stored dataset fingerprint. Aggregate OOS metrics above remain those "
            "persisted on the qualification record._"
        )
    else:
        lines.append(
            "| Window | Trades | Net PnL | Win rate % | Profit factor | Max DD | "
            "Avg win | Avg loss | Costs |"
        )
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for w in windows:
            lines.append(
                f"| {w['window_index']} | {w['trade_count']} | {w['net_pnl']} | "
                f"{w['win_rate_pct']} | {w['profit_factor']} | {w['max_drawdown']} | "
                f"{w['average_win']} | {w['average_loss']} | {w['transaction_costs']} |"
            )

    lines.extend(["", "## Hard blockers", ""])
    blockers = metrics.get("hard_blockers") or []
    if not blockers:
        lines.append("- none")
    else:
        for b in blockers:
            if isinstance(b, dict):
                lines.append(f"- `{b.get('code')}`: {b.get('message')}")
            else:
                lines.append(f"- {b}")

    lines.extend(["", "## Warnings", ""])
    codes = metrics.get("warning_codes") or []
    if codes:
        lines.append(f"- Codes: {', '.join(codes)}")
    else:
        lines.append("- none")
    # Deduplicate warning messages
    messages = sorted(
        {
            w.get("message")
            for w in (metrics.get("warnings") or [])
            if isinstance(w, dict) and w.get("message")
        }
    )
    for msg in messages:
        lines.append(f"- {msg}")

    lines.extend(
        [
            "",
            "## Qualification recommendation",
            "",
            f"- **{metrics['recommendation']}**",
            "- Auto-approval was **not** performed.",
            "- Owner must explicitly approve after reviewing this report.",
            "",
            "## Recompute integrity",
            "",
            f"- Parameter hash match: {metrics['hashes_match_recompute']['parameter_hash']}",
            f"- Dataset fingerprint match: {metrics['hashes_match_recompute']['dataset_fingerprint']}",
            f"- Evaluation id match: {metrics['hashes_match_recompute']['evaluation_id']}",
            f"- Note: {metrics.get('recompute_note') or 'n/a'}",
            "",
            "## Disclaimer",
            "",
            "These metrics describe historical simulated performance on past market data",
            "with stated transaction costs. They are **not** a guarantee of future results,",
            "profitability, or suitability for unsupervised trading.",
            "",
        ]
    )
    return "\n".join(lines)


async def generate_qualification_report(
    db: Session,
    *,
    qualification_id: uuid.UUID = DEFAULT_QUALIFICATION_ID,
    settings: Settings | None = None,
    bars: list[Bar] | None = None,
) -> QualificationReportBundle:
    """Build a human report from the stored qualification + optional recompute.

    Stored report fields are authoritative. Window-level rows come from a live
    recompute when dataset/evaluation hashes match; otherwise window rows are
    omitted rather than inventing metrics from a drifted dataset.
    """
    cfg = settings or get_settings()
    row = load_qualification(db, qualification_id)
    report = row.report if isinstance(row.report, dict) else {}
    if bars is None:
        bars = await fetch_equity_bars(settings=cfg)
    wf = run_sma_crossover_walk_forward(bars)
    metrics = build_metrics_from_walk_forward(row, bars, wf)
    hashes_ok = all(metrics["hashes_match_recompute"].values())
    if not hashes_ok:
        # Keep stored aggregates; drop drifted window rows (do not invent).
        metrics["oos_windows"] = []
        metrics["recompute_note"] = (
            "Live market-data recompute no longer matches the stored dataset "
            "fingerprint (common if bar volumes revise). Headline OOS metrics "
            "below come from the stored qualification report; window table omitted."
        )
        # Prefer stored headline figures explicitly
        metrics["oos"]["net_pnl"] = str(report.get("oos_net_pnl") or metrics["oos"]["net_pnl"])
        metrics["oos"]["net_return_pct"] = str(
            report.get("oos_return_pct") or metrics["oos"]["net_return_pct"]
        )
        metrics["oos"]["windows"] = int(
            report.get("oos_window_count") or metrics["oos"]["windows"]
        )
        metrics["oos"]["trades"] = int(
            report.get("oos_trade_count") or metrics["oos"]["trades"]
        )
        metrics["oos"]["max_drawdown_worst"] = str(
            report.get("max_drawdown") or metrics["oos"]["max_drawdown_worst"]
        )
    else:
        metrics["recompute_note"] = (
            "Live recompute matched stored parameter hash, dataset fingerprint, "
            "and evaluation id — window table is reproducible evidence."
        )
    md = render_markdown(metrics)
    return QualificationReportBundle(
        qualification_id=row.id,
        markdown=md,
        metrics=metrics,
        hashes_match=hashes_ok,
    )


def write_report_files(
    bundle: QualificationReportBundle,
    *,
    markdown_path: Path,
    json_path: Path | None = None,
) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(bundle.markdown, encoding="utf-8")
    if json_path is not None:
        json_path.write_text(
            json.dumps(bundle.metrics, indent=2, default=str), encoding="utf-8"
        )
