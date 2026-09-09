#!/usr/bin/env bash
# Start FastAPI (uvicorn) + Vite UI together. Restarts each process if it exits.
#
# Usage:
#   ./scripts/dev.sh              # requires bash — do not use "sh scripts/dev.sh"
#   RESTART=0 ./scripts/dev.sh
#   FREE_PORTS=0 ./scripts/dev.sh
#
# UI:  http://127.0.0.1:5173
# API: http://127.0.0.1:8000/health

set -euo pipefail

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "[dev] ERROR: use bash — run: ./scripts/dev.sh"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
RESTART="${RESTART:-1}"
RELOAD="${RELOAD:-0}"
FREE_PORTS="${FREE_PORTS:-1}"
API_HOST="${API_HOST:-127.0.0.1}"
UI_HOST="${UI_HOST:-127.0.0.1}"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "[dev] frontend/node_modules missing — run: cd frontend && npm install"
  exit 1
fi

port_pids() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true
}

port_in_use() {
  [[ -n "$(port_pids "$1")" ]]
}

free_port() {
  local label="$1" port="$2"
  local pids
  pids="$(port_pids "$port")"
  [[ -n "$pids" ]] || return 0

  if [[ "$FREE_PORTS" != "1" ]]; then
    echo "[dev] ERROR: $label port $port in use (PIDs: $(echo "$pids" | tr '\n' ' '))"
    echo "[dev] Kill manually or run: FREE_PORTS=1 ./scripts/dev.sh"
    exit 1
  fi

  echo "[dev] freeing $label port $port (PIDs: $(echo "$pids" | tr '\n' ' '))"
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done <<< "$pids"
  sleep 1

  pids="$(port_pids "$port")"
  if [[ -n "$pids" ]]; then
    echo "[dev] force-killing listeners on port $port"
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
    done <<< "$pids"
    sleep 0.5
  fi
}

stop_dev_servers() {
  free_port "API" "$API_PORT"
  free_port "UI" "$UI_PORT"
  pkill -f "uvicorn api:app.*--port ${API_PORT}" 2>/dev/null || true
  pkill -f "uvicorn api:app.*--port ${API_PORT}" 2>/dev/null || true
  pkill -f "vite.*--port ${UI_PORT}" 2>/dev/null || true
  pkill -f "node.*vite.*${UI_PORT}" 2>/dev/null || true
}

WRAPPER_PIDS=()

stop_all() {
  echo
  echo "[dev] stopping…"
  for pid in "${WRAPPER_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  stop_dev_servers
  wait 2>/dev/null || true
}

trap stop_all EXIT INT TERM

run_api() {
  while true; do
    free_port "API" "$API_PORT"
    if [[ "$RELOAD" == "1" ]]; then
      echo "[api] uvicorn api:app --reload --host $API_HOST --port $API_PORT (reload kills in-flight screener scans)"
      set +e
      uvicorn api:app --reload --host "$API_HOST" --port "$API_PORT"
      code=$?
      set -e
    else
      echo "[api] uvicorn api:app --host $API_HOST --port $API_PORT"
      set +e
      uvicorn api:app --host "$API_HOST" --port "$API_PORT"
      code=$?
      set -e
    fi
    [[ "$RESTART" == "1" ]] || break
    echo "[api] exited ($code) — restart in 3s (Ctrl+C to quit)"
    sleep 3
  done
}

run_ui() {
  while true; do
    free_port "UI" "$UI_PORT"
    echo "[ui] vite → http://$UI_HOST:$UI_PORT"
    set +e
    (cd "$ROOT/frontend" && npm run dev -- --host "$UI_HOST" --port "$UI_PORT")
    code=$?
    set -e
    [[ "$RESTART" == "1" ]] || break
    echo "[ui] exited ($code) — restart in 3s (Ctrl+C to quit)"
    sleep 3
  done
}

stop_dev_servers

echo "[dev] Stock Adda — backend :$API_PORT + UI :$UI_PORT (RESTART=$RESTART)"
echo "[dev] Press Ctrl+C to stop both"

run_api &
WRAPPER_PIDS+=("$!")
run_ui &
WRAPPER_PIDS+=("$!")

wait
