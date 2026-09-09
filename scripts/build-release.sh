#!/usr/bin/env bash
# Build Stock Adda distributable for macOS (and Linux folder bundle).
#
# Usage:
#   ./scripts/build-release.sh
#
# Outputs (under dist/release/):
#   macOS: StockAdda.app, StockAdda-macOS.dmg, StockAdda-macOS.zip
#   Linux: StockAdda/ folder + StockAdda-Linux.zip
#
# Windows: run scripts/build-release.ps1 on a Windows machine.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${STOCK_ADDA_VERSION:-0.6.0}"
RELEASE_DIR="$ROOT/dist/release"
APP_NAME="StockAdda"

echo "[release] Stock Adda v${VERSION}"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

echo "[release] 1/5 — frontend production build"
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi
(cd "$ROOT/frontend" && npm run build)

echo "[release] 2/5 — bundle seed data"
python3 "$ROOT/packaging/prepare_bundle_data.py"

echo "[release] 3/5 — PyInstaller"
pip install -q -r "$ROOT/requirements-packaging.txt"
pyinstaller "$ROOT/packaging/stock_adda.spec" --clean --noconfirm --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller"

mkdir -p "$RELEASE_DIR"

if [[ "$(uname -s)" == "Darwin" ]] && [[ -d "$ROOT/dist/StockAdda.app" ]]; then
  echo "[release] 4/5 — macOS .app + .dmg + .zip"
  rm -rf "$RELEASE_DIR/StockAdda.app"
  cp -R "$ROOT/dist/StockAdda.app" "$RELEASE_DIR/"

  DMG="$RELEASE_DIR/StockAdda-macOS-v${VERSION}.dmg"
  rm -f "$DMG"
  hdiutil create -volname "Stock Adda" -srcfolder "$RELEASE_DIR/StockAdda.app" -ov -format UDZO "$DMG"

  ZIP="$RELEASE_DIR/StockAdda-macOS-v${VERSION}.zip"
  rm -f "$ZIP"
  (cd "$RELEASE_DIR" && zip -qr "$(basename "$ZIP")" StockAdda.app)

  echo "[release] 5/5 — done"
  echo "  App: $RELEASE_DIR/StockAdda.app"
  echo "  DMG: $DMG"
  echo "  ZIP: $ZIP"
else
  echo "[release] 4/5 — folder bundle + zip"
  BUNDLE="$ROOT/dist/StockAdda"
  if [[ ! -d "$BUNDLE" ]]; then
    echo "[release] ERROR: expected $BUNDLE — PyInstaller may have failed"
    exit 1
  fi
  rm -rf "$RELEASE_DIR/StockAdda"
  cp -R "$BUNDLE" "$RELEASE_DIR/StockAdda"
  ZIP="$RELEASE_DIR/StockAdda-$(uname -s)-v${VERSION}.zip"
  rm -f "$ZIP"
  (cd "$RELEASE_DIR" && zip -qr "$(basename "$ZIP")" StockAdda)
  echo "[release] 5/5 — done"
  echo "  Folder: $RELEASE_DIR/StockAdda"
  echo "  ZIP: $ZIP"
fi

echo "[release] First launch stores data in ~/Library/Application Support/StockAdda (macOS)"
