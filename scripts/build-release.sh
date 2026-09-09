#!/usr/bin/env bash
# Build Scan Bhav distributable for macOS (and Linux folder bundle).
#
# Usage:
#   ./scripts/build-release.sh
#
# Outputs (under dist/release/):
#   macOS: ScanBhav.app, ScanBhav-macOS.dmg, ScanBhav-macOS.zip
#   Linux: ScanBhav/ folder + ScanBhav-Linux.zip
#
# Windows: run scripts/build-release.ps1 on a Windows machine.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${SCAN_BHAV_VERSION:-0.6.0}"
RELEASE_DIR="$ROOT/dist/release"
APP_NAME="ScanBhav"

echo "[release] Scan Bhav v${VERSION}"

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
pyinstaller "$ROOT/packaging/scan_bhav.spec" --clean --noconfirm --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller"

mkdir -p "$RELEASE_DIR"

if [[ "$(uname -s)" == "Darwin" ]] && [[ -d "$ROOT/dist/ScanBhav.app" ]]; then
  echo "[release] 4/5 — macOS .app + .dmg + .zip"
  rm -rf "$RELEASE_DIR/ScanBhav.app"
  cp -R "$ROOT/dist/ScanBhav.app" "$RELEASE_DIR/"

  DMG="$RELEASE_DIR/ScanBhav-macOS-v${VERSION}.dmg"
  rm -f "$DMG"
  hdiutil create -volname "Scan Bhav" -srcfolder "$RELEASE_DIR/ScanBhav.app" -ov -format UDZO "$DMG"

  ZIP="$RELEASE_DIR/ScanBhav-macOS-v${VERSION}.zip"
  rm -f "$ZIP"
  (cd "$RELEASE_DIR" && zip -qr "$(basename "$ZIP")" ScanBhav.app)

  echo "[release] 5/5 — done"
  echo "  App: $RELEASE_DIR/ScanBhav.app"
  echo "  DMG: $DMG"
  echo "  ZIP: $ZIP"
else
  echo "[release] 4/5 — folder bundle + zip"
  BUNDLE="$ROOT/dist/ScanBhav"
  if [[ ! -d "$BUNDLE" ]]; then
    echo "[release] ERROR: expected $BUNDLE — PyInstaller may have failed"
    exit 1
  fi
  rm -rf "$RELEASE_DIR/ScanBhav"
  cp -R "$BUNDLE" "$RELEASE_DIR/ScanBhav"
  ZIP="$RELEASE_DIR/ScanBhav-$(uname -s)-v${VERSION}.zip"
  rm -f "$ZIP"
  (cd "$RELEASE_DIR" && zip -qr "$(basename "$ZIP")" ScanBhav)
  echo "[release] 5/5 — done"
  echo "  Folder: $RELEASE_DIR/ScanBhav"
  echo "  ZIP: $ZIP"
fi

echo "[release] First launch stores data in ~/Library/Application Support/ScanBhav (macOS)"
