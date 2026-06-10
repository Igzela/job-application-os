#!/usr/bin/env bash
# Launch Chrome with remote debugging for BOSS Zhipin adapter.
# Uses a dedicated profile so login state persists across runs.
# First run: scan QR code to log into BOSS Zhipin in the browser window.
# If a slider/captcha appears, solve it manually (human-in-the-loop).
set -euo pipefail
PORT="${1:-9222}"
PROFILE="$HOME/.jobos-chrome-profile"
CHROME="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium-browser || command -v chromium)"
if [ -z "$CHROME" ]; then
  echo "Error: Chrome/Chromium not found. Install google-chrome or chromium." >&2
  exit 1
fi
mkdir -p "$PROFILE"
echo "Launching Chrome (debug port $PORT, profile=$PROFILE)"
echo "=> Log into BOSS Zhipin in the browser window (QR scan)."
echo "=> If a slider/captcha appears, solve it manually."
echo "=> Then run: node read-boss.mjs \"AIGC\" 100010000 $PORT"
exec "$CHROME" --remote-debugging-port="$PORT" --user-data-dir="$PROFILE" "https://www.zhipin.com"
