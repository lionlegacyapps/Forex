"""Qlib-inspired research pipeline (isolated, deterministic demo).

Architecture:
  Historical Market Data
  → Feature Preparation
  → Quantitative Research Model (fit on train only)
  → Prediction / Factor Score (eval period only)
  → Normalized ResearchOutput
  → Strategy Adapter (separate step; not auto-trading)

Does NOT import or execute microsoft/qlib.
Does NOT call BrokerRouter / Alpaca.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.market_data.models import Bar
from app.research.data import ResearchBarFrame, bars_to_research_frame
from app.research.factors import compute_momentum_factor, compute_return_factor
from app.research.models import ResearchOutput, ResearchPrediction
from app.research.notices import MICROSOFT_QLIB_MIT_NOTICE
from app.research.qlib_intake import QLIB_PINNED_COMMIT, QLIB_REPOSITORY_URL


class TrainEvalSplit(BaseModel):
    """Strict temporal split — train ends before eval begins."""

    train_end_exclusive: datetime
    # eval uses timestamps >= train_end_exclusive

    def assert_valid(self, frame: ResearchBarFrame) -> None:
        if self.train_end_exclusive.tzinfo is None:
            raise ValueError("train_end_exclusive must be timezone-aware")
        train_rows = [r for r in frame.rows if r.timestamp < self.train_end_exclusive]
        eval_rows = [r for r in frame.rows if r.timestamp >= self.train_end_exclusive]
        if len(train_rows) < 3:
            raise ValueError("insufficient training rows")
        if not eval_rows:
            raise ValueError("empty evaluation period")
        if train_rows[-1].timestamp >= eval_rows[0].timestamp:
            raise ValueError("train/eval contamination: overlapping periods")


class FittedResearchModel(BaseModel):
    """Tiny deterministic model: score = momentum - bias, bias from train mean."""

    model_id: str = "qlib_inspired_momentum_v1"
    model_version: str = "1.0.0"
    lookback: int = 5
    train_bias: Decimal = Decimal("0")
    train_start: datetime | None = None
    train_end: datetime | None = None


class QlibInspiredResearchPipeline:
    """Fit/predict research workflow with point-in-time features."""

    MODEL_ID = "qlib_inspired_momentum_v1"
    MODEL_VERSION = "1.0.0"
    HORIZON = "1bar"

    def __init__(self, *, lookback: int = 5) -> None:
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        self.lookback = lookback

    def prepare_frame(self, bars: list[Bar], *, data_version: str = "v1-fixture") -> ResearchBarFrame:
        return bars_to_research_frame(bars, data_version=data_version)

    def fit(self, frame: ResearchBarFrame, split: TrainEvalSplit) -> FittedResearchModel:
        split.assert_valid(frame)
        momentum = compute_momentum_factor(frame, lookback=self.lookback)
        train_scores: list[Decimal] = []
        train_start: datetime | None = None
        train_end: datetime | None = None
        for row, score in zip(frame.rows, momentum, strict=True):
            if row.timestamp >= split.train_end_exclusive:
                break
            if score is None:
                continue
            train_scores.append(score)
            if train_start is None:
                train_start = row.timestamp
            train_end = row.timestamp
        if not train_scores:
            raise ValueError("no usable training factor values")
        bias = sum(train_scores, Decimal("0")) / Decimal(len(train_scores))
        return FittedResearchModel(
            model_id=self.MODEL_ID,
            model_version=self.MODEL_VERSION,
            lookback=self.lookback,
            train_bias=bias,
            train_start=train_start,
            train_end=train_end,
        )

    def predict(
        self,
        frame: ResearchBarFrame,
        model: FittedResearchModel,
        split: TrainEvalSplit,
    ) -> ResearchOutput:
        split.assert_valid(frame)
        momentum = compute_momentum_factor(frame, lookback=model.lookback)
        returns = compute_return_factor(frame, period=1)
        predictions: list[ResearchPrediction] = []
        warnings = [
            "This is a Qlib-inspired demonstration model, not the full Microsoft Qlib framework.",
            "Research outputs do not automatically trigger trading.",
            "BACKTEST PERFORMANCE DOES NOT GUARANTEE FUTURE PERFORMANCE.",
            MICROSOFT_QLIB_MIT_NOTICE.split("\n")[0],
        ]

        eval_start: datetime | None = None
        eval_end: datetime | None = None
        for idx, row in enumerate(frame.rows):
            if row.timestamp < split.train_end_exclusive:
                continue
            # Point-in-time: factor at idx uses only history < current close mean window
            mom = momentum[idx]
            if mom is None:
                continue
            # Labels / future returns must NOT enter the score
            _ = returns  # computed for integrity tests only; not used in score
            score = mom - model.train_bias
            predictions.append(
                ResearchPrediction(
                    symbol=frame.symbol,
                    prediction_timestamp=row.timestamp,
                    prediction_horizon=self.HORIZON,
                    score=score,
                    factor_values={
                        "momentum": mom,
                        "train_bias": model.train_bias,
                    },
                )
            )
            if eval_start is None:
                eval_start = row.timestamp
            eval_end = row.timestamp

        return ResearchOutput(
            research_model_id=model.model_id,
            source_repository=QLIB_REPOSITORY_URL,
            pinned_commit=QLIB_PINNED_COMMIT,
            model_version=model.model_version,
            symbol=frame.symbol,
            prediction_horizon=self.HORIZON,
            data_version=frame.data_version,
            training_period_start=model.train_start,
            training_period_end=model.train_end,
            evaluation_period_start=eval_start,
            evaluation_period_end=eval_end,
            predictions=predictions,
            warnings=warnings,
            metadata={
                "lookback": model.lookback,
                "price_convention": frame.price_convention,
                "full_qlib_runtime": False,
                "auto_trade": False,
            },
        )

    def run(
        self,
        bars: list[Bar],
        split: TrainEvalSplit,
        *,
        data_version: str = "v1-fixture",
    ) -> ResearchOutput:
        frame = self.prepare_frame(bars, data_version=data_version)
        model = self.fit(frame, split)
        return self.predict(frame, model, split)
