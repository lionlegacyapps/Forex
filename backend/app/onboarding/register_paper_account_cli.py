"""Register verified Alpaca paper account after owner auth (is_enabled=false).

Usage (from backend/):
  .venv/bin/python -m app.onboarding.register_paper_account_cli

Refuses to run when allowlist is empty or credentials are not verified.
Never prints API secrets. Never enables the account.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.db.session import get_session_factory, reset_db_state
from app.onboarding.account import verify_and_register_alpaca_paper_account
from app.onboarding.owner import owner_allowlist_status, require_authenticated_owner
from app.onboarding.supabase_owner import sign_in_supabase_password


def _mask(subject: str) -> str:
    if "@" not in subject:
        return "***"
    local, domain = subject.split("@", 1)
    return f"{local[:2]}…@{domain}" if len(local) > 2 else f"*@{domain}"


async def _run() -> int:
    get_settings.cache_clear()
    reset_db_state()
    settings = get_settings()
    if settings.paper_session_execute_enabled:
        print("ERROR: PAPER_SESSION_EXECUTE_ENABLED must be false")
        return 2
    status = owner_allowlist_status(settings)
    if not status.configured:
        print("ERROR: Owner allowlist empty. Run owner_setup_cli first.")
        return 2

    print("Sign in to prove you are the allowlisted owner.")
    email = input("Supabase email: ").strip()
    password = getpass.getpass("Supabase password (hidden): ")
    identity, token = sign_in_supabase_password(email, password, settings=settings)
    del token
    owner = require_authenticated_owner(
        subject=identity.subject,
        credential_verified=True,
        settings=settings,
    )
    print(f"Owner verified (masked): {_mask(owner.subject)}")

    factory = get_session_factory()
    with factory() as db:
        result = await verify_and_register_alpaca_paper_account(
            db,
            owner=owner,
            settings=settings,
            enable_account=False,
        )
        db.commit()
        print("BROKER ACCOUNT REGISTRATION: PASS")
        print(f"account_id={result.account_id}")
        print(f"external_masked={result.external_account_id_masked}")
        print(f"trading_mode={result.trading_mode}")
        print(f"is_enabled={result.is_enabled} (left false on purpose)")
        print(f"created_new={result.created_new}")
        print(f"paper_host={result.paper_endpoint_host}")
        print("Do NOT enable the account without a separate owner decision.")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print(f"REGISTRATION FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
