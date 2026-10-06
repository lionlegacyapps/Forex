#!/usr/bin/env bash
# Apply Alembic migrations only after confirming the target is Supabase.
# Prints no secrets. Uses repository-root .env as source of truth.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/backend"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
unset DATABASE_URL || true

python - <<'PY'
from app.core.config import env_file_path, get_settings
from app.db.session import reset_db_state
from app.db.target import require_supabase_target

get_settings.cache_clear()
reset_db_state()
settings = get_settings()
print(f"ENV_FILE: {env_file_path()}")
if not settings.is_database_configured:
    print("RESULT: FAILED")
    print("REASON: DATABASE_URL missing in repository-root .env")
    raise SystemExit(1)
assert settings.database_url is not None
info = require_supabase_target(settings.database_url)
print("RESULT: TARGET_CONFIRMED")
print("TARGET: Supabase PostgreSQL")
print(f"HAS_AUTH_SCHEMA: {info.has_supabase_auth_schema}")
PY

exec alembic upgrade head
