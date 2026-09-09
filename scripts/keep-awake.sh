#!/usr/bin/env bash
# Prevent Mac sleep until an IST time (default 15:30).
# Usage: ./scripts/keep-awake.sh
#        CAFFEINATE_UNTIL=17:30 ./scripts/keep-awake.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/scripts/.run"
mkdir -p "$RUN_DIR"
PID_FILE="$RUN_DIR/caffeinate.pid"
CAFFEINATE_UNTIL="${CAFFEINATE_UNTIL:-15:30}"

ist_epoch_at() {
  local hm="$1"
  local d
  d="$(TZ=Asia/Kolkata date +%Y-%m-%d)"
  TZ=Asia/Kolkata date -j -f "%Y-%m-%d %H:%M:%S" "${d} ${hm}:00" +%s
}

seconds_until_ist() {
  local end now diff
  end="$(ist_epoch_at "$1")"
  now="$(TZ=Asia/Kolkata date +%s)"
  diff=$(( end - now ))
  [[ "$diff" -lt 0 ]] && echo 0 || echo "$diff"
}

stop_existing() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped previous caffeinate (pid $pid)"
    fi
    rm -f "$PID_FILE"
  fi
}

secs="$(seconds_until_ist "$CAFFEINATE_UNTIL")"
if [[ "$secs" -le 0 ]]; then
  echo "Already past $CAFFEINATE_UNTIL IST — nothing to do."
  exit 0
fi

stop_existing
echo "Keeping Mac awake until $CAFFEINATE_UNTIL IST (~$(( secs / 60 )) min)"
caffeinate -dims -t "$secs" &
echo $! >"$PID_FILE"
echo "caffeinate pid $(cat "$PID_FILE") — stop early: kill \$(cat $PID_FILE)"
