#!/usr/bin/env bash
# Build a shareable Windows portable folder+zip FROM macOS/Linux
# using the official Windows embeddable Python + win_amd64 wheels.
#
# Output:
#   dist/release/ScanBhav-Windows-portable/
#   dist/release/ScanBhav-Windows-vX.Y.Z-portable.zip
#
# Recipient: unzip → double-click ScanBhav.bat (needs 64-bit Windows).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${SCAN_BHAV_VERSION:-0.6.0}"
PY_VER="3.12.8"
PY_TAG="312"
RELEASE_DIR="$ROOT/dist/release"
STAGE="$RELEASE_DIR/ScanBhav-Windows-portable"
PY_DIR="$STAGE/python"
WHEEL_DIR="$ROOT/build/win_wheels"
ZIP_OUT="$RELEASE_DIR/ScanBhav-Windows-v${VERSION}-portable.zip"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

echo "[win-portable] 1/6 — frontend production build"
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi
(cd "$ROOT/frontend" && npm run build)

echo "[win-portable] 2/6 — download Windows embeddable Python ${PY_VER}"
rm -rf "$STAGE" "$WHEEL_DIR"
mkdir -p "$PY_DIR" "$WHEEL_DIR" "$RELEASE_DIR"
EMBED_ZIP="$ROOT/build/python-${PY_VER}-embed-amd64.zip"
EMBED_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-embed-amd64.zip"
if [[ ! -f "$EMBED_ZIP" ]]; then
  curl -fsSL "$EMBED_URL" -o "$EMBED_ZIP"
fi
unzip -q -o "$EMBED_ZIP" -d "$PY_DIR"

# Enable site-packages imports in embeddable Python.
PTH="$(ls "$PY_DIR"/python*._pth | head -1)"
{
  echo "python${PY_TAG}.zip"
  echo "."
  echo "Lib"
  echo "Lib/site-packages"
  echo "import site"
} > "$PTH"

echo "[win-portable] 3/6 — get pip into embeddable Python (via get-pip bootstrap files)"
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$ROOT/build/get-pip.py"
# We cannot execute Windows python here; instead vendor a prepared site-packages
# built from Windows wheels downloaded on this host.

echo "[win-portable] 4/6 — download Windows wheels"
# Core runtime (skip optional broker SDKs that fight on aiohttp pins).
cat > "$ROOT/build/requirements-win-portable.txt" <<'REQ'
pandas>=2.0
chromadb>=0.5,<2
ollama>=0.4
pypdf>=5
fastapi>=0.115
uvicorn[standard]>=0.30
requests>=2.31
python-dotenv>=1.0
yfinance>=0.2.54
python-multipart>=0.0.9
PyJWT>=2.8
numpy
REQ

pip download \
  -r "$ROOT/build/requirements-win-portable.txt" \
  -d "$WHEEL_DIR" \
  --platform win_amd64 \
  --python-version "${PY_TAG}" \
  --implementation cp \
  --abi "cp${PY_TAG}" \
  --only-binary=:all: \
  || pip download \
    -r "$ROOT/build/requirements-win-portable.txt" \
    -d "$WHEEL_DIR" \
    --platform win_amd64 \
    --python-version "${PY_TAG}" \
    --only-binary=:all:

# Install wheels into portable site-packages using host pip's target mode.
# Binary wheels are platform-tagged; extracting them is enough for Windows to import.
SITE="$PY_DIR/Lib/site-packages"
mkdir -p "$SITE"
python3 - <<PY
import zipfile
from pathlib import Path
wheel_dir = Path(r"$WHEEL_DIR")
site = Path(r"$SITE")
site.mkdir(parents=True, exist_ok=True)
count = 0
for whl in sorted(wheel_dir.glob("*.whl")):
    with zipfile.ZipFile(whl) as zf:
        zf.extractall(site)
    count += 1
    print("extracted", whl.name)
print(f"extracted {count} wheels into {site}")
PY

echo "[win-portable] 5/6 — copy application"
APP="$STAGE/app"
mkdir -p "$APP"
# App code (exclude bulky / local-only trees)
rsync -a \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude 'build' \
  --exclude '.git' \
  --exclude 'data/raw' \
  --exclude 'data/chroma' \
  --exclude 'data/user_secrets.json' \
  --exclude 'data/broker_tokens.json' \
  --exclude 'frontend/node_modules' \
  --exclude 'packaging/bundle_data' \
  "$ROOT/" "$APP/"

# Prefer production UI
mkdir -p "$APP/frontend/dist"
rsync -a "$ROOT/frontend/dist/" "$APP/frontend/dist/"

# Seed data for first run
python3 "$ROOT/packaging/prepare_bundle_data.py"
mkdir -p "$APP/packaging/bundle_data"
rsync -a "$ROOT/packaging/bundle_data/" "$APP/packaging/bundle_data/"

cat > "$STAGE/ScanBhav.bat" <<'BAT'
@echo off
setlocal
cd /d "%~dp0"
set SCAN_BHAV_DATA=%LOCALAPPDATA%\ScanBhav
if not exist "%SCAN_BHAV_DATA%" mkdir "%SCAN_BHAV_DATA%"
set PYTHONPATH=%~dp0app
set PATH=%~dp0python;%~dp0python\Scripts;%PATH%
echo Starting Scan Bhav...
echo Data folder: %SCAN_BHAV_DATA%
"%~dp0python\python.exe" "%~dp0app\packaging\launcher.py"
if errorlevel 1 pause
BAT

cat > "$STAGE/README-WINDOWS.txt" <<EOF
Scan Bhav ${VERSION} — Windows portable

1. Unzip this folder anywhere (e.g. Desktop\\ScanBhav).
2. Double-click ScanBhav.bat
3. A browser tab opens at http://127.0.0.1:8000
4. Optional keys: Settings → Your API keys (or edit %LOCALAPPDATA%\\ScanBhav\\.env)

No installer required. 64-bit Windows 10/11.
Core Analyze / Screen / Paper Autopilot / Backtest need no API key.
EOF

echo "[win-portable] 6/6 — zip"
rm -f "$ZIP_OUT"
(cd "$RELEASE_DIR" && zip -qr "$(basename "$ZIP_OUT")" "$(basename "$STAGE")")

echo "[win-portable] done"
echo "  Folder: $STAGE"
echo "  ZIP:    $ZIP_OUT"
du -sh "$STAGE" "$ZIP_OUT" || true
