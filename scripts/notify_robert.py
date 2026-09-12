#!/usr/bin/env python3
"""ROBERT entry/exit mail - the shadow book's queued entries for the next open
and the rows it closed on the bar, to the personal list.

Until 2026-09-11 nothing mailed a ROBERT signal. notify_buys.py reads six
blobs from index.html and never ROBSIG, so the ATI TAKE on the 09-10 bar - the
first live entry since the entry-snap workflow was re-enabled - reached nobody.
The page showed it; no inbox did.

What is mailed is the ledger's `queued` list, not the TAKE chips: queued is
what the book will actually enter at the next open after the one-per-name and
busy rules, so this mail and the ledger cannot disagree about what a "buy"
is. ROBSIG only decorates each row with the gate readings the scan printed.

Usage
  notify_robert.py --page robert.html --ledger data/robert_shadow.json
      [--config ~/.strategy_lab_notify.json]
      [--state ~/.strategy_lab_robert_state.json]
      [--session YYYY-MM-DD] [--allow-stale] [--dry-run] [--force] [--test]

Recipients: `to_robert` in the config if present, else `to`. Never `to_digest`
- the subscriber list gets the ranked digest, not paper-test entries.

Freshness and dedupe follow notify_buys exactly: refuse unless the ledger's bar
is the last completed session (holidays not modelled - refusing is the safe
direction for a mail carrying "buy at the next open"), and skip when the
content hash matches the last send. On the stateless cloud runner the state
file never survives; there the workflow's new_session gate does the deduping,
same as for the two notify_buys mails beside it.
"""
import datetime as dt
import hashlib
import html as _html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_buys as nb  # noqa: E402

START_MARK = "<!-- ROBSIG:START -->"
END_MARK = "<!-- ROBSIG:END -->"
_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")

ENTRY_RULE = ("Rule: buy at the next open, ~09:45 ET limit at mid; skip if the "
              "open is already above the prior SMA5. Contract: shallowest strike "
              "with extrinsic < 20% of premium, first monthly 30-50 DTE; chain "
              "gate OI >= 10 and spread <= 25% of mid - verify on the live chain "
              "before anything else. Exit: sell at the close when close > SMA5, "
              "or the 10-bar time stop. No stop-loss.")
POSTURE = ("ROBERT - RSI(2) DITM long-call line. PAPER ONLY: indefinite forward "
           "test on real data, no capital. Nothing in this mail is an order.")


def _text(fragment):
    return _WS.sub(" ", _html.unescape(_TAG.sub("", fragment))).strip()


def parse_robsig(page):
    """The scan table robert_scan.py splices, in either its compact form or
    after a beautifier has wrapped it. Missing markers parse to empty."""
    out = {"as_of": "", "rows": {}}
    i, j = page.find(START_MARK), page.find(END_MARK)
    if i < 0 or j < 0:
        return out
    block = page[i:j]
    m = re.search(r"Scan as of the\s+(\d{4}-\d{2}-\d{2})\s+bar", block)
    if m:
        out["as_of"] = m.group(1)
    for tr in re.findall(r"<tr>(.*?)</tr>", block, re.S):
        tds = re.findall(r"<td>(.*?)</td>", tr, re.S)
        if len(tds) < 6:
            continue
        t, rsi2, rs, iv, earn, verdict = [_text(x) for x in tds[:6]]
        out["rows"][t] = {"rsi2": rsi2, "rs": rs, "iv": iv, "earn": earn,
                          "verdict": verdict,
                          "take": verdict.startswith("TAKE")}
    return out


def collect(page, ledger):
    """(as_of, entries, exits). Entries are the queued rows decorated from
    ROBSIG; a queued name ROBSIG does not list is kept with n/a readings - the
    ledger is the authority on what enters. Exits are rows closed ON the bar."""
    sig = parse_robsig(page)
    as_of = ledger.get("last_as_of") or sig["as_of"] or ""
    entries = []
    for q in ledger.get("queued") or []:
        t = q.get("t")
        r = sig["rows"].get(t, {})
        rsi2 = r.get("rsi2") or ("%.2f" % q["rsi2"]
                                 if q.get("rsi2") is not None else "n/a")
        entries.append({"t": t, "signal_date": q.get("signal_date") or as_of,
                        "rsi2": rsi2, "rs": r.get("rs", "n/a"),
                        "iv": r.get("iv", "n/a"), "earn": r.get("earn", "n/a")})
    exits = [c for c in ledger.get("closed") or []
             if c.get("exit_date") == as_of]
    return as_of, entries, exits


def next_session(as_of):
    """The next weekday. Holidays deliberately not modelled - the ledger's own
    bar arithmetic says the same, and a wrong date here is recoverable while
    a suppressed mail is not."""
    d = dt.date.fromisoformat(as_of) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def _pct(v, digits=1):
    return "n/a" if v is None else ("%+." + str(digits) + "f%%") % (v * 100)


def compose(as_of, entries, exits, url):
    nxt = next_session(as_of) if as_of else "next session"
    names_in = ", ".join(e["t"] for e in entries)
    names_out = ", ".join(x["t"] for x in exits)
    if entries:
        subject = "ROBERT: %d entr%s for the %s open - %s" % (
            len(entries), "y" if len(entries) == 1 else "ies", nxt, names_in)
    else:
        subject = "ROBERT: %d exit%s at the %s close - %s" % (
            len(exits), "" if len(exits) == 1 else "s", as_of, names_out)

    L = [POSTURE, "",
         "Scan bar %s. Entries are the shadow book's queued rows for the next "
         "open (%s - weekday roll, holidays not modelled); exits are the rows "
         "it closed at the %s close." % (as_of, nxt, as_of), ""]
    if entries:
        L.append("ENTRIES for the next open (%s) - %d" % (nxt, len(entries)))
        for e in entries:
            L.append("  %-6s RSI(2) %-6s RS252 %-6s IV proxy %-5s earnings %s"
                     % (e["t"], e["rsi2"], e["rs"], e["iv"], e["earn"]))
        L.extend(["", ENTRY_RULE, ""])
    else:
        L.extend(["No entries queued for the next open.", ""])
    if exits:
        L.append("EXITS at the %s close - %d" % (as_of, len(exits)))
        for x in exits:
            o = x.get("opt") or {}
            L.append("  %-6s %s after %s bar%s   stock %s   option %s (%s)   %s marks"
                     % (x["t"], x.get("reason", "?"), x.get("bars", "?"),
                        "" if x.get("bars") == 1 else "s", _pct(x.get("net"), 2),
                        _pct(o.get("ret")),
                        format(o["pnl"], "+,.0f").replace("+", "+$").replace("-", "-$")
                        if o.get("pnl") is not None else "n/a",
                        o.get("basis", "MODEL")))
        L.append("")
    if url:
        L.append("Page: " + url)
    return subject, "\n".join(L).rstrip() + "\n"


def payload_hash(as_of, entries, exits):
    payload = json.dumps([as_of, sorted(e["t"] for e in entries),
                          sorted((x["t"], x.get("exit_date"), x.get("reason"))
                                 for x in exits)], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main():
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    page_p = opt("--page") or sys.exit("--page /path/to/robert.html required")
    led_p = opt("--ledger") or sys.exit("--ledger /path/to/robert_shadow.json required")
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    state_path = os.path.expanduser(opt("--state", "~/.strategy_lab_robert_state.json"))
    dry, force, test = "--dry-run" in args, "--force" in args, "--test" in args

    if not os.path.exists(cfg_path):
        print("robert-notify: no config at %s - nothing sent." % cfg_path)
        return
    cfg = json.load(open(cfg_path))
    if cfg.get("to_robert"):
        cfg = dict(cfg, to=cfg["to_robert"])

    if test:
        subject, body = ("ROBERT - test notification",
                         "Wiring works. ROBERT entry/exit mail will arrive after "
                         "each green build that queues an entry or closes a row.")
        key = "test"
    else:
        page = open(page_p).read()
        ledger = json.load(open(led_p))
        as_of, entries, exits = collect(page, ledger)
        print("robert-notify: bar %s - %d queued entr%s, %d exit%s on the bar"
              % (as_of or "(none)", len(entries),
                 "y" if len(entries) == 1 else "ies", len(exits),
                 "" if len(exits) == 1 else "s"))
        if not entries and not exits:
            print("robert-notify: nothing to send")
            return
        expected = opt("--session") or nb.last_completed_session()
        if as_of != expected and "--allow-stale" not in args:
            print("robert-notify: REFUSING to send - ledger holds bar %s but the "
                  "last completed session is %s. Nothing sent. (--session "
                  "YYYY-MM-DD to set the expected date, --allow-stale to bypass.)"
                  % (as_of or "(none)", expected))
            return
        state = {}
        if os.path.exists(state_path):
            try:
                state = json.load(open(state_path))
            except Exception:
                state = {}
        key = payload_hash(as_of, entries, exits)
        if not force and state.get("last_hash") == key:
            print("robert-notify: identical payload already sent (key %s) - "
                  "skipping (--force to resend)" % key[:12])
            return
        subject, body = compose(as_of, entries, exits, cfg.get("robert_url")
                                or (cfg.get("dashboard_url") or "").replace(
                                    "index.html", "").rstrip("/") + "/robert.html"
                                if cfg.get("dashboard_url") else None)
        stamp = ("Session %s | key %s | composed %s CT"
                 % (as_of, key[:12],
                    (dt.datetime.now(nb._CHI) if nb._CHI else dt.datetime.now())
                    .strftime("%Y-%m-%d %H:%M")))
        body = body + "\n-- \n" + stamp + "\n"

    if dry:
        print("=== DRY RUN - nothing sent ===")
        print("To:", ", ".join(cfg.get("to") or []) or "(no recipients configured)")
        print("Subject:", subject)
        print(body)
        return

    results = []
    for fn in (nb.send_email, nb.send_push):
        try:
            results.append(fn(cfg, subject, body))
        except Exception as e:
            results.append("%s: FAILED %s: %s" % (fn.__name__, type(e).__name__, e))
    for r in results:
        print("robert-notify:", r)
    if not test and any(r.startswith("email: sent") for r in results):
        json.dump({"last_hash": key, "last_sent": as_of,
                   "sent_at": dt.datetime.now().isoformat(timespec="minutes")},
                  open(state_path, "w"))


if __name__ == "__main__":
    main()
