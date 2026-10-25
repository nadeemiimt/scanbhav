#!/usr/bin/env bash
# Install Scan Bhav Python deps in a resolver-safe order.
# fyers-apiv3 pins ancient requests/aiohttp that conflict with growwapi —
# so FYERS is installed with --no-deps after groww + kite.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
PIP="${PIP:-$PYTHON -m pip}"

echo "[deps] core"
$PIP install -U pip setuptools wheel
$PIP install -r "$ROOT/requirements.txt"

echo "[deps] kiteconnect + growwapi"
$PIP install "kiteconnect>=5.0" "growwapi>=1.5"

echo "[deps] fyers-apiv3 (--no-deps; avoids requests/aiohttp pin war with groww)"
$PIP install "fyers-apiv3>=3.1.14" --no-deps
# Soft deps that do not fight groww's pins
$PIP install "websocket-client>=1.6" || true

if [[ "${SCAN_BHAV_INSTALL_OPTIONAL:-0}" == "1" ]]; then
  echo "[deps] optional"
  $PIP install -r "$ROOT/requirements-optional.txt" || true
fi

if [[ "${SCAN_BHAV_INSTALL_PACKAGING:-0}" == "1" ]]; then
  echo "[deps] packaging"
  $PIP install -r "$ROOT/requirements-packaging.txt"
fi

echo "[deps] done"
