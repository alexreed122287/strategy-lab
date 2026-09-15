#!/usr/bin/env python3
"""Shape tests for the JASON entry mailer. Run: python3 scripts/notify_jason_test.py

Why this mail exists. JASON's forward ledger opened 09/12/2026 and filled AMAT
and CAT on the 09-14 bar off real chain quotes, and nothing mailed any of it -
the same gap notify_robert.py closed for ROBERT four days earlier. The page
showed it; no inbox did.

What it mails is the ledger's `queued` list, which is what the book will
actually enter at the next open after the one-per-name and 5-bar rules. Unlike
ROBERT there is no signal blob to decorate from: JASON's queued rows already
carry every gate reading, so the ledger is the single authority and the mail
cannot disagree with it about what a buy is.

These tests assert SHAPE, not today's tickers - a fixture below naming CSCO is
a fixture, and the suite must keep passing on the day CSCO is not queued.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_jason as nj  # noqa: E402

CHECKS = 0
FAILED = 0


def check(cond, msg):
    global CHECKS, FAILED
    CHECKS += 1
    if not cond:
        FAILED += 1
        print("FAIL: " + msg)


LEDGER = {
    "arm": "JASON", "started": "2026-09-12", "last_as_of": "2026-09-14",
    "queued": [{"t": "CSCO", "signal_date": "2026-09-14", "close": 110.06,
                "vap50": 114.2324, "atr14": 2.1435, "threshold": 111.0171,
                "rs252": 0.4689, "iv_proxy": 0.3141}],
    "open": [{"t": "AMAT", "signal_date": "2026-09-11", "entry_date": "2026-09-14"}],
    "closed": [
        {"t": "OLD", "exit_date": "2026-09-11", "reason": "VAP", "bars": 4,
         "net": 0.031, "opt": {"ret": 0.12, "pnl": 900.0, "basis": "CHAIN"}},
        {"t": "NOW", "exit_date": "2026-09-14", "reason": "VAP", "bars": 2,
         "net": 0.018, "opt": {"ret": 0.07, "pnl": 510.0, "basis": "MODEL"}},
    ],
}

# ---- collect: the ledger is the only authority ----------------------------
as_of, entries, exits = nj.collect(LEDGER)
check(as_of == "2026-09-14", "collect: as_of comes from the ledger")
check([e["t"] for e in entries] == ["CSCO"],
      "collect: entries are exactly the queued rows")
check(entries[0]["close"] == 110.06 and entries[0]["threshold"] == 111.0171
      and entries[0]["rs252"] == 0.4689 and entries[0]["iv_proxy"] == 0.3141,
      "collect: queued row carries its own gate readings")
check([x["t"] for x in exits] == ["NOW"],
      "collect: exits are only rows closed ON the bar, not older ones")

e0, x0 = nj.collect({"last_as_of": "2026-09-14"})[1:]
check(e0 == [] and x0 == [],
      "collect: a ledger with no queued/closed keys yields nothing, does not raise")
check(nj.collect({})[0] == "", "collect: empty ledger yields an empty as_of")

# ---- weekday roll ---------------------------------------------------------
check(nj.nb_next_session("2026-09-10") == "2026-09-11", "next_session: Thu -> Fri")
check(nj.nb_next_session("2026-09-11") == "2026-09-14", "next_session: Fri -> Mon")

# ---- formatting: a level must not wear a sign -----------------------------
check(nj._lvl(0.3141) == "31.4%", "_lvl: IV proxy renders unsigned")
check(nj._pct(0.4689) == "+46.9%", "_pct: RS252 keeps its sign")
check(nj._lvl(None) == "n/a" and nj._pct(None) == "n/a" and nj._num(None) == "n/a",
      "formatters: None renders as n/a rather than raising")

# ---- compose --------------------------------------------------------------
subject, body = nj.compose(as_of, entries, exits, "https://example.com/jason.html")
check(subject.startswith("JASON"), "compose: subject is branded")
check("CSCO" in subject and "2026-09-15" in subject,
      "compose: subject names the ticker and the open it is for")
for needle in ("PAPER ONLY", "no capital", "Nothing in this mail is an order",
               "09:30 ET", "VAP(50)", "no gap-skip rule", "no stop-loss",
               "ENTRIES for the next open", "EXITS at the 2026-09-14 close",
               "https://example.com/jason.html"):
    check(needle in body, "compose: body carries '%s'" % needle)
check("110.06" in body and "31.4%" in body and "+46.9%" in body,
      "compose: entry line prints the readings the ledger gave it")
check("NOW" in body and "OLD" not in body,
      "compose: only the bar's own exits reach the body")

s2, b2 = nj.compose(as_of, [], exits, None)
check(s2.startswith("JASON: 1 exit"), "compose: exit-only mail is subjected as exits")
check("No entries queued for the next open." in b2,
      "compose: exit-only mail says so rather than printing an empty section")
check("Page:" not in b2, "compose: no url, no dangling Page line")

# ---- dedupe ---------------------------------------------------------------
h1 = nj.payload_hash(as_of, entries, exits)
check(h1 == nj.payload_hash(as_of, entries, exits), "payload_hash: stable")
check(h1 != nj.payload_hash(as_of, [], exits),
      "payload_hash: changes when the queued set changes")
check(h1 != nj.payload_hash("2026-09-15", entries, exits),
      "payload_hash: changes when the bar changes")

print("notify_jason_test: %d checks, %d failed" % (CHECKS, FAILED))
sys.exit(1 if FAILED else 0)
