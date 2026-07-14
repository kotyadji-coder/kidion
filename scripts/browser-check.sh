#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://chat.kidion.ru}"
PLAYWRIGHT_VERSION="${PLAYWRIGHT_VERSION:-1.61.1}"

if [ -f package.json ] && npm run | grep -q "test:e2e"; then
  BASE_URL="$BASE_URL" npm run test:e2e
  exit 0
fi

if [ -f package.json ] && [ -d tests/e2e ]; then
  BASE_URL="$BASE_URL" npx playwright test
  exit 0
fi

if [ -d tests/e2e ]; then
  npx --yes "@playwright/test@${PLAYWRIGHT_VERSION}" install chromium
  BASE_URL="$BASE_URL" npx --yes "@playwright/test@${PLAYWRIGHT_VERSION}" test tests/e2e --browser chromium
  exit 0
fi

echo "No browser checks configured yet."
echo "For web projects, add Playwright tests in tests/e2e."
exit 2
