"""Supabase Auth → authenticated owner subject (smallest safe integration).

The platform previously had no HTTP/session auth that produced an owner subject.
This module verifies a real Supabase Auth session and returns the confirmed
email as the subject for PAPER_QUALIFICATION_OWNER_SUBJECTS.

Never invents subjects. Never logs tokens or passwords. Never bypasses checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.onboarding.errors import OnboardingBlockedError, OnboardingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VerifiedOwnerIdentity:
    """Server-verified owner identity from Supabase Auth."""

    subject: str  # confirmed email
    supabase_user_id: str
    email_confirmed: bool
    auth_provider: str = "supabase"


class OwnerAuthError(OnboardingError):
    def __init__(self, message: str, *, code: str = "owner_auth_failed") -> None:
        super().__init__(message, code=code)


def _supabase_base(settings: Settings) -> str:
    base = (settings.supabase_url or "").strip().rstrip("/")
    if not base:
        raise OnboardingBlockedError(
            "SUPABASE_URL is not configured in the private .env file",
            code="supabase_url_missing",
        )
    return base


def _anon_key(settings: Settings) -> str:
    key = (settings.supabase_anon_key or "").strip()
    if not key:
        raise OnboardingBlockedError(
            "SUPABASE_ANON_KEY is not configured in the private .env file",
            code="supabase_anon_missing",
        )
    return key


def _auth_headers(anon_key: str, *, access_token: str | None = None) -> dict[str, str]:
    token = access_token or anon_key
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _extract_identity(payload: dict[str, Any]) -> VerifiedOwnerIdentity:
    email = (payload.get("email") or "").strip().lower()
    user_id = str(payload.get("id") or "").strip()
    confirmed_at = payload.get("email_confirmed_at") or payload.get("confirmed_at")
    if not email or "@" not in email:
        raise OwnerAuthError(
            "Supabase user has no usable email subject",
            code="owner_email_missing",
        )
    if not confirmed_at:
        raise OwnerAuthError(
            "Supabase email is not confirmed; confirm the email before owner setup",
            code="owner_email_unconfirmed",
        )
    if not user_id:
        raise OwnerAuthError(
            "Supabase user id missing from auth response",
            code="owner_user_id_missing",
        )
    app_meta = payload.get("app_metadata") if isinstance(payload.get("app_metadata"), dict) else {}
    providers = app_meta.get("providers") if isinstance(app_meta, dict) else None
    provider = "supabase"
    if isinstance(providers, list) and providers:
        provider = str(providers[0])
    return VerifiedOwnerIdentity(
        subject=email,
        supabase_user_id=user_id,
        email_confirmed=True,
        auth_provider=provider,
    )


def verify_supabase_access_token(
    access_token: str,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> VerifiedOwnerIdentity:
    """Validate an existing Supabase access token and return the owner subject."""
    token = (access_token or "").strip()
    if not token:
        raise OwnerAuthError("access token required", code="access_token_missing")
    # Never log the token.
    cfg = settings or get_settings()
    base = _supabase_base(cfg)
    anon = _anon_key(cfg)
    url = f"{base}/auth/v1/user"
    try:
        with httpx.Client(timeout=20.0, transport=transport) as client:
            response = client.get(url, headers=_auth_headers(anon, access_token=token))
    except httpx.HTTPError as exc:
        raise OwnerAuthError(
            "Supabase auth network error while verifying access token",
            code="supabase_network_error",
        ) from exc

    if response.status_code in {401, 403}:
        raise OwnerAuthError(
            "Supabase access token rejected (not authenticated)",
            code="access_token_rejected",
        )
    if response.status_code >= 400:
        raise OwnerAuthError(
            f"Supabase user lookup failed (HTTP {response.status_code})",
            code="supabase_user_lookup_failed",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise OwnerAuthError("unexpected Supabase user payload", code="supabase_bad_payload")
    identity = _extract_identity(payload)
    logger.info(
        "supabase_owner_verified",
        extra={
            "email_domain": identity.subject.split("@", 1)[-1],
            "email_confirmed": identity.email_confirmed,
            "provider": identity.auth_provider,
        },
    )
    return identity


def sign_in_supabase_password(
    email: str,
    password: str,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[VerifiedOwnerIdentity, str]:
    """Sign in with email/password via Supabase Auth; return identity + access token.

    The access token is returned only to the caller for immediate verification /
    allowlist setup. Callers must not log or persist it in git.
    """
    cfg = settings or get_settings()
    base = _supabase_base(cfg)
    anon = _anon_key(cfg)
    email_norm = (email or "").strip().lower()
    if not email_norm or "@" not in email_norm:
        raise OwnerAuthError("email required for password sign-in", code="email_required")
    if not password:
        raise OwnerAuthError("password required for password sign-in", code="password_required")

    url = f"{base}/auth/v1/token?grant_type=password"
    try:
        with httpx.Client(timeout=20.0, transport=transport) as client:
            response = client.post(
                url,
                headers=_auth_headers(anon),
                json={"email": email_norm, "password": password},
            )
    except httpx.HTTPError as exc:
        raise OwnerAuthError(
            "Supabase auth network error during password sign-in",
            code="supabase_network_error",
        ) from exc

    if response.status_code in {400, 401, 403}:
        # Do not echo server body (may leak details).
        raise OwnerAuthError(
            "Supabase sign-in failed — check email/password, or confirm the account exists",
            code="sign_in_rejected",
        )
    if response.status_code >= 400:
        raise OwnerAuthError(
            f"Supabase sign-in failed (HTTP {response.status_code})",
            code="sign_in_failed",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise OwnerAuthError("unexpected sign-in payload", code="supabase_bad_payload")
    access_token = (payload.get("access_token") or "").strip()
    if not access_token:
        raise OwnerAuthError("sign-in response missing access_token", code="access_token_missing")
    user = payload.get("user") if isinstance(payload.get("user"), dict) else None
    if user is None:
        # Fall back to /auth/v1/user with the new token
        identity = verify_supabase_access_token(
            access_token, settings=cfg, transport=transport
        )
    else:
        identity = _extract_identity(user)
    # Defense: signed-in email must match the email the operator typed.
    if identity.subject != email_norm:
        raise OwnerAuthError(
            "signed-in email does not match the email you entered",
            code="email_mismatch",
        )
    return identity, access_token
