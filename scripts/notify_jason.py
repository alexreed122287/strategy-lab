#!/usr/bin/env python3
"""JASON entry/exit mail - the shadow book's queued entries for the next open
and the rows it closed on the bar, to the personal list.

Written 2026-09-15 on the owner's ask: JASON had no mail of any kind. Its
forward ledger opened 09/12/2026 and filled AMAT and CAT on the 09-14 bar off
real chain quotes, and none of it reached an inbox - the same gap
notify_robert.py was written to close for ROBERT four days earlier. The page
showed it; nobody was told.

Modelled on notify_robert.py deliberately, down to the freshness and dedupe
rules, so the two books' mail cannot drift apart in behaviour. The one
structural difference: ROBERT decorates its entries from the ROBSIG blob
spliced into its page, because its ledger does not carry the gate readings.
JASON's queued rows carry every reading already (close, vap50, atr14,
threshold, rs252, iv_proxy), so this reads the LEDGER ALONE and never the
page - one authority, no chance of the mail and the ledger disagreeing about
what a buy is.

What is mailed is the ledger's `queued` list, not a TAKE chip: queued is what
the book will actually enter at the next open after the one-per-name and
5-bar rules.

Usage
  notify_jason.py --ledger data/jason_shadow.json
      [--config ~/.strategy_lab_notify.json]
      [--state ~/.strategy_lab_jason_state.json]
      [--session YYYY-MM-DD] [--allow-stale] [--dry-run] [--force] [--test]

Recipients: `to_jason` in the config if present, else `to` - the same list the
RSI2 alert goes to, which is what the owner asked for. Never `to_digest`: the
subscriber list gets the ranked digest, not paper-test entries.

Freshness and dedupe follow notify_robert exactly: refuse unless the ledger's
bar is the last completed session (holidays not modelled - refusing is the safe
direction for a mail carrying "buy at the next open"), and skip when the
content hash matches the last send. On the stateless cloud runner the state
file never survives; there the workflow's new_session gate does the deduping.
"""

import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_buys as nb  # noqa: E402

ENTRY_RULE = (
    "Rule: buy at the NEXT SESSION'S OPEN, 09:30 ET. There is no gap-skip rule "
    "- JASON has none. Contract: first monthly >= 30 DTE, shallowest strike "
    "with extrinsic under 20% of premium (deep ITM). The jason-entry-snap "
    "workflow targets a 09:45 ET chain quote; verify on the live chain before "
    "anything else. Exit: sell at the CLOSE of the first bar that closes back "
    "at or above VAP(50), or at the contract's expiry - no DTE cap, no time "
    "stop, no profit target, no stop-loss. Size: 5 slots at $12,500 on a "
    "$250,000 sleeve - never ROBERT's 6 x 15%.")
POSTURE = ("JASON - VAP dislocation reversion, DITM long calls, S&P 500. PAPER "
           "ONLY: forward ledger since 09/12/2026 on real chains, no capital. "
           "Nothing in this mail is an order.")


def _pct(v, digits=1):
    return "n/a" if v is None else ("%+." + str(digits) + "f%%") % (v * 100)


def _num(v, digits=2):
    return "n/a" if v is None else ("%.*f" % (digits, v))


def _lvl(v, digits=1):
    """Unsigned percent. IV proxy is a level; _pct's sign would read as a move."""
    return "n/a" if v is None else ("%.*f%%" % (digits, v * 100))


def collect(ledger):
    """(as_of, entries, exits) straight off the ledger - the one authority."""
    as_of = ledger.get("last_as_of") or ""
    entries = [{"t": q.get("t"),
                "signal_date": q.get("signal_date") or as_of,
                "close": q.get("close"), "vap50": q.get("vap50"),
                "threshold": q.get("threshold"), "atr14": q.get("atr14"),
                "rs252": q.get("rs252"), "iv_proxy": q.get("iv_proxy")}
               for q in (ledger.get("queued") or [])]
    exits = [c for c in (ledger.get("closed") or [])
             if c.get("exit_date") == as_of]
    return as_of, entries, exits


def compose(as_of, entries, exits, url):
    nxt = nb_next_session(as_of) if as_of else "next session"
    names_in = ", ".join(e["t"] for e in entries)
    names_out = ", ".join(x.get("t", "?") for x in exits)
    if entries:
        subject = "JASON: %d entr%s for the %s open - %s" % (
            len(entries), "y" if len(entries) == 1 else "ies", nxt, names_in)
    else:
        subject = "JASON: %d exit%s at the %s close - %s" % (
            len(exits), "" if len(exits) == 1 else "s", as_of, names_out)

    L = [POSTURE, "",
         "Scan bar %s. Entries are the shadow book's queued rows for the next "
         "open (%s - weekday roll, holidays not modelled); exits are the rows "
         "it closed at the %s close." % (as_of, nxt, as_of), ""]
    if entries:
        L.append("ENTRIES for the next open (%s) - %d" % (nxt, len(entries)))
        for e in entries:
            L.append("  %-6s close %-9s trigger %-9s VAP50 %-9s RS252 %-7s IV proxy %s"
                     % (e["t"], _num(e["close"]), _num(e["threshold"]),
                        _num(e["vap50"]), _pct(e["rs252"]), _lvl(e["iv_proxy"])))
        L.extend(["", ENTRY_RULE, ""])
    else:
        L.extend(["No entries queued for the next open.", ""])
    if exits:
        L.append("EXITS at the %s close - %d" % (as_of, len(exits)))
        for x in exits:
            o = x.get("opt") or {}
            L.append("  %-6s %s after %s bar%s   stock %s   option %s (%s)   %s marks"
                     % (x.get("t", "?"), x.get("reason", "?"), x.get("bars", "?"),
                        "" if x.get("bars") == 1 else "s", _pct(x.get("net"), 2),
                        _pct(o.get("ret")),
                        format(o["pnl"], "+,.0f").replace("+", "+$").replace("-", "-$")
                        if o.get("pnl") is not None else "n/a",
                        o.get("basis", "MODEL")))
        L.append("")
    if url:
        L.append("Page: " + url)
    return subject, "\n".join(L).rstrip() + "\n"


def nb_next_session(as_of):
    """The next weekday. Holidays deliberately not modelled - same call
    notify_robert makes, and for the same reason: a wrong date here is
    recoverable, a suppressed mail is not."""
    d = dt.date.fromisoformat(as_of) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def payload_hash(as_of, entries, exits):
    payload = json.dumps([as_of, sorted(e["t"] for e in entries),
                          sorted((x.get("t"), x.get("exit_date"), x.get("reason"))
                                 for x in exits)], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def main():
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    led_p = opt("--ledger") or sys.exit("--ledger data/jason_shadow.json required")
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    state_path = os.path.expanduser(opt("--state", "~/.strategy_lab_jason_state.json"))
    dry, force, test = "--dry-run" in args, "--force" in args, "--test" in args

    if not os.path.exists(cfg_path):
        print("jason-notify: no config at %s - nothing sent." % cfg_path)
        return
    try:
        cfg = json.load(open(cfg_path))
    except Exception as e:
        print("jason-notify: config at %s is unreadable (%s: %s) - nothing sent."
              % (cfg_path, type(e).__name__, e))
        return
    # Default is the RSI2 alert list, per the owner's ask. `to_jason` is an
    # override for when this book should go somewhere narrower.
    if cfg.get("to_jason"):
        cfg = dict(cfg, to=cfg["to_jason"])

    if test:
        subject, body = ("JASON - test notification",
                         "Wiring works. JASON entry/exit mail will arrive after "
                         "each green build that queues an entry or closes a row.")
        key = "test"
    else:
        ledger = json.load(open(led_p))
        as_of, entries, exits = collect(ledger)
        print("jason-notify: bar %s - %d queued entr%s, %d exit%s on the bar"
              % (as_of or "(none)", len(entries),
                 "y" if len(entries) == 1 else "ies", len(exits),
                 "" if len(exits) == 1 else "s"))
        if not entries and not exits:
            print("jason-notify: nothing to send")
            return
        expected = opt("--session") or nb.last_completed_session()
        if as_of != expected and "--allow-stale" not in args:
            print("jason-notify: REFUSING to send - ledger holds bar %s but the "
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
            print("jason-notify: identical payload already sent (key %s) - "
                  "skipping (--force to resend)" % key[:12])
            return
        url = cfg.get("jason_url")
        if not url and cfg.get("dashboard_url"):
            url = (cfg["dashboard_url"].replace("index.html", "").rstrip("/")
                   + "/jason.html")
        subject, body = compose(as_of, entries, exits, url)
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
        print("jason-notify:", r)
    if not test and any(r.startswith("email: sent") for r in results):
        json.dump({"last_hash": key, "last_sent": as_of,
                   "sent_at": dt.datetime.now().isoformat(timespec="minutes")},
                  open(state_path, "w"))


if __name__ == "__main__":
    main()
