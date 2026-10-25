#!/usr/bin/env bash
# Install Playwright once, then run the feature scripts.
# Usage: ./scripts/playwright.sh
#        PLAYWRIGHT_LIVE=1 ./scripts/playwright.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules/@playwright/test ]]; then
  npm install
fi
npx playwright install chromium
npm run test:e2e
