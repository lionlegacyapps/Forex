#!/usr/bin/env bash
# Start the API locally without Docker (development helper).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/backend"
exec uvicorn app.main:app --reload --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
