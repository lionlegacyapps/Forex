"""Data-leakage guards for walk-forward evaluation."""

from __future__ import annotations

from datetime import datetime

from app.evaluation.models import SplitRole
from app.evaluation.walkforward.errors import DataLeakageError
from app.evaluation.walkforward.windows import EvaluationPeriod, WalkForwardWindow
from app.market_data.models import Bar


def assert_no_future_bars(visible: list[Bar], *, as_of: datetime) -> None:
    if any(b.timestamp > as_of for b in visible):
        raise DataLeakageError("future market bars present in strategy context")


def assert_period_isolation(window: WalkForwardWindow) -> None:
    """Scored periods must be strictly chronological and non-overlapping."""
    periods = [window.train, window.validation, window.oos]
    for p in periods:
        if p.score_start >= p.score_end:
            raise DataLeakageError(f"{p.role} scored period is empty or inverted")
        if p.warmup_start > p.score_start:
            raise DataLeakageError(f"{p.role} warm-up starts after score start")
    if not (
        window.train.score_end <= window.validation.score_start
        and window.validation.score_end <= window.oos.score_start
    ):
        raise DataLeakageError("train/validation/oos scored periods overlap or misordered")


def assert_no_oos_in_earlier_context(
    bars: list[Bar],
    *,
    period: EvaluationPeriod,
    oos_start: datetime,
) -> None:
    """Bars used for train/validation must not include OOS observations."""
    if period.role == SplitRole.OUT_OF_SAMPLE:
        return
    for b in bars:
        if b.timestamp >= oos_start and b.timestamp < period.score_end:
            # train/val score windows must end at or before oos_start
            raise DataLeakageError("OOS observations leaked into earlier period bars")
    if period.score_end > oos_start:
        raise DataLeakageError("earlier period score_end extends into OOS")


def purge_embargo_ok(
    *,
    label_horizon_bars: int,
    embargo_bars: int,
    gap_bars_between_fit_and_eval: int,
) -> bool:
    """Return True when gap is sufficient for the declared label horizon."""
    need = max(0, label_horizon_bars) + max(0, embargo_bars)
    return gap_bars_between_fit_and_eval >= need


def require_purge_or_reject(
    *,
    label_horizon_bars: int,
    embargo_bars: int,
    gap_bars_between_fit_and_eval: int,
) -> None:
    if label_horizon_bars <= 0:
        return
    if not purge_embargo_ok(
        label_horizon_bars=label_horizon_bars,
        embargo_bars=embargo_bars,
        gap_bars_between_fit_and_eval=gap_bars_between_fit_and_eval,
    ):
        raise DataLeakageError(
            "forward-looking label horizon cannot be purged/embargoed; "
            "rejecting evaluation"
        )
