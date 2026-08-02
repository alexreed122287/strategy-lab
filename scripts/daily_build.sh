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
  --out "$TMP/bars.json" --days 400 --ohlcv
# earnings.json (z-score force-exit + no-entry dates) - sourced from the local
# market-data-brain earnings cache (x37 fetcher format). Override the location
# with SL_EARNINGS_DIR; a missing dir just disables earnings flags (fail-quiet).
EARN_DIR="${SL_EARNINGS_DIR:-}"
if [ -z "$EARN_DIR" ]; then
  for d in "$HOME/Projects/market-data-brain/earnings" "$HOME/repos/market-data-brain/earnings"; do
    [ -d "$d" ] && EARN_DIR="$d" && break
  done
fi
python3 "$REPO/scripts/next_earnings.py" --dir "$EARN_DIR" --out "$TMP/earnings.json"

# 4) Splice the TRACK indicator snapshot into the page (ready to run).
python3 "$REPO/scripts/track_snapshot_reference.py" "$TMP/bars.json" \
  --earnings "$TMP/earnings.json" \
  --splice "$REPO/index.html" \
  --source "tradier local build $(date +%F)"

# 4b) Evaluate the strategy books' entry rules -> BOOKSIG (Gap Widen x2 +
#     Z-Score paper; BB dropped 2026-08-01 per its pre-registered kill gate).
python3 "$REPO/scripts/scan_book_signals.py" --bars "$TMP/bars.json" \
  --page "$REPO/index.html" --earnings "$TMP/earnings.json" --splice

# 4c) Shadow forward book - the automated skip-free paper ledger (fills queued
#     MOO entries, applies exit rules, logs today's qualifying TAKEs).
python3 "$REPO/scripts/shadow_book.py" --bars "$TMP/bars.json" \
  --page "$REPO/index.html" --earnings "$TMP/earnings.json" \
  --ledger "$REPO/data/shadow_book.json" --splice

# 4d) Pipeline health stamp shown in the page header.
python3 - "$REPO/index.html" "$TMP/bars.json" "$TMP/earnings.json" <<'PYEOF'
import json, re, sys, datetime
page_path, bars_path, earn_path = sys.argv[1], sys.argv[2], sys.argv[3]
html = open(page_path).read()
bars = json.load(open(bars_path))
earn = json.load(open(earn_path))
scan = json.loads(re.search(r"const SCAN = (.*?);\n", html, re.S).group(1))
booksig = json.loads(re.search(r"const BOOKSIG = (.*?);\n", html, re.S).group(1))
shadow = json.loads(re.search(r"const SHADOW = (.*?);\n", html, re.S).group(1))
uni = len(json.loads(re.search(r"const TRACK = (.*?);\n", html, re.S).group(1)).get("tickers") or {}) or len(bars)
h = {"build": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
     "bars_ok": len(bars), "universe": max(uni, len(bars)),
     "earnings": len(earn), "booksig_rows": len(booksig.get("rows") or []),
     "shadow_open": sum(1 for p in shadow.get("open") or [] if p.get("state") == "open"),
     "shadow_closed": shadow.get("closed_total") or 0}
line = "const HEALTH = " + json.dumps(h, separators=(",", ":")) + ";"
html2, n = re.subn(r"const HEALTH = .*?;\n", lambda _m: line + "\n", html, count=1, flags=re.S)
assert n == 1, "no HEALTH line"
open(page_path, "w").write(html2)
print("health stamped:", h)
PYEOF

# 5) Validate before publishing: every embedded blob must parse. Fail-closed.
python3 - "$REPO/index.html" <<'PYEOF'
import json, re, sys
html = open(sys.argv[1]).read()
for n in ["SCAN","BASKETS","SIGNALS","REGIME","DAILY","CALLS","TF","METHOD","BOOKS","TRACK","BOOKSIG","NOTIFY","SHADOW","HEALTH"]:
    m = re.search(r'const %s = (.*?);\n' % n, html, re.S)
    assert m, "missing blob: " + n
    json.loads(m.group(1))
track = json.loads(re.search(r'const TRACK = (.*?);\n', html, re.S).group(1))
assert track and track.get("tickers"), "TRACK is empty - refusing to publish"
print("validation OK:", len(track["tickers"]), "tickers as of", track["as_of"])
PYEOF

# 6) Publish (GitHub Pages serves main, so push = deploy). The shadow ledger
#    is committed too - the forward record must survive machines.
cd "$REPO"
git add index.html data/shadow_book.json
if git diff --cached --quiet; then
  echo "no changes to publish"
else
  git commit -m "daily build $(date +%F)"
  for delay in 0 2 4 8 16; do
    sleep "$delay"
    git push origin main && break
  done
  # 7) Notify (email + ntfy push + optional SMS) - configured via
  #    ~/.strategy_lab_notify.json, see docs/notifications.md. First harvest
  #    any self-service signups from the page's card. Never fails the build.
  python3 "$REPO/scripts/notify_signups.py" || echo "signup harvest failed (non-fatal)"
  python3 "$REPO/scripts/notify_buys.py" --page "$REPO/index.html" \
    || echo "notify step failed (non-fatal)"
fi
echo "=== daily build done $(date '+%F %T') ==="
