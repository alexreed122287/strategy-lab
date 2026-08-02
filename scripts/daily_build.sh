#!/usr/bin/env bash
# Strategy Lab daily build — run weekdays after the close (launchd template:
# scripts/com.alex.strategylab.daily.plist fires 15:30 CT = 4:30 PM ET).
#
# Sections marked FILL IN call YOUR local generators (agentic-cron /
# market-data-brain). Everything else is ready to run. The script is
# fail-closed: if any step or validation fails, nothing is pushed and the
# previous build keeps serving.
set -euo pipefail

REPO="$HOME/repos/strategy-lab"        # FILL IN: local clone of alexreed122287/strategy-lab
WORK="$HOME/repos/agentic-cron"        # FILL IN: where your generators + data caches live
TMP="$(mktemp -d)"
LOG="$REPO/.daily_build.log"
trap 'rm -rf "$TMP"' EXIT
exec >>"$LOG" 2>&1
echo "=== daily build start $(date '+%F %T') ==="

cd "$WORK"

# 1) Refresh EOD data caches (Tradier-native — single source, program law).
# FILL IN: your existing refresh entrypoint, e.g.:
# python3 refresh_histories.py

# 2) Regenerate the dashboard blobs into index.html
#    (SCAN / SIGNALS / BASKETS / DAILY / REGIME — the script that produced the
#    2026-08-01 build; point its output at the repo copy).
# FILL IN, e.g.:
# python3 build_dashboard.py --out "$REPO/index.html"

# 3) Emit the TRACK inputs:
#    closes.json  = {"SYM": [["YYYY-MM-DD", close], ...]} ascending, ~60 bars,
#                   for every scan ticker + the four books' universes + holdings.
#    earnings.json = {"SYM": "YYYY-MM-DD"} next confirmed report (optional).
# FILL IN, e.g.:
# python3 dump_closes.py --closes "$TMP/closes.json" --earnings "$TMP/earnings.json"

# 4) Splice the TRACK indicator snapshot into the page (ready to run).
python3 "$REPO/scripts/track_snapshot_reference.py" "$TMP/closes.json" \
  --earnings "$TMP/earnings.json" \
  --splice "$REPO/index.html" \
  --source "tradier local build $(date +%F)"

# 5) Validate before publishing: every embedded blob must parse. Fail-closed.
python3 - "$REPO/index.html" <<'PYEOF'
import json, re, sys
html = open(sys.argv[1]).read()
for n in ["SCAN","BASKETS","SIGNALS","REGIME","DAILY","CALLS","TF","METHOD","BOOKS","TRACK"]:
    m = re.search(r'const %s = (.*?);\n' % n, html, re.S)
    assert m, "missing blob: " + n
    json.loads(m.group(1))
track = json.loads(re.search(r'const TRACK = (.*?);\n', html, re.S).group(1))
assert track and track.get("tickers"), "TRACK is empty - refusing to publish"
print("validation OK:", len(track["tickers"]), "tickers as of", track["as_of"])
PYEOF

# 6) Publish (GitHub Pages serves main, so push = deploy).
cd "$REPO"
git add index.html
if git diff --cached --quiet; then
  echo "no changes to publish"
else
  git commit -m "daily build $(date +%F)"
  for delay in 0 2 4 8 16; do
    sleep "$delay"
    git push origin main && break
  done
fi
echo "=== daily build done $(date '+%F %T') ==="
