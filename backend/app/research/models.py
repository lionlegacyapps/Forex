"""Normalized research outputs — serializable for UI / Market Memory later.

Research outputs do not automatically trigger trading.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchPrediction(BaseModel):
    symbol: str
    prediction_timestamp: datetime
    prediction_horizon: str
    score: Decimal
    factor_values: dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("prediction_timestamp")
    @classmethod
    def _tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("prediction_timestamp must be timezone-aware")
        return value


class ResearchOutput(BaseModel):
    research_model_id: str
    source_repository: str
    pinned_commit: str
    model_version: str
    symbol: str
    prediction_horizon: str
    data_version: str
    training_period_start: datetime | None = None
    training_period_end: datetime | None = None
    evaluation_period_start: datetime | None = None
    evaluation_period_end: datetime | None = None
    predictions: list[ResearchPrediction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_serializable_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def prediction_at(self, timestamp: datetime) -> ResearchPrediction | None:
        for pred in self.predictions:
            if pred.prediction_timestamp == timestamp:
                return pred
        return None
