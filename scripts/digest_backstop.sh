#!/usr/bin/env bash
# Digest backstop - runs the ranked digest ONLY when a build actually landed
# today's session. Invoked by com.alex.strategylab.digest.
#
# WHY THIS EXISTS. The launchd job used to call notify_buys.py directly on a
# clock at 16:00 CT. That is one minute before the Mac build finishes and half
# an hour before the cloud backstop, so on any day the build was late, failed,
# or did not run, the job read whatever index.html was on disk - the PREVIOUS
# session - and the only thing standing between that and a "buy at the market
# open" email to three recipients was a dedupe state file. A clock is not a
# dependency. This wrapper makes the dependency explicit: no build for today's
# session, no mail.
#
# Three gates, all of which must pass:
#   1. the page's BOOKSIG.as_of is the last completed session
#   2. the build log records a completed run today
#   3. notify_buys' own freshness gate and content-hash idempotency key
#      (it re-checks 1 independently, and suppresses an unchanged payload)
#
# Exits 0 when it declines - declining is a normal outcome, not a failure, and
# a non-zero exit would only produce launchd noise.
set -uo pipefail

REPO="$HOME/repos/strategy-lab-site"
PAGE="$REPO/index.html"
LOG="$REPO/.daily_build.log"
cd "$REPO" || { echo "digest-backstop: no repo at $REPO"; exit 0; }

say() { echo "[digest-backstop $(date '+%F %T')] $*"; }

# Gate 1 - the page must hold the last completed session. Reuses the mailer's
# own helper so the two can never disagree about what "today's session" means.
read -r EXPECTED PAGE_ASOF <<<"$(python3 - "$PAGE" <<'PY'
import importlib.util, json, re, sys
spec = importlib.util.spec_from_file_location("nb", "scripts/notify_buys.py")
nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)
try:
    h = open(sys.argv[1]).read()
    a = json.loads(re.search(r"const BOOKSIG = (.*?);\n", h, re.S).group(1)).get("as_of") or "none"
except Exception:
    a = "unreadable"
print(nb.last_completed_session(), a)
PY
)"

if [ "$PAGE_ASOF" != "$EXPECTED" ]; then
  say "declining: page holds session $PAGE_ASOF, last completed session is $EXPECTED."
  say "declining: no build has landed today's session - sending would mail a stale page."
  exit 0
fi

# Gate 2 - a build must have actually completed today. The page could hold the
# right date from a partial run that died before publishing.
TODAY="$(date '+%F')"
if ! grep -q "=== daily build done $TODAY" "$LOG" 2>/dev/null; then
  say "declining: no 'daily build done $TODAY' marker in $LOG."
  say "declining: the page looks current but no local build completed today."
  exit 0
fi

say "both gates passed (session $EXPECTED, build completed today) - running digest."
# Gate 3 lives inside notify_buys: it re-derives the expected session itself and
# suppresses on the content hash, so a digest the build already chained will be
# recognised as an identical payload and skipped rather than duplicated.
python3 "$REPO/scripts/notify_buys.py" --page "$PAGE" --simple
say "done (rc=$?)"
exit 0
