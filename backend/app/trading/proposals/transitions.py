"""Explicit TradeProposal status transition rules."""

from __future__ import annotations

from app.core.exceptions import TradingPipelineError
from app.models.enums import TradeProposalStatus
from app.trading.risk.codes import INVALID_STATE_TRANSITION

# Allowed directed edges for proposal lifecycle.
ALLOWED_PROPOSAL_TRANSITIONS: dict[TradeProposalStatus, frozenset[TradeProposalStatus]] = {
    TradeProposalStatus.PENDING: frozenset(
        {
            TradeProposalStatus.RISK_APPROVED,
            TradeProposalStatus.RISK_REJECTED,
            TradeProposalStatus.CANCELLED,
            TradeProposalStatus.EXPIRED,
        }
    ),
    TradeProposalStatus.RISK_APPROVED: frozenset(
        {
            TradeProposalStatus.VALIDATED,
            TradeProposalStatus.VALIDATION_REJECTED,
            TradeProposalStatus.CANCELLED,
            TradeProposalStatus.EXPIRED,
        }
    ),
    TradeProposalStatus.VALIDATED: frozenset(
        {
            TradeProposalStatus.ROUTED,
            TradeProposalStatus.CANCELLED,
            TradeProposalStatus.EXPIRED,
        }
    ),
    TradeProposalStatus.ROUTED: frozenset(
        {
            TradeProposalStatus.SUBMITTED,
            TradeProposalStatus.CANCELLED,
            TradeProposalStatus.EXPIRED,
        }
    ),
    # Terminal / failure states: no further progression into submission path.
    TradeProposalStatus.RISK_REJECTED: frozenset({TradeProposalStatus.CANCELLED}),
    TradeProposalStatus.VALIDATION_REJECTED: frozenset({TradeProposalStatus.CANCELLED}),
    TradeProposalStatus.SUBMITTED: frozenset({TradeProposalStatus.CANCELLED}),
    TradeProposalStatus.CANCELLED: frozenset(),
    TradeProposalStatus.EXPIRED: frozenset(),
}


def assert_proposal_transition(
    current: TradeProposalStatus,
    target: TradeProposalStatus,
) -> None:
    """Raise if ``current → target`` is not an allowed transition."""
    allowed = ALLOWED_PROPOSAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise TradingPipelineError(
            f"Illegal proposal status transition: {current.value} → {target.value}",
            code=INVALID_STATE_TRANSITION,
        )


def can_transition(current: TradeProposalStatus, target: TradeProposalStatus) -> bool:
    return target in ALLOWED_PROPOSAL_TRANSITIONS.get(current, frozenset())
