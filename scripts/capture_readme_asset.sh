#!/usr/bin/env bash
# Regenerate the README hero image (docs/assets/report-card.png) from the
# messy CJA example report. Illustrative only — not part of the
# examples-drift gate. Rerun after a visual-contract change and commit
# the result. Requires Google Chrome (macOS path below).
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=1200,850 \
  --screenshot="$PWD/docs/assets/report-card.png" \
  "file://$PWD/examples/grade-cja-messy.html"
