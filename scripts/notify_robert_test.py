#!/usr/bin/env python3
"""Shape tests for the ROBERT entry mailer. Run: python3 scripts/notify_robert_test.py

Why this mail exists at all. Until 2026-09-11 nothing mailed a ROBERT signal:
notify_buys.py reads six blobs from index.html and never ROBSIG, so the ATI
TAKE on the 09-10 bar - the first live entry since the entry-snap workflow was
re-enabled - reached nobody. The page showed it; no inbox did.

What it mails is the shadow ledger's `queued` list, not the TAKE chips: queued
is what the book will actually enter at the next open after the one-per-name
and busy rules, so the mail and the ledger cannot disagree about what a "buy"
is. ROBSIG only decorates each row with the gate readings.

These tests assert shape, not today's tickers.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_robert as nr  # noqa: E402

CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        print("FAIL -", msg)
        sys.exit(1)
    print("PASS -", msg)


SPAN = '<span style="font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid #009E73;color:#009E73;white-space:nowrap">'
GRAY = '<span style="font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid #8d8c85;color:#8d8c85;white-space:nowrap">'

# Exactly what robert_scan.py splices: one line, no whitespace between tags.
COMPACT = (
    '<!-- ROBSIG:START -->'
    '<p class="small">Scan as of the 2026-09-10 bar - 2 raw signal(s), 1 pass all gates. '
    'Entry is the NEXT open, ~09:45 ET limit at mid; skip if the open is already above the prior SMA5.</p>'
    '<div class="tablewrap"><table>'
    '<tr><th>Ticker</th><th>RSI(2)</th><th>RS252 vs SPY</th><th>IV proxy</th><th>Earnings</th><th>Verdict</th></tr>'
    '<tr><td><b>ATI</b></td><td>9.42</td><td>+143%</td><td>37%</td><td>clear</td>'
    '<td>' + SPAN + 'TAKE - verify chain at 09:45 (OI&ge;10, spread&le;25%)</span></td></tr>'
    '<tr><td><b>GE</b></td><td>8.42</td><td>-3%</td><td>29%</td><td>2026-09-15</td>'
    '<td>' + GRAY + 'signal, gated out: RS gate</span></td></tr>'
    '</table></div>'
    '<!-- ROBSIG:END -->'
)

# The same block after js-beautify (robert.html was reformatted 2026-09-11):
# tags split across lines, the verdict text itself wrapped mid-sentence.
WRAPPED = """
      <!-- ROBSIG:START -->
      <p class="small">Scan as of the 2026-09-10 bar - 2 raw signal(s), 1 pass all gates. Entry is the NEXT open, ~09:45
        ET limit at mid; skip if the open is already above the prior SMA5.</p>
      <div class="tablewrap">
        <table>
          <tr>
            <th>Ticker</th>
            <th>RSI(2)</th>
            <th>RS252 vs SPY</th>
            <th>IV proxy</th>
            <th>Earnings</th>
            <th>Verdict</th>
          </tr>
          <tr>
            <td><b>ATI</b></td>
            <td>9.42</td>
            <td>+143%</td>
            <td>37%</td>
            <td>clear</td>
            <td><span
                style="font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid #009E73;color:#009E73;white-space:nowrap">TAKE
                - verify chain at 09:45 (OI&ge;10, spread&le;25%)</span></td>
          </tr>
          <tr>
            <td><b>GE</b></td>
            <td>8.42</td>
            <td>-3%</td>
            <td>29%</td>
            <td>2026-09-15</td>
            <td><span
                style="font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid #8d8c85;color:#8d8c85;white-space:nowrap">signal,
                gated out: RS gate</span></td>
          </tr>
        </table>
      </div>
      <!-- ROBSIG:END -->
"""

LEDGER = {
    "last_as_of": "2026-09-10",
    "queued": [{"t": "ATI", "signal_date": "2026-09-10", "rsi2": 9.42}],
    "open": [],
    "closed": [
        {"t": "LRCX", "entry_date": "2026-09-03", "exit_date": "2026-09-10",
         "entry_px": 283.73, "exit_px": 307.65, "bars": 1, "reason": "SMA5",
         "net": 0.08387,
         "opt": {"expiry": "2026-10-16", "strike": 240.0, "basis": "MODEL",
                 "prem_paid": 51.2264, "exit_recv": 69.5017, "contracts": 2,
                 "ret": 0.35674, "pnl": 3654.92}},
        {"t": "OLD", "entry_date": "2026-09-01", "exit_date": "2026-09-04",
         "entry_px": 10.0, "exit_px": 10.5, "bars": 3, "reason": "TIME",
         "net": 0.05, "opt": {"basis": "MODEL", "ret": 0.1, "pnl": 100.0}},
    ],
}

# --- ROBSIG parsing: both the producer's compact form and the beautified one
for label, html in (("compact", COMPACT), ("wrapped", WRAPPED)):
    sig = nr.parse_robsig(html)
    check(sig["as_of"] == "2026-09-10", "%s: as_of read from the scan header" % label)
    check(set(sig["rows"]) == {"ATI", "GE"}, "%s: both tickers parsed" % label)
    a = sig["rows"]["ATI"]
    check(a["rsi2"] == "9.42" and a["rs"] == "+143%" and a["iv"] == "37%" and a["earn"] == "clear",
          "%s: ATI gate readings parsed" % label)
    check(a["take"] is True, "%s: ATI verdict is TAKE" % label)
    g = sig["rows"]["GE"]
    check(g["take"] is False and "RS gate" in g["verdict"], "%s: GE verdict is gated out, whitespace normalised" % label)
    check(g["earn"] == "2026-09-15", "%s: GE earnings date parsed" % label)

check(nr.parse_robsig("<p>no markers here</p>") == {"as_of": "", "rows": {}},
      "a page without ROBSIG markers parses to empty, not an exception")

# --- collect: queued rows decorated from ROBSIG; exits are closed rows on the bar
as_of, entries, exits = nr.collect(COMPACT, LEDGER)
check(as_of == "2026-09-10", "collect: as_of comes from the ledger")
check([e["t"] for e in entries] == ["ATI"], "collect: entries are exactly the queued rows")
check(entries[0]["rs"] == "+143%" and entries[0]["iv"] == "37%", "collect: queued row carries the ROBSIG readings")
check([x["t"] for x in exits] == ["LRCX"], "collect: exits are only the rows closed ON the bar, not older ones")

# A queued name missing from ROBSIG still mails - the ledger is the authority.
_led = dict(LEDGER, queued=[{"t": "ZZZ", "signal_date": "2026-09-10", "rsi2": 3.1}])
_, e2, _ = nr.collect(COMPACT, _led)
check(e2[0]["t"] == "ZZZ" and e2[0]["rsi2"] == "3.10" and e2[0]["rs"] == "n/a",
      "collect: a queued name absent from ROBSIG is kept, readings fall back to n/a")

# Nothing queued and nothing closed on the bar -> nothing to send.
_, e3, x3 = nr.collect(COMPACT, dict(LEDGER, queued=[], closed=[]))
check(e3 == [] and x3 == [], "collect: empty ledger yields no entries and no exits")

# --- next session: weekday roll, holidays deliberately not modelled
check(nr.next_session("2026-09-10") == "2026-09-11", "next_session: Thu -> Fri")
check(nr.next_session("2026-09-11") == "2026-09-14", "next_session: Fri -> Mon")

# --- compose
subject, body = nr.compose(as_of, entries, exits, "https://example.test/robert.html")
check(subject.startswith("ROBERT"), "compose: subject is branded")
check("ATI" in subject and "2026-09-11" in subject, "compose: subject names the ticker and the open it is for")
for needle in ("next open", "09:45 ET", "SMA5", "OI", "spread", "PAPER", "https://example.test/robert.html"):
    check(needle in body, "compose: body carries '%s'" % needle)
check("ATI" in body and "+143%" in body and "37%" in body, "compose: entry row prints its gate readings")
check("LRCX" in body and "SMA5" in body and "+35.7%" in body and "MODEL" in body,
      "compose: exit row prints reason, option return and pricing basis")
check("Session 2026-09-10" not in body, "compose: the dedupe stamp is main()'s job, not compose's")

# Exits only, no entries: still a mail, subject says so.
s2, b2 = nr.compose(as_of, [], exits, None)
check("exit" in s2.lower() and "LRCX" in s2, "compose: exits-only mail has an exits subject")

# --- dedupe key: content, not clock
k1 = nr.payload_hash(as_of, entries, exits)
k2 = nr.payload_hash(as_of, entries, exits)
k3 = nr.payload_hash(as_of, [], exits)
check(k1 == k2 and k1 != k3 and len(k1) == 64, "payload_hash: stable for equal payloads, differs when entries differ")

print("all %d ROBERT mailer tests passed" % CHECKS)
