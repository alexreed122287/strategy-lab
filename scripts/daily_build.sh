#!/usr/bin/env bash
# Strategy Lab daily build — run weekdays after the close (launchd template:
# scripts/com.alex.strategylab.daily.plist fires 15:30 CT = 4:30 PM ET).
#
# Sections marked FILL IN call YOUR local generators (agentic-cron /
# market-data-brain). Everything else is ready to run. The script is
# fail-closed: if any step or validation fails, nothing is pushed and the
# previous build keeps serving.
set -euo pipefail

REPO="$HOME/repos/strategy-lab-site"   # local clone of alexreed122287/strategy-lab (per publish.sh)
WORK="$HOME/repos/strategy-lab-dashboard"  # where the builder + caches live
TMP="$(mktemp -d)"
LOG="$REPO/.daily_build.log"
trap 'rm -rf "$TMP"' EXIT
exec >>"$LOG" 2>&1
echo "=== daily build start $(date '+%F %T') ==="

cd "$WORK"

# 1-2) Refresh data + regenerate the dashboard blobs — CONFIG-DRIVEN, no script
#    edit needed. Put your one-line build command (data refresh + blob rebuild,
#    ending with index.html written into $REPO) in EITHER:
#      the SL_BLOB_BUILD_CMD environment variable, or
#      the file ~/.strategy_lab_build_cmd
#    Example (write once, from your local research session):
#      echo 'python3 build_dashboard.py --out ~/repos/strategy-lab/index.html' \
#        > ~/.strategy_lab_build_cmd
#    Until configured, the build runs in TRACK-ONLY mode: sell flags and the
#    indicator snapshot refresh daily, while scan/signal blobs stay at their
#    last build (the page's stamps show exactly this).
BUILD_CMD="${SL_BLOB_BUILD_CMD:-}"
[ -z "$BUILD_CMD" ] && [ -f "$HOME/.strategy_lab_build_cmd" ] && \
  BUILD_CMD="$(cat "$HOME/.strategy_lab_build_cmd")"
if [ -n "$BUILD_CMD" ]; then
  echo "blob rebuild: $BUILD_CMD"
  bash -c "$BUILD_CMD"
else
  echo "blob rebuild not configured - TRACK-only build (see comments above)"
fi

# 3) Emit the TRACK inputs - READY TO RUN: closes fetched straight from
#    Tradier for every scan ticker + book-universe symbol parsed off the page.
#    Token: TRADIER_TOKEN env var or ~/.tradier_token file. ~6 min for ~700 names.
python3 "$REPO/scripts/dump_closes.py" --index "$REPO/index.html" \
  --out "$TMP/closes.json" --days 90
# earnings.json (z-score force-exit dates) - OPTIONAL FILL IN if you have a
# confirmed-earnings feed; empty file just disables earnings flags:
[ -f "$TMP/earnings.json" ] || echo '{}' > "$TMP/earnings.json"

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
