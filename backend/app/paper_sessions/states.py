"""Paper session state machine."""

from __future__ import annotations

from app.models.enums import PaperSessionState
from app.paper_sessions.errors import IllegalSessionTransitionError

LEGAL_TRANSITIONS: dict[PaperSessionState, frozenset[PaperSessionState]] = {
    PaperSessionState.CREATED: frozenset(
        {PaperSessionState.READY, PaperSessionState.FAILED, PaperSessionState.STOPPED}
    ),
    PaperSessionState.READY: frozenset(
        {
            PaperSessionState.RUNNING,
            PaperSessionState.STOPPED,
            PaperSessionState.FAILED,
        }
    ),
    PaperSessionState.RUNNING: frozenset(
        {
            PaperSessionState.PAUSING,
            PaperSessionState.STOPPING,
            PaperSessionState.FAILED,
        }
    ),
    PaperSessionState.PAUSING: frozenset(
        {
            PaperSessionState.PAUSED,
            PaperSessionState.STOPPING,
            PaperSessionState.FAILED,
        }
    ),
    PaperSessionState.PAUSED: frozenset(
        {
            PaperSessionState.RUNNING,
            PaperSessionState.STOPPING,
            PaperSessionState.FAILED,
        }
    ),
    PaperSessionState.STOPPING: frozenset(
        {PaperSessionState.STOPPED, PaperSessionState.FAILED}
    ),
    PaperSessionState.STOPPED: frozenset(),
    PaperSessionState.FAILED: frozenset(),
}

ACTIVE_STATES = frozenset(
    {
        PaperSessionState.CREATED,
        PaperSessionState.READY,
        PaperSessionState.RUNNING,
        PaperSessionState.PAUSING,
        PaperSessionState.PAUSED,
        PaperSessionState.STOPPING,
    }
)

TERMINAL_STATES = frozenset({PaperSessionState.STOPPED, PaperSessionState.FAILED})


def assert_transition(current: PaperSessionState, target: PaperSessionState) -> None:
    allowed = LEGAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise IllegalSessionTransitionError(
            f"illegal session transition {current.value} → {target.value}"
        )
