"""Controlled Paper Session Runner — DRY_RUN default; PAPER_EXECUTE opt-in."""

from app.paper_sessions.authorization import PaperExecutionAuthorizationService
from app.paper_sessions.errors import (
    ActivationRejectedError,
    ConcurrentSessionError,
    ConsentError,
    PaperExecuteDisabledError,
    PaperSessionError,
    UncertainOrderAcknowledgmentError,
)
from app.paper_sessions.market_data import InMemorySessionBarSource
from app.paper_sessions.risk_limits import SessionRiskLimits
from app.paper_sessions.runner import IterationResult, PaperSessionRunner
from app.paper_sessions.service import PaperSessionService

__all__ = [
    "ActivationRejectedError",
    "ConcurrentSessionError",
    "ConsentError",
    "InMemorySessionBarSource",
    "IterationResult",
    "PaperExecuteDisabledError",
    "PaperExecutionAuthorizationService",
    "PaperSessionError",
    "PaperSessionRunner",
    "PaperSessionService",
    "SessionRiskLimits",
    "UncertainOrderAcknowledgmentError",
]
