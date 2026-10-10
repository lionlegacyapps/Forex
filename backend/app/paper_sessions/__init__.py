"""Controlled Paper Session Runner V1 — DRY_RUN by default; no auto-start."""

from app.paper_sessions.errors import (
    ActivationRejectedError,
    ConcurrentSessionError,
    PaperExecuteDisabledError,
    PaperSessionError,
)
from app.paper_sessions.market_data import InMemorySessionBarSource
from app.paper_sessions.risk_limits import SessionRiskLimits
from app.paper_sessions.runner import IterationResult, PaperSessionRunner
from app.paper_sessions.service import PaperSessionService

__all__ = [
    "ActivationRejectedError",
    "ConcurrentSessionError",
    "InMemorySessionBarSource",
    "IterationResult",
    "PaperExecuteDisabledError",
    "PaperSessionError",
    "PaperSessionRunner",
    "PaperSessionService",
    "SessionRiskLimits",
]
