#!/usr/bin/env bash
# Safe database connectivity check (SELECT 1). Prints no secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/backend"
# Ensure repo-root .env is visible via app.core.config resolution.
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python - <<'PY'
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.health import check_database_connection
from app.db.session import reset_db_state

get_settings.cache_clear()
reset_db_state()
settings = get_settings()
configure_logging(settings)

if not settings.is_database_configured:
    print("RESULT: FAILED")
    print("REASON: DATABASE_URL is not configured")
    raise SystemExit(1)

try:
    check_database_connection()
except Exception:
    print("RESULT: FAILED")
    print("REASON: database connection error")
    raise SystemExit(1)

print("RESULT: SUCCESS")
print("CHECK: SELECT 1")
PY
