"""Server-side owner authorization for paper qualification approvals.

Never accept a client-supplied user identifier as proof of authorization.
Fail closed when owner identity cannot be established.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.qualification.errors import UnauthorizedApprovalError


@dataclass(frozen=True, slots=True)
class AuthenticatedOwner:
    """Proven owner identity established by the server, not the client."""

    subject: str
    actor_type: str = "owner"

    def __post_init__(self) -> None:
        if self.actor_type != "owner":
            raise UnauthorizedApprovalError("actor_type must be owner")
        if not self.subject or not self.subject.strip():
            raise UnauthorizedApprovalError("owner subject required")


def parse_owner_allowlist(raw: str | None) -> frozenset[str]:
    if not raw or not raw.strip():
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def resolve_authenticated_owner(
    *,
    subject: str | None,
    credential_verified: bool,
    settings: Settings | None = None,
) -> AuthenticatedOwner:
    """Resolve an approving owner.

    Parameters
    ----------
    subject:
        Server-resolved subject (e.g. from session/JWT after verification).
        Must NOT be taken from an untrusted request body alone.
    credential_verified:
        Must be True only after server-side authentication succeeded.
    """
    cfg = settings or get_settings()
    allowlist = parse_owner_allowlist(cfg.paper_qualification_owner_subjects)
    if not allowlist:
        raise UnauthorizedApprovalError(
            "paper qualification owner allowlist is empty; fail closed"
        )
    if not credential_verified:
        raise UnauthorizedApprovalError("credentials not verified")
    if subject is None or not str(subject).strip():
        raise UnauthorizedApprovalError("missing authenticated owner subject")
    normalized = str(subject).strip()
    if normalized not in allowlist:
        raise UnauthorizedApprovalError("subject not in owner allowlist")
    return AuthenticatedOwner(subject=normalized)
