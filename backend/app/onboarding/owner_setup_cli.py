"""Interactive CLI for non-programmer owner allowlist setup.

Usage (from backend/):
  .venv/bin/python -m app.onboarding.owner_setup_cli

Never prints passwords or tokens.
"""

from __future__ import annotations

import getpass
import sys

from app.core.config import get_settings
from app.onboarding.owner_setup import (
    OWNER_SETUP_OPERATOR_STEPS,
    configure_owner_from_access_token,
    configure_owner_from_password,
    default_env_path,
    read_allowlist_raw,
)


def _mask_subject(subject: str) -> str:
    if "@" not in subject:
        return "***"
    local, domain = subject.split("@", 1)
    if len(local) <= 2:
        return f"*@{domain}"
    return f"{local[:2]}…@{domain}"


def main(argv: list[str] | None = None) -> int:
    _ = argv
    print(OWNER_SETUP_OPERATOR_STEPS)
    print()
    env_path = default_env_path()
    print(f"Private env file: {env_path}")
    if not env_path.is_file():
        print("ERROR: .env not found. Copy .env.example to .env first, then fill Supabase values.")
        return 2

    current = read_allowlist_raw(env_path)
    if current:
        print(f"Current allowlist entry present: {_mask_subject(current)}")
    else:
        print("Current allowlist: (empty — fail closed)")

    get_settings.cache_clear()
    settings = get_settings()
    if settings.paper_session_execute_enabled:
        print("ERROR: PAPER_SESSION_EXECUTE_ENABLED is true. Turn it off before owner setup.")
        return 2
    if not settings.supabase_url or not settings.supabase_anon_key:
        print("ERROR: SUPABASE_URL / SUPABASE_ANON_KEY missing in .env")
        return 2

    print()
    print("Choose how to prove your identity:")
    print("  1) Email + password (recommended)")
    print("  2) Paste an existing Supabase access token")
    print("  3) Exit without changes")
    choice = (input("Enter 1, 2, or 3: ").strip() or "3")

    try:
        if choice == "1":
            email = input("Supabase email: ").strip()
            password = getpass.getpass("Supabase password (hidden): ")
            result = configure_owner_from_password(
                email, password, env_path=env_path, write_env=True
            )
        elif choice == "2":
            token = getpass.getpass("Supabase access token (hidden): ")
            result = configure_owner_from_access_token(
                token, env_path=env_path, write_env=True
            )
        else:
            print("No changes made.")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"SETUP FAILED: {exc}")
        print("Owner setup remains incomplete. Authentication was not bypassed.")
        return 1

    if result.ok:
        print("OWNER SETUP: PASS")
        if result.subject:
            print(f"Verified subject (masked): {_mask_subject(result.subject)}")
        print(result.detail)
        for action in result.owner_actions:
            print(f" - {action}")
        return 0

    print("OWNER SETUP: BLOCKED")
    print(result.detail)
    for action in result.owner_actions:
        print(f" - {action}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
