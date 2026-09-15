#!/usr/bin/env python3
"""Shape tests for the combined daily mailer. Run: python3 scripts/notify_daily_test.py

Why one mail. Until 2026-09-15 the build sent three to (by default) the same
list - notify_buys' alert, notify_robert's, notify_jason's - three subjects a
morning for one decision. notify_daily.py merges them into one sectioned mail
and the three per-book mailers stay runnable standalone.

What these tests pin is the part a combined mail can get WRONG in ways the
reader cannot detect:
  * a section that failed must SAY so - silence reads as "no signals"
  * a stale section must be suppressed and named, never printed beside fresh
    rows as though it were today's
  * one bad book must never suppress the others
  * the subject must not advertise rows a suppressed section did not deliver

Shape, not today's tickers.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_daily as nd  # noqa: E402

CHECKS = 0
FAILED = 0


def check(cond, msg):
    global CHECKS, FAILED
    CHECKS += 1
    if not cond:
        FAILED += 1
        print("FAIL: " + msg)


# ---- _sect: every section states its own verdict --------------------------
s = nd._sect("ROBERT - RSI(2) DITM calls", "OK", "two entries\n")
check("ROBERT - RSI(2) DITM calls  [OK]" in s, "_sect: banner carries title and state")
check("two entries" in s, "_sect: body is included verbatim")
check(nd._sect("X", "NOTHING", "").count("[NOTHING]") == 1,
      "_sect: an empty body still renders a stated section")

# ---- build: subject and header ---------------------------------------------
LIVE = [("RSI2 / SHARED BOOKS", "OK", 3, "rsi2 body", "k1"),
        ("ROBERT - RSI(2) DITM calls", "OK", 2, "robert body", "k2"),
        ("JASON - VAP dislocation reversion", "OK", 1, "jason body", "k3")]
subj, body, key = nd.build(LIVE, "2026-09-14")
check(subj.startswith("Strategy Lab 2026-09-14"), "build: subject leads with the session")
check("RSI2 3" in subj and "ROBERT 2" in subj and "JASON 1" in subj,
      "build: subject counts every live section")
check("[check:" not in subj, "build: all-OK subject carries no check flag")
for needle in ("rsi2 body", "robert body", "jason body"):
    check(needle in body, "build: body carries '%s'" % needle)
check("Sections: RSI2 OK, ROBERT OK, JASON OK" in body,
      "build: header states each section's verdict up front")
check("Nothing in this mail places an order." in body, "build: posture line present")

# ---- build: a failed section is named, not hidden --------------------------
MIXED = [("RSI2 / SHARED BOOKS", "OK", 3, "rsi2 body", "k1"),
         ("ROBERT - RSI(2) DITM calls", "STALE", 0, "Suppressed: ledger holds bar X.", ""),
         ("JASON - VAP dislocation reversion", "FAILED", 0, "could not be built: Boom", "")]
subj2, body2, _ = nd.build(MIXED, "2026-09-14")
check("RSI2 3" in subj2, "build: live section still summarised alongside broken ones")
check("ROBERT" not in subj2.split("[check:")[0],
      "build: a suppressed section is NOT advertised as delivering rows")
check("[check:" in subj2 and "ROBERT" in subj2 and "JASON" in subj2,
      "build: subject flags both the stale and the failed section")
check("ROBERT STALE" in body2 and "JASON FAILED" in body2,
      "build: header states the broken verdicts")
check("could not be built: Boom" in body2,
      "build: the failure reason reaches the reader")

# ---- build: nothing live ---------------------------------------------------
NONE = [("RSI2 / SHARED BOOKS", "NOTHING", 0, "No new buys.", ""),
        ("ROBERT - RSI(2) DITM calls", "NOTHING", 0, "No entries.", ""),
        ("JASON - VAP dislocation reversion", "NOTHING", 0, "No entries.", "")]
subj3, _, _ = nd.build(NONE, "2026-09-14")
check("no signals" in subj3, "build: an empty day says so in the subject")

# ---- dedupe key ------------------------------------------------------------
k_a = nd.build(LIVE, "2026-09-14")[2]
check(k_a == nd.build(LIVE, "2026-09-14")[2], "key: stable for identical input")
check(k_a != nd.build(LIVE, "2026-09-15")[2], "key: changes with the session")
check(k_a != nd.build(MIXED, "2026-09-14")[2], "key: changes when a section changes")

# ---- section helpers: freshness and emptiness ------------------------------
tmp = tempfile.mkdtemp()
led = os.path.join(tmp, "jason.json")

json.dump({"last_as_of": "2026-09-14", "queued": [
    {"t": "ZZZ", "signal_date": "2026-09-14", "close": 10.0, "vap50": 12.0,
     "atr14": 0.5, "threshold": 11.0, "rs252": 0.5, "iv_proxy": 0.3}],
    "closed": []}, open(led, "w"))
state, count, body4, key4 = nd.jason_section(led, "2026-09-14", False, None)
check((state, count) == ("OK", 1), "jason_section: fresh ledger with a queued row is OK")
check("ZZZ" in body4 and key4, "jason_section: body names the row and yields a key")

state, count, body5, key5 = nd.jason_section(led, "2026-09-15", False, None)
check(state == "STALE" and count == 0, "jason_section: a bar behind the session is STALE")
check("Suppressed" in body5 and "2026-09-14" in body5 and "2026-09-15" in body5,
      "jason_section: the suppression names BOTH bars so the gap is visible")
check("ZZZ" not in body5, "jason_section: a stale section prints no rows")
check(key5 == "", "jason_section: a suppressed section contributes no dedupe key")

state, count, _, _ = nd.jason_section(led, "2026-09-15", True, None)
check(state == "OK" and count == 1, "jason_section: --allow-stale overrides the gate")

json.dump({"last_as_of": "2026-09-14", "queued": [], "closed": []}, open(led, "w"))
state, count, body6, _ = nd.jason_section(led, "2026-09-14", False, None)
check(state == "NOTHING" and count == 0, "jason_section: empty ledger is NOTHING, not STALE")
check("No entries queued" in body6, "jason_section: an empty section still says what it checked")

print("notify_daily_test: %d checks, %d failed" % (CHECKS, FAILED))
sys.exit(1 if FAILED else 0)
