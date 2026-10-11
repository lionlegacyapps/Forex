"""Owner allowlist setup helpers — never invent subjects or disable checks."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.qualification.auth import (
    AuthenticatedOwner,
    parse_owner_allowlist,
    resolve_authenticated_owner,
)
from app.onboarding.errors import OnboardingBlockedError


@dataclass(frozen=True, slots=True)
class OwnerAllowlistStatus:
    configured: bool
    subject_count: int
    # Never expose the full allowlist in logs by default; optional for operator tooling.
    subjects: frozenset[str]


def owner_allowlist_status(settings: Settings | None = None) -> OwnerAllowlistStatus:
    cfg = settings or get_settings()
    subjects = parse_owner_allowlist(cfg.paper_qualification_owner_subjects)
    return OwnerAllowlistStatus(
        configured=bool(subjects),
        subject_count=len(subjects),
        subjects=subjects,
    )


def require_authenticated_owner(
    *,
    subject: str | None,
    credential_verified: bool,
    settings: Settings | None = None,
) -> AuthenticatedOwner:
    """Resolve owner via existing auth — never invent a subject."""
    cfg = settings or get_settings()
    status = owner_allowlist_status(cfg)
    if not status.configured:
        raise OnboardingBlockedError(
            "PAPER_QUALIFICATION_OWNER_SUBJECTS is empty. "
            "Set it in private server-side environment to the exact "
            "server-resolved authenticated subject (e.g. verified email), "
            "then restart the process. Never invent a subject; never disable checks.",
            code="owner_allowlist_empty",
        )
    return resolve_authenticated_owner(
        subject=subject,
        credential_verified=credential_verified,
        settings=cfg,
    )


OWNER_ALLOWLIST_SETUP_PROCEDURE = """
Paper pilot owner allowlist (private server-side only)
-----------------------------------------------------
1. Determine the subject your auth layer will pass to
   resolve_authenticated_owner(subject=..., credential_verified=True)
   AFTER successful server-side credential verification.
   Typical subject: verified email of the repository/platform owner.
2. Set in the private repository-root .env (never commit real values):
     PAPER_QUALIFICATION_OWNER_SUBJECTS=<exact-subject>
   Multiple subjects: comma-separated, no spaces required.
3. Restart the API/worker process so Settings reload.
4. Verify with require_authenticated_owner(subject=<exact-subject>,
   credential_verified=True) — must succeed.
5. Verify unauthorized subject and credential_verified=False still fail.

Do NOT:
- Invent a subject that auth will not emit
- Hard-code owner identity in source
- Leave the allowlist empty (fail-closed)
- Disable authorization checks
- Put tokens or passwords in PAPER_QUALIFICATION_OWNER_SUBJECTS
""".strip()
