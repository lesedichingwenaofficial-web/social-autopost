#!/usr/bin/env bash
# Render HTML slides to 1080x1350 PNGs with headless Chrome (SIZE=1080,1920 for Stories).
#   scripts/render.sh drafts/my-post/*.html     -> writes a .png next to each .html
# Finds Chrome/Chromium on PATH, or a Playwright-installed Chromium (cloud sessions).
# Override with CHROME=/path/to/chrome.
set -euo pipefail
CHROME=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser \
  || find /opt/pw-browsers ~/.cache/ms-playwright -type f \( -name chrome -o -name headless_shell \) 2>/dev/null | head -1 || true)}
[ -n "$CHROME" ] || { echo "No Chrome/Chromium found - set CHROME=/path/to/chrome" >&2; exit 1; }
for html in "$@"; do
  png="${html%.html}.png"
  "$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=${SIZE:-1080,1350} --virtual-time-budget=5000 \
    --screenshot="$(realpath -m "$png")" "file://$(realpath "$html")" 2>/dev/null
  echo "$png"
done
