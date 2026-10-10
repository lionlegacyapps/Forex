"""Chronological TRAIN / VALIDATION / OOS window generation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.evaluation.hashing import canonical_json, configuration_hash, dataset_fingerprint, sha256_hex
from app.evaluation.models import SplitRole
from app.evaluation.walkforward.errors import InsufficientHistoryError, InvalidSplitError
from app.evaluation.walkforward.plan import ChronologicalSplit, WalkForwardPlan
from app.market_data.models import Bar


class WindowMode(StrEnum):
    ROLLING = "rolling"
    EXPANDING = "expanding"
    FIXED = "fixed"  # single date/pct split


class SplitSpec(BaseModel):
    """Configurable split definition (date, percentage, or bar-count)."""

    mode: WindowMode = WindowMode.FIXED
    # Date-based (inclusive start semantics; harness uses half-open score ends)
    train_start: datetime | None = None
    train_end: datetime | None = None
    validation_end: datetime | None = None
    oos_end: datetime | None = None
    # Percentage-based (of full bar series after warm-up reserved)
    train_pct: float | None = None
    validation_pct: float | None = None
    oos_pct: float | None = None
    # Bar-count based (rolling / expanding)
    train_bars: int | None = None
    validation_bars: int | None = None
    oos_bars: int | None = None
    step_bars: int = 1
    # Warm-up / minimums
    warmup_bars: int = 0
    min_train_bars: int = 5
    min_validation_bars: int = 1
    min_oos_bars: int = 1
    # Forward-label leakage controls (research features)
    label_horizon_bars: int = 0
    embargo_bars: int = 0

    @model_validator(mode="after")
    def _basic(self) -> SplitSpec:
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars must be >= 0")
        if self.step_bars < 1:
            raise ValueError("step_bars must be >= 1")
        if self.label_horizon_bars < 0 or self.embargo_bars < 0:
            raise ValueError("label_horizon_bars/embargo_bars must be >= 0")
        pcts = [self.train_pct, self.validation_pct, self.oos_pct]
        if any(p is not None for p in pcts):
            if any(p is None for p in pcts):
                raise ValueError("percentage splits require train/validation/oos pct")
            total = float(self.train_pct or 0) + float(self.validation_pct or 0) + float(
                self.oos_pct or 0
            )
            if abs(total - 1.0) > 1e-9:
                raise ValueError("percentage splits must sum to 1.0")
            if any(float(p) <= 0 for p in pcts):  # type: ignore[arg-type]
                raise ValueError("percentage splits must be > 0")
        return self


class EvaluationPeriod(BaseModel):
    role: SplitRole
    warmup_start: datetime
    score_start: datetime
    score_end: datetime  # exclusive
    bar_count_scored: int = 0
    warmup_bars: int = 0


class WalkForwardWindow(BaseModel):
    window_index: int
    mode: WindowMode
    train: EvaluationPeriod
    validation: EvaluationPeriod
    oos: EvaluationPeriod
    strategy_id: str
    strategy_version: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    configuration_hash: str
    dataset_fingerprint: str
    symbol: str
    timeframe: str
    label_horizon_bars: int = 0
    embargo_bars: int = 0

    def to_plan(self) -> WalkForwardPlan:
        plan = WalkForwardPlan(
            symbol=self.symbol,
            timeframe=self.timeframe,
            splits=[
                ChronologicalSplit(
                    role=self.train.role,
                    start=self.train.score_start,
                    end=self.train.score_end,
                ),
                ChronologicalSplit(
                    role=self.validation.role,
                    start=self.validation.score_start,
                    end=self.validation.score_end,
                ),
                ChronologicalSplit(
                    role=self.oos.role,
                    start=self.oos.score_start,
                    end=self.oos.score_end,
                ),
            ],
        )
        plan.validate_chronology()
        plan.assert_no_oos_mislabel()
        return plan


def _require_tz(ts: datetime, name: str) -> None:
    if ts.tzinfo is None:
        raise InvalidSplitError(f"{name} must be timezone-aware")


def _exclusive_end_timestamp(bars: list[Bar], score_end_idx: int) -> datetime:
    """Half-open end: timestamp of bars[score_end_idx], or sentinel after last."""
    if score_end_idx < len(bars):
        return bars[score_end_idx].timestamp
    # After last bar — use last timestamp + 1 microsecond for exclusive compare
    from datetime import timedelta

    return bars[-1].timestamp + timedelta(microseconds=1)


def build_period(
    role: SplitRole,
    bars: list[Bar],
    *,
    score_start_idx: int,
    score_end_idx: int,
    warmup_bars: int,
) -> EvaluationPeriod:
    if score_start_idx < 0 or score_end_idx > len(bars) or score_start_idx >= score_end_idx:
        raise InvalidSplitError(f"invalid {role} score indices")
    warmup_start_idx = max(0, score_start_idx - warmup_bars)
    return EvaluationPeriod(
        role=role,
        warmup_start=bars[warmup_start_idx].timestamp,
        score_start=bars[score_start_idx].timestamp,
        score_end=_exclusive_end_timestamp(bars, score_end_idx),
        bar_count_scored=score_end_idx - score_start_idx,
        warmup_bars=score_start_idx - warmup_start_idx,
    )


def _index_at_or_after(bars: list[Bar], ts: datetime) -> int:
    for i, b in enumerate(bars):
        if b.timestamp >= ts:
            return i
    raise InvalidSplitError(f"no bars at or after {ts.isoformat()}")


def generate_windows(
    bars: list[Bar],
    *,
    spec: SplitSpec,
    symbol: str,
    timeframe: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any] | None = None,
) -> list[WalkForwardWindow]:
    if not bars:
        raise InsufficientHistoryError("empty bar series")
    for i in range(1, len(bars)):
        if bars[i].timestamp <= bars[i - 1].timestamp:
            raise InvalidSplitError("bars must be strictly chronological")

    params = parameters or {}
    cfg_hash = configuration_hash(params)
    fingerprint = dataset_fingerprint(bars, symbol=symbol, timeframe=timeframe)
    n = len(bars)

    if spec.mode == WindowMode.FIXED and all(
        x is not None for x in (spec.train_start, spec.train_end, spec.validation_end, spec.oos_end)
    ):
        return [
            _window_from_dates(
                bars,
                spec=spec,
                symbol=symbol,
                timeframe=timeframe,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                parameters=params,
                configuration_hash=cfg_hash,
                dataset_fingerprint=fingerprint,
                window_index=0,
            )
        ]

    if spec.train_pct is not None:
        return [
            _window_from_percentages(
                bars,
                spec=spec,
                symbol=symbol,
                timeframe=timeframe,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                parameters=params,
                configuration_hash=cfg_hash,
                dataset_fingerprint=fingerprint,
                window_index=0,
            )
        ]

    if spec.train_bars is None or spec.validation_bars is None or spec.oos_bars is None:
        raise InvalidSplitError(
            "bar-count splits require train_bars, validation_bars, and oos_bars"
        )

    train_n = spec.train_bars
    val_n = spec.validation_bars
    oos_n = spec.oos_bars
    need = train_n + val_n + oos_n
    if n < need + (1 if spec.warmup_bars else 0):
        # warm-up may borrow from before train; still need enough scored bars
        if n < need:
            raise InsufficientHistoryError(
                f"need at least {need} bars for one window; have {n}"
            )

    windows: list[WalkForwardWindow] = []
    if spec.mode == WindowMode.ROLLING:
        start = 0
        idx = 0
        while start + need <= n:
            train_s, train_e = start, start + train_n
            val_s, val_e = train_e, train_e + val_n
            oos_s, oos_e = val_e, val_e + oos_n
            windows.append(
                _assemble_window(
                    bars,
                    window_index=idx,
                    mode=WindowMode.ROLLING,
                    train_s=train_s,
                    train_e=train_e,
                    val_s=val_s,
                    val_e=val_e,
                    oos_s=oos_s,
                    oos_e=oos_e,
                    warmup_bars=spec.warmup_bars,
                    label_horizon_bars=spec.label_horizon_bars,
                    embargo_bars=spec.embargo_bars,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    parameters=params,
                    configuration_hash=cfg_hash,
                    dataset_fingerprint=fingerprint,
                    min_train=spec.min_train_bars,
                    min_val=spec.min_validation_bars,
                    min_oos=spec.min_oos_bars,
                )
            )
            start += spec.step_bars
            idx += 1
            if spec.step_bars <= 0:
                break
    elif spec.mode == WindowMode.EXPANDING:
        # Expanding train: initial train_n, then grows by step each window
        idx = 0
        train_e = train_n
        while train_e + val_n + oos_n <= n:
            train_s = 0
            val_s, val_e = train_e, train_e + val_n
            oos_s, oos_e = val_e, val_e + oos_n
            windows.append(
                _assemble_window(
                    bars,
                    window_index=idx,
                    mode=WindowMode.EXPANDING,
                    train_s=train_s,
                    train_e=train_e,
                    val_s=val_s,
                    val_e=val_e,
                    oos_s=oos_s,
                    oos_e=oos_e,
                    warmup_bars=spec.warmup_bars,
                    label_horizon_bars=spec.label_horizon_bars,
                    embargo_bars=spec.embargo_bars,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    parameters=params,
                    configuration_hash=cfg_hash,
                    dataset_fingerprint=fingerprint,
                    min_train=spec.min_train_bars,
                    min_val=spec.min_validation_bars,
                    min_oos=spec.min_oos_bars,
                )
            )
            train_e += spec.step_bars
            idx += 1
    else:
        raise InvalidSplitError(f"unsupported mode for bar-count splits: {spec.mode}")

    if not windows:
        raise InsufficientHistoryError("no walk-forward windows could be generated")
    return windows


def _assemble_window(
    bars: list[Bar],
    *,
    window_index: int,
    mode: WindowMode,
    train_s: int,
    train_e: int,
    val_s: int,
    val_e: int,
    oos_s: int,
    oos_e: int,
    warmup_bars: int,
    label_horizon_bars: int,
    embargo_bars: int,
    symbol: str,
    timeframe: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    configuration_hash: str,
    dataset_fingerprint: str,
    min_train: int,
    min_val: int,
    min_oos: int,
) -> WalkForwardWindow:
    if (train_e - train_s) < min_train:
        raise InsufficientHistoryError("train period below minimum bars")
    if (val_e - val_s) < min_val:
        raise InsufficientHistoryError("validation period below minimum bars")
    if (oos_e - oos_s) < min_oos:
        raise InsufficientHistoryError("oos period below minimum bars")
    if not (train_e == val_s and val_e == oos_s):
        raise InvalidSplitError("scored periods must be contiguous and non-overlapping")

    train = build_period(
        SplitRole.TRAIN, bars, score_start_idx=train_s, score_end_idx=train_e, warmup_bars=warmup_bars
    )
    validation = build_period(
        SplitRole.VALIDATION,
        bars,
        score_start_idx=val_s,
        score_end_idx=val_e,
        warmup_bars=warmup_bars,
    )
    oos = build_period(
        SplitRole.OUT_OF_SAMPLE,
        bars,
        score_start_idx=oos_s,
        score_end_idx=oos_e,
        warmup_bars=warmup_bars,
    )
    window = WalkForwardWindow(
        window_index=window_index,
        mode=mode,
        train=train,
        validation=validation,
        oos=oos,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        parameters=parameters,
        configuration_hash=configuration_hash,
        dataset_fingerprint=dataset_fingerprint,
        symbol=symbol.strip().upper(),
        timeframe=timeframe,
        label_horizon_bars=label_horizon_bars,
        embargo_bars=embargo_bars,
    )
    window.to_plan()  # validates chronology
    return window


def _window_from_dates(
    bars: list[Bar],
    *,
    spec: SplitSpec,
    symbol: str,
    timeframe: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    configuration_hash: str,
    dataset_fingerprint: str,
    window_index: int,
) -> WalkForwardWindow:
    assert spec.train_start and spec.train_end and spec.validation_end and spec.oos_end
    for name, ts in [
        ("train_start", spec.train_start),
        ("train_end", spec.train_end),
        ("validation_end", spec.validation_end),
        ("oos_end", spec.oos_end),
    ]:
        _require_tz(ts, name)
    if not (spec.train_start < spec.train_end <= spec.validation_end <= spec.oos_end):
        raise InvalidSplitError("date splits must be strictly chronological and non-overlapping")

    train_s = _index_at_or_after(bars, spec.train_start)
    # Date ends are exclusive: first bar at/after boundary starts the next period.
    train_e = (
        _index_at_or_after(bars, spec.train_end)
        if any(b.timestamp >= spec.train_end for b in bars)
        else len(bars)
    )
    val_e = (
        _index_at_or_after(bars, spec.validation_end)
        if any(b.timestamp >= spec.validation_end for b in bars)
        else len(bars)
    )
    oos_e = (
        _index_at_or_after(bars, spec.oos_end)
        if any(b.timestamp >= spec.oos_end for b in bars)
        else len(bars)
    )
    if spec.oos_end > bars[-1].timestamp:
        oos_e = len(bars)
    val_s = train_e
    oos_s = val_e
    return _assemble_window(
        bars,
        window_index=window_index,
        mode=WindowMode.FIXED,
        train_s=train_s,
        train_e=train_e,
        val_s=val_s,
        val_e=val_e,
        oos_s=oos_s,
        oos_e=oos_e,
        warmup_bars=spec.warmup_bars,
        label_horizon_bars=spec.label_horizon_bars,
        embargo_bars=spec.embargo_bars,
        symbol=symbol,
        timeframe=timeframe,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        parameters=parameters,
        configuration_hash=configuration_hash,
        dataset_fingerprint=dataset_fingerprint,
        min_train=spec.min_train_bars,
        min_val=spec.min_validation_bars,
        min_oos=spec.min_oos_bars,
    )


def _window_from_percentages(
    bars: list[Bar],
    *,
    spec: SplitSpec,
    symbol: str,
    timeframe: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    configuration_hash: str,
    dataset_fingerprint: str,
    window_index: int,
) -> WalkForwardWindow:
    n = len(bars)
    train_n = int(n * float(spec.train_pct))
    val_n = int(n * float(spec.validation_pct))
    oos_n = n - train_n - val_n
    if train_n < spec.min_train_bars or val_n < spec.min_validation_bars or oos_n < spec.min_oos_bars:
        raise InsufficientHistoryError("percentage split produced insufficient bars")
    return _assemble_window(
        bars,
        window_index=window_index,
        mode=WindowMode.FIXED,
        train_s=0,
        train_e=train_n,
        val_s=train_n,
        val_e=train_n + val_n,
        oos_s=train_n + val_n,
        oos_e=n,
        warmup_bars=spec.warmup_bars,
        label_horizon_bars=spec.label_horizon_bars,
        embargo_bars=spec.embargo_bars,
        symbol=symbol,
        timeframe=timeframe,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        parameters=parameters,
        configuration_hash=configuration_hash,
        dataset_fingerprint=dataset_fingerprint,
        min_train=spec.min_train_bars,
        min_val=spec.min_validation_bars,
        min_oos=spec.min_oos_bars,
    )


def window_config_hash(window: WalkForwardWindow) -> str:
    body = {
        "window_index": window.window_index,
        "mode": window.mode.value,
        "train": window.train.model_dump(mode="json"),
        "validation": window.validation.model_dump(mode="json"),
        "oos": window.oos.model_dump(mode="json"),
        "configuration_hash": window.configuration_hash,
        "dataset_fingerprint": window.dataset_fingerprint,
    }
    return sha256_hex(canonical_json(body))
