#!/usr/bin/env bash
# Unattended NSE trading day — keep Mac awake, run API, start/resume Autopilot session.
#
# Usage (run in Terminal before you leave):
#   ./scripts/autopilot-day.sh
#   nohup ./scripts/autopilot-day.sh >> scripts/logs/autopilot-day.log 2>&1 &
#
# Optional env (or copy scripts/autopilot-day.env.example → scripts/autopilot-day.env):
#   CAFFEINATE_UNTIL=15:30   IST — prevent sleep until this time (default 15:30)
#   WATCH_UNTIL=17:30        IST — stop watchdog when you expect to be back
#                            Tip: set CAFFEINATE_UNTIL=17:30 if you want API up when you return at 5:30 PM
#   API_PORT=8000
#   POLL_SECONDS=30         health-check interval
#   PICK_MODE=curated_list  | agent_auto
#   SYMBOLS=RELIANCE.NSE,TCS.NSE   override curated list (else reads data/trading/config.json)
#   MAX_SPEND=200000  MAX_PROFIT=30000  MAX_LOSS=15000  MAX_CONCURRENT=3
#
# NSE flow (automatic once session starts):
#   09:00  pre-market analysis · 09:15–15:30 live trading · 15:20 square-off

set -euo pipefail

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "Use bash: ./scripts/autopilot-day.sh"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
[[ -f "$ROOT/scripts/autopilot-day.env" ]] && source "$ROOT/scripts/autopilot-day.env"

API_PORT="${API_PORT:-8000}"
API_HOST="${API_HOST:-127.0.0.1}"
API_URL="http://${API_HOST}:${API_PORT}"
POLL_SECONDS="${POLL_SECONDS:-30}"
CAFFEINATE_UNTIL="${CAFFEINATE_UNTIL:-15:30}"
WATCH_UNTIL="${WATCH_UNTIL:-17:30}"
MAX_SPEND="${MAX_SPEND:-200000}"
MAX_PROFIT="${MAX_PROFIT:-30000}"
MAX_LOSS="${MAX_LOSS:-15000}"
MAX_CONCURRENT="${MAX_CONCURRENT:-3}"
PICK_MODE="${PICK_MODE:-}"

LOG_DIR="$ROOT/scripts/logs"
RUN_DIR="$ROOT/scripts/.run"
mkdir -p "$LOG_DIR" "$RUN_DIR"
DAY="$(TZ=Asia/Kolkata date +%Y-%m-%d)"
LOG_FILE="$LOG_DIR/autopilot-day-${DAY}.log"
API_PID_FILE="$RUN_DIR/autopilot-api.pid"
CAFF_PID_FILE="$RUN_DIR/caffeinate.pid"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

log() {
  local msg="[$(TZ=Asia/Kolkata date '+%H:%M:%S IST')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

ist_epoch_at() {
  local hm="$1"
  local d
  d="$(TZ=Asia/Kolkata date +%Y-%m-%d)"
  TZ=Asia/Kolkata date -j -f "%Y-%m-%d %H:%M:%S" "${d} ${hm}:00" +%s 2>/dev/null || echo 0
}

seconds_until_ist() {
  local hm="$1"
  local end now
  end="$(ist_epoch_at "$hm")"
  now="$(TZ=Asia/Kolkata date +%s)"
  local diff=$(( end - now ))
  if [[ "$diff" -lt 0 ]]; then
    echo 0
  else
    echo "$diff"
  fi
}

load_session_payload() {
  python3 - <<'PY'
import json
import os
from pathlib import Path

cfg = json.loads(Path("data/trading/config.json").read_text(encoding="utf-8"))
ap = cfg.get("autopilot") or {}
risk = cfg.get("risk") or {}

pick_mode = os.environ.get("PICK_MODE") or ap.get("pick_mode") or "curated_list"
sym_env = os.environ.get("SYMBOLS", "").strip()
if sym_env:
    symbols = [s.strip().upper() for s in sym_env.split(",") if s.strip()]
else:
    symbols = list(ap.get("curated_symbols") or cfg.get("watchlist") or [])

payload = {
    "pick_mode": pick_mode,
    "symbols": symbols if pick_mode == "curated_list" else None,
    "max_spend_inr": float(os.environ.get("MAX_SPEND") or risk.get("max_daily_notional_inr") or 200000),
    "max_profit_inr": float(os.environ.get("MAX_PROFIT") or risk.get("max_profit_inr") or 30000),
    "max_loss_inr": float(os.environ.get("MAX_LOSS") or risk.get("max_intraday_loss_inr") or 15000),
    "max_concurrent_picks": int(os.environ.get("MAX_CONCURRENT") or ap.get("max_concurrent_picks") or 3),
}
print(json.dumps(payload))
PY
}

api_ok() {
  curl -sf -m 8 "${API_URL}/health" >/dev/null 2>&1
}

api_get() {
  curl -sf -m 15 "${API_URL}$1"
}

api_post_json() {
  local path="$1" body="$2"
  curl -sf -m 30 -X POST "${API_URL}${path}" \
    -H "Content-Type: application/json" \
    -d "$body"
}

api_patch_json() {
  local path="$1" body="$2"
  curl -sf -m 30 -X PATCH "${API_URL}${path}" \
    -H "Content-Type: application/json" \
    -d "$body"
}

stop_api() {
  if [[ -f "$API_PID_FILE" ]]; then
    local pid
    pid="$(cat "$API_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      log "Stopping API pid $pid"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$API_PID_FILE"
  fi
  local pids
  pids="$(lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    log "Freeing port $API_PORT (PIDs: $(echo "$pids" | tr '\n' ' '))"
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
    done <<< "$pids"
    sleep 1
  fi
}

start_api() {
  stop_api
  log "Starting API on ${API_URL}"
  nohup uvicorn api:app --host "$API_HOST" --port "$API_PORT" >>"$LOG_FILE" 2>&1 &
  echo $! >"$API_PID_FILE"
  log "API pid $(cat "$API_PID_FILE")"
}

wait_for_api() {
  local tries="${1:-40}"
  local i
  for (( i=1; i<=tries; i++ )); do
    if api_ok; then
      log "API healthy (${API_URL}/health)"
      return 0
    fi
    sleep 2
  done
  log "ERROR: API did not become healthy"
  return 1
}

enable_autopilot_scheduler() {
  log "Enabling autopilot scheduler"
  api_patch_json "/api/trading/config" '{"autopilot":{"enabled":true,"paper_autopilot":true}}' >/dev/null \
    || log "WARN: could not PATCH autopilot enabled"
}

session_is_active() {
  local status active
  status="$(api_get "/api/trading/session/status" 2>/dev/null || echo '{}')"
  active="$(python3 -c "import json,sys; d=json.load(sys.stdin); print('1' if d.get('active') else '0')" <<<"$status" 2>/dev/null || echo 0)"
  [[ "$active" == "1" ]]
}

start_trading_session() {
  local payload
  payload="$(load_session_payload)"
  log "Starting trading session: $payload"
  if api_post_json "/api/trading/session/start" "$payload" >/dev/null 2>&1; then
    log "Session started OK"
    return 0
  fi
  if session_is_active; then
    log "Session already active — continuing"
    return 0
  fi
  log "WARN: session start failed (may already be completed for today)"
  return 1
}

ensure_session() {
  if session_is_active; then
    log "Session active — scheduler will continue trading"
    return 0
  fi
  local phase
  phase="$(api_get "/api/trading/session/nse-hours" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('phase',''))" 2>/dev/null || echo "")"
  case "$phase" in
    weekend|post_close|overnight)
      log "NSE phase '$phase' — not starting new session"
      return 0
      ;;
  esac
  start_trading_session || true
}

start_caffeinate() {
  local secs
  secs="$(seconds_until_ist "$CAFFEINATE_UNTIL")"
  if [[ "$secs" -le 0 ]]; then
    log "CAFFEINATE_UNTIL ($CAFFEINATE_UNTIL IST) already passed — not starting caffeinate"
    return 0
  fi
  log "Preventing Mac sleep until $CAFFEINATE_UNTIL IST (~$(( secs / 60 )) min) [caffeinate -dims]"
  caffeinate -dims -t "$secs" >>"$LOG_FILE" 2>&1 &
  echo $! >"$CAFF_PID_FILE"
}

cleanup() {
  log "Shutting down autopilot-day watchdog"
  if [[ -f "$CAFF_PID_FILE" ]]; then
    kill "$(cat "$CAFF_PID_FILE" 2>/dev/null)" 2>/dev/null || true
    rm -f "$CAFF_PID_FILE"
  fi
  # Leave API running so user can review when back — set STOP_API=1 to kill it
  if [[ "${STOP_API:-0}" == "1" ]]; then
    stop_api
  else
    log "API left running (set STOP_API=1 to stop on exit)"
  fi
}

trap cleanup EXIT INT TERM

main() {
  log "========== Autopilot day watchdog =========="
  log "Log file: $LOG_FILE"
  log "CAFFEINATE_UNTIL=$CAFFEINATE_UNTIL IST · WATCH_UNTIL=$WATCH_UNTIL IST · poll=${POLL_SECONDS}s"

  start_caffeinate

  if api_ok; then
    log "API already running on port $API_PORT"
  else
    start_api
    wait_for_api || exit 1
  fi

  enable_autopilot_scheduler
  ensure_session

  while true; do
    local remain
    remain="$(seconds_until_ist "$WATCH_UNTIL")"
    if [[ "$remain" -le 0 ]]; then
      log "WATCH_UNTIL ($WATCH_UNTIL IST) reached — done for today"
      local summary
      summary="$(api_get "/api/trading/session/status" 2>/dev/null || echo '{}')"
      log "Final session status: $(echo "$summary" | python3 -c "import json,sys; d=json.load(sys.stdin); s=d.get('session') or {}; print(f\"active={d.get('active')} pnl={s.get('realized_pnl_inr')} reason={s.get('completion_reason')}\")" 2>/dev/null || echo 'n/a')"
      break
    fi

    if ! api_ok; then
      log "API down — restarting"
      start_api
      if wait_for_api 30; then
        enable_autopilot_scheduler
        ensure_session
      else
        log "ERROR: API restart failed — retry in ${POLL_SECONDS}s"
      fi
    else
      # Periodic session check during market hours
      local phase
      phase="$(api_get "/api/trading/session/nse-hours" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('phase',''))" 2>/dev/null || echo "")"
      if [[ "$phase" == "pre_market" || "$phase" == "trading" ]]; then
        ensure_session
      fi
    fi

    sleep "$POLL_SECONDS"
  done
}

main "$@"
