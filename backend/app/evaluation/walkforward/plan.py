"""Walk-forward plan metadata (no parameter search / optimization)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.evaluation.models import SplitRole


class ChronologicalSplit(BaseModel):
    """TRAIN / VALIDATION / OUT_OF_SAMPLE bounds.

    Bounds are half-open ``[start, end)`` in harness scoring semantics.
    Labeling FULL_SAMPLE as OOS is forbidden.
    """

    role: SplitRole
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _validate(self) -> ChronologicalSplit:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("split bounds must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("split start must be before end")
        if self.role == SplitRole.FULL_SAMPLE:
            pass
        return self


class WalkForwardPlan(BaseModel):
    """Design-only plan — does not search parameters or optimize."""

    symbol: str
    timeframe: str
    splits: list[ChronologicalSplit] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=lambda: [
            "Walk-forward optimization is not implemented in V1.",
            "FULL_SAMPLE and TRAIN results must not be reported as OUT_OF_SAMPLE.",
            "Parameter search / automated strategy promotion is out of scope.",
        ]
    )

    def assert_no_oos_mislabel(self) -> None:
        roles = [s.role for s in self.splits]
        if SplitRole.OUT_OF_SAMPLE in roles and SplitRole.TRAIN not in roles:
            raise ValueError("OOS split without prior TRAIN is invalid for walk-forward")

    def validate_chronology(self) -> None:
        ordered = sorted(self.splits, key=lambda s: s.start)
        for a, b in zip(ordered, ordered[1:], strict=False):
            if a.end > b.start:
                raise ValueError("walk-forward splits must not overlap chronologically")
