#!/usr/bin/env bash
# One-process host: built UI + API. Suitable for a cheap Node/Python box with a disk.
# Required on the host:
#   PORT                 (set by Render, Fly, Railway)
#   SCAN_BHAV_DATA       writable directory that survives restarts
#   ALLOWED_ORIGINS      your public https origin, comma-separated
#   AUTH_JWT_SECRET      long random string
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
if [[ ! -f frontend/dist/index.html ]]; then
  (cd frontend && npm install && npm run build)
fi
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
exec uvicorn api:app --host "$HOST" --port "$PORT"
