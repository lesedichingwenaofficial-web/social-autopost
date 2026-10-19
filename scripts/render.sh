#!/usr/bin/env bash
# Render HTML slides to 1080x1350 PNGs with headless Chrome.
#   scripts/render.sh drafts/my-post/*.html     -> writes a .png next to each .html
set -euo pipefail
CHROME=$(command -v google-chrome || command -v chromium || command -v chromium-browser)
for html in "$@"; do
  png="${html%.html}.png"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1080,1350 --virtual-time-budget=5000 \
    --screenshot="$(realpath -m "$png")" "file://$(realpath "$html")" 2>/dev/null
  echo "$png"
done
