"""Hard blockers, warnings, and informational findings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FindingSeverity(StrEnum):
    HARD_BLOCKER = "hard_blocker"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class QualificationFinding(BaseModel):
    code: str
    severity: FindingSeverity
    message: str
    details: dict = Field(default_factory=dict)
