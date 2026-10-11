"""Operator-friendly owner allowlist configuration after verified Supabase Auth.

Never invents a subject. Never writes credentials. Never disables auth checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.onboarding.errors import OnboardingBlockedError, OnboardingError
from app.onboarding.owner import require_authenticated_owner
from app.onboarding.supabase_owner import (
    VerifiedOwnerIdentity,
    sign_in_supabase_password,
    verify_supabase_access_token,
)
from app.qualification.auth import AuthenticatedOwner


_ENV_KEY = "PAPER_QUALIFICATION_OWNER_SUBJECTS"
_ENV_LINE_RE = re.compile(rf"^{re.escape(_ENV_KEY)}\s*=(.*)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class OwnerSetupResult:
    ok: bool
    subject: str | None
    env_path: str | None
    allowlist_written: bool
    verification_passed: bool
    detail: str
    owner_actions: tuple[str, ...] = ()


def default_env_path() -> Path:
    """Repository-root private ``.env`` (never commit)."""
    # backend/app/onboarding/owner_setup.py → repo root is parents[3]
    return Path(__file__).resolve().parents[3] / ".env"


def read_allowlist_raw(env_path: Path) -> str:
    if not env_path.is_file():
        return ""
    text = env_path.read_text(encoding="utf-8")
    match = _ENV_LINE_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def write_owner_allowlist_subject(
    subject: str,
    *,
    env_path: Path | None = None,
) -> Path:
    """Set PAPER_QUALIFICATION_OWNER_SUBJECTS to the verified subject only."""
    email = (subject or "").strip().lower()
    if not email or "@" not in email:
        raise OnboardingError("refusing to write invalid subject", code="invalid_subject")
    path = env_path or default_env_path()
    if not path.is_file():
        raise OnboardingBlockedError(
            f"Private env file not found at {path}. Create it from .env.example first.",
            code="env_missing",
        )
    # Refuse writing into anything that looks committed/example
    if path.name.endswith(".example"):
        raise OnboardingError("refusing to write allowlist into .env.example", code="env_example")

    original = path.read_text(encoding="utf-8")
    replacement = f"{_ENV_KEY}={email}"
    if _ENV_LINE_RE.search(original):
        updated = _ENV_LINE_RE.sub(replacement, original, count=1)
    else:
        sep = "" if original.endswith("\n") or not original else "\n"
        updated = original + sep + replacement + "\n"
    path.write_text(updated, encoding="utf-8")
    return path


def verify_allowlist_accepts_subject(
    subject: str,
    *,
    settings: Settings | None = None,
) -> AuthenticatedOwner:
    """Fail-closed verification via existing auth helper."""
    cfg = settings or get_settings()
    return require_authenticated_owner(
        subject=subject,
        credential_verified=True,
        settings=cfg,
    )


def configure_owner_from_password(
    email: str,
    password: str,
    *,
    env_path: Path | None = None,
    write_env: bool = True,
    settings: Settings | None = None,
    transport=None,
) -> OwnerSetupResult:
    """Sign in with Supabase, write allowlist, verify resolve_authenticated_owner."""
    identity, _access_token = sign_in_supabase_password(
        email, password, settings=settings, transport=transport
    )
    # Drop token reference immediately; do not return it.
    del _access_token
    return _finalize_setup(
        identity, env_path=env_path, write_env=write_env, settings=settings
    )


def configure_owner_from_access_token(
    access_token: str,
    *,
    env_path: Path | None = None,
    write_env: bool = True,
    settings: Settings | None = None,
    transport=None,
) -> OwnerSetupResult:
    identity = verify_supabase_access_token(
        access_token, settings=settings, transport=transport
    )
    return _finalize_setup(
        identity, env_path=env_path, write_env=write_env, settings=settings
    )


def _finalize_setup(
    identity: VerifiedOwnerIdentity,
    *,
    env_path: Path | None,
    write_env: bool,
    settings: Settings | None,
) -> OwnerSetupResult:
    path = env_path or default_env_path()
    written = False
    if write_env:
        write_owner_allowlist_subject(identity.subject, env_path=path)
        written = True
        # Reload settings from dotenv
        get_settings.cache_clear()
        cfg = get_settings()
    else:
        # In-memory verification only — construct Settings overlay
        base = settings or get_settings()
        cfg = base.model_copy(
            update={"paper_qualification_owner_subjects": identity.subject}
        )

    try:
        owner = verify_allowlist_accepts_subject(identity.subject, settings=cfg)
    except Exception as exc:  # noqa: BLE001
        return OwnerSetupResult(
            ok=False,
            subject=identity.subject,
            env_path=str(path) if written else None,
            allowlist_written=written,
            verification_passed=False,
            detail=f"allowlist written but verification failed: {exc}",
            owner_actions=(
                "Confirm PAPER_QUALIFICATION_OWNER_SUBJECTS matches the signed-in email exactly.",
                "Restart any running API process after editing .env.",
            ),
        )

    return OwnerSetupResult(
        ok=True,
        subject=owner.subject,
        env_path=str(path) if written else None,
        allowlist_written=written,
        verification_passed=True,
        detail="Owner authenticated via Supabase and allowlist verified",
        owner_actions=(
            "Keep the private .env file out of git.",
            "Do not share your password or access token.",
            "Next: register the Alpaca paper account (is_enabled stays false).",
        ),
    )


OWNER_SETUP_OPERATOR_STEPS = """
Owner setup (simple steps — no programming required)
====================================================

What this does:
  Proves you can sign in, then saves YOUR verified email into the private
  allowlist so the platform recognizes you as the owner.

What this does NOT do:
  It does not approve a strategy, enable trading, or place any orders.

Prerequisites:
  1. You already have a Supabase account email+password for this project
     (the same project configured in the private repository-root `.env`).
  2. The private file `.env` exists at the repository root (copy from
     `.env.example` if needed). Never commit `.env`.

Steps:
  1. Open a terminal in the repository root.
  2. Run:
       cd backend
       .venv/bin/python -m app.onboarding.owner_setup_cli
  3. Choose option 1 (email + password).
  4. Enter the email and password for your Supabase login when prompted.
     (Nothing is printed back except success/failure.)
  5. On success, the tool writes:
       PAPER_QUALIFICATION_OWNER_SUBJECTS=<your-verified-email>
     into the private `.env` file and verifies authorization.
  6. If an API server is running, restart it so it reloads `.env`.

Alternative (advanced):
  If you already have a Supabase access token from a signed-in session,
  choose option 2 and paste the token. The token is not saved.

If sign-in fails:
  - Confirm the Supabase user exists and the email is confirmed.
  - Confirm SUPABASE_URL and SUPABASE_ANON_KEY in `.env` are correct.
  - Do not invent an email that has never signed up.
""".strip()
