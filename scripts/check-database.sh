#!/usr/bin/env bash
# Safe database connectivity check (SELECT 1). Prints no secrets.
# Uses repository-root .env as the source of truth (not a stale shell DATABASE_URL).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/backend"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
# Prevent leftover shell exports from masking an empty/misconfigured .env during this check.
unset DATABASE_URL || true
exec python - <<'PY'
from app.core.config import env_file_path, get_settings
from app.core.logging import configure_logging
from app.db.health import check_database_connection
from app.db.session import reset_db_state
from app.db.target import DatabaseTargetKind, inspect_database_target

get_settings.cache_clear()
reset_db_state()
settings = get_settings()
configure_logging(settings)

env_path = env_file_path()
print(f"ENV_FILE: {env_path}")

if not settings.is_database_configured:
    print("RESULT: FAILED")
    print("REASON: DATABASE_URL is not configured in the repository-root .env")
    raise SystemExit(1)

assert settings.database_url is not None
try:
    check_database_connection()
    info = inspect_database_target(settings.database_url)
except Exception:
    print("RESULT: FAILED")
    print("REASON: database connection or target inspection error")
    raise SystemExit(1)

print("RESULT: SUCCESS")
print("CHECK: SELECT 1")
if info.kind == DatabaseTargetKind.SUPABASE:
    print("TARGET: Supabase PostgreSQL")
elif info.kind == DatabaseTargetKind.LOCAL:
    print("TARGET: Local PostgreSQL (not Supabase)")
    raise SystemExit(2)
else:
    print("TARGET: Unknown")
    raise SystemExit(2)
PY
