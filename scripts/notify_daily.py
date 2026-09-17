#!/usr/bin/env python3
"""One daily email, three sections - RSI2 / shared books, ROBERT, JASON.

Owner's ask, 2026-09-15: "combine them into one daily email with sections."
Before this the build sent three separate mails to (by default) the same list:
notify_buys' alert, notify_robert's entry/exit mail, and notify_jason's. Three
subjects a morning for one decision.

SINGLE SOURCE OF TRUTH. Each section's text is produced by that book's OWN
compose() - this module never re-formats a row itself. That is deliberate: the
moment this file learned to print a ROBERT entry, there would be two renderers
for one fact and they would drift, which is the defect this program keeps
paying for. So a section here reads exactly as that book's standalone mail
would have read, and the per-book mailers stay runnable on their own for
debugging and backfill.

PER-SECTION FRESHNESS. Each book carries its own bar. A section whose bar is
not the last completed session is SUPPRESSED and says so rather than printing
positions from an older day beside fresh ones - the mail carries a "buy at the
next open" imperative, and a silently stale section is worse than a missing
one. One book being stale never suppresses the others.

PER-SECTION FAILURE. If a book's collect or compose raises, the mail still
goes with that section marked FAILED and the exception named. Silence there
would read as "no signals", which is a lie the reader cannot detect.

RECIPIENTS: `to` - the RSI2 alert list, per the ask. In combined mode the
per-book override keys `to_robert` and `to_jason` are NOT consulted, because
one mail cannot go to two lists; if either is set, this prints a loud warning
naming it so the widening is visible in the build log rather than silent. A
book that genuinely needs its own list should keep using its own mailer.
Never `to_digest`: the subscriber list gets the ranked digest, not paper-test
entries, and that mail is untouched by this one.

Usage
  notify_daily.py --page index.html --robert-page robert.html
      --robert-ledger data/robert_shadow.json --jason-ledger data/jason_shadow.json
      [--config ~/.strategy_lab_notify.json]
      [--state ~/.strategy_lab_daily_state.json]
      [--session YYYY-MM-DD] [--allow-stale] [--dry-run] [--force] [--test]
"""

import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_buys as nb        # noqa: E402
import notify_robert as nr      # noqa: E402
import notify_jason as nj       # noqa: E402

RULE = "=" * 68


def _sect(title, state, body=""):
    """One section: a banner, a one-word state, and the book's own text."""
    head = "%s\n%s  [%s]\n%s" % (RULE, title, state, RULE)
    return head + ("\n" + body.rstrip() + "\n" if body.strip() else "\n")


def rsi2_section(page_path, expected, allow_stale, url_hint=None):
    """(state, count, body, key) for the shared-book alert."""
    as_of, ranked, gw_book, paper, exits, scan_as_of = nb.collect(page_path)
    n = len(ranked) + len(gw_book) + len(paper) + len(exits)
    if not n:
        return "NOTHING", 0, "No new buys or sells on the %s bar." % (as_of or "latest"), ""
    if as_of != expected and not allow_stale:
        return ("STALE", 0,
                "Suppressed: page holds bar %s, last completed session is %s."
                % (as_of or "(none)", expected), "")
    # scan_as_of rides through to compose so the combined mail dates its
    # evidence exactly as the standalone alert does. Section text comes from
    # the book's own compose() precisely so the two cannot say different
    # things about where a number came from.
    _, body = nb.compose(as_of, ranked, gw_book, paper, exits, url_hint, scan_as_of)
    return "OK", n, body, nb.payload_hash(as_of, ranked, gw_book, paper, exits)


def robert_section(page_path, ledger_path, expected, allow_stale, url):
    page = open(page_path).read()
    ledger = json.load(open(ledger_path))
    as_of, entries, exits = nr.collect(page, ledger)
    n = len(entries) + len(exits)
    if not n:
        return "NOTHING", 0, "No entries queued and no exits on the %s bar." % (as_of or "latest"), ""
    if as_of != expected and not allow_stale:
        return ("STALE", 0,
                "Suppressed: ledger holds bar %s, last completed session is %s."
                % (as_of or "(none)", expected), "")
    _, body = nr.compose(as_of, entries, exits, url)
    return "OK", n, body, nr.payload_hash(as_of, entries, exits)


def jason_section(ledger_path, expected, allow_stale, url):
    ledger = json.load(open(ledger_path))
    as_of, entries, exits = nj.collect(ledger)
    n = len(entries) + len(exits)
    if not n:
        return "NOTHING", 0, "No entries queued and no exits on the %s bar." % (as_of or "latest"), ""
    if as_of != expected and not allow_stale:
        return ("STALE", 0,
                "Suppressed: ledger holds bar %s, last completed session is %s."
                % (as_of or "(none)", expected), "")
    _, body = nj.compose(as_of, entries, exits, url)
    return "OK", n, body, nj.payload_hash(as_of, entries, exits)


def build(sections, expected):
    """sections: [(title, state, count, body, key)] -> (subject, body, key)."""
    live = [(t, c) for t, s, c, _, _ in sections if s == "OK" and c]
    bad = [t for t, s, _, _, _ in sections if s in ("STALE", "FAILED")]
    if live:
        summary = " | ".join("%s %d" % (t.split()[0], c) for t, c in live)
    else:
        summary = "no signals"
    subject = "Strategy Lab %s - %s" % (expected, summary)
    if bad:
        subject += "  [%s: %s]" % ("check" if len(bad) > 1 else "check",
                                   ", ".join(b.split()[0] for b in bad))
    L = ["Strategy Lab - daily, session %s" % expected,
         "Sections: " + ", ".join("%s %s" % (t.split()[0], s)
                                  for t, s, _, _, _ in sections),
         "Nothing in this mail places an order.", ""]
    for title, state, _c, body, _k in sections:
        L.append(_sect(title, state, body))
    return subject, "\n".join(L).rstrip() + "\n", hashlib.sha256(
        json.dumps([expected] + [k for _, _, _, _, k in sections],
                   sort_keys=True).encode()).hexdigest()


def main():
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    page_p = opt("--page", "index.html")
    rob_page = opt("--robert-page", "robert.html")
    rob_led = opt("--robert-ledger", "data/robert_shadow.json")
    jas_led = opt("--jason-ledger", "data/jason_shadow.json")
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    state_path = os.path.expanduser(opt("--state", "~/.strategy_lab_daily_state.json"))
    dry, force, test = "--dry-run" in args, "--force" in args, "--test" in args
    allow_stale = "--allow-stale" in args

    if not os.path.exists(cfg_path):
        print("daily-notify: no config at %s - nothing sent." % cfg_path)
        return
    try:
        cfg = json.load(open(cfg_path))
    except Exception as e:
        print("daily-notify: config at %s is unreadable (%s: %s) - nothing sent."
              % (cfg_path, type(e).__name__, e))
        return

    # One mail cannot go to two lists. Say so rather than widening in silence.
    for k in ("to_robert", "to_jason"):
        if cfg.get(k):
            print("daily-notify: WARNING - config sets `%s`, which the combined "
                  "mail does NOT use. This section will go to `to` along with "
                  "everything else. Run that book's own mailer if it needs a "
                  "separate list." % k)

    if test:
        subject, body = ("Strategy Lab - test notification",
                         "Wiring works. The combined daily mail carries RSI2, "
                         "ROBERT and JASON sections after each green build.")
        key = "test"
    else:
        expected = opt("--session") or nb.last_completed_session()
        dash = cfg.get("dashboard_url")
        base = (dash or "").replace("index.html", "").rstrip("/")
        specs = [
            ("RSI2 / SHARED BOOKS", lambda: rsi2_section(page_p, expected, allow_stale, dash)),
            ("ROBERT - RSI(2) DITM calls", lambda: robert_section(
                rob_page, rob_led, expected, allow_stale,
                cfg.get("robert_url") or (base + "/robert.html" if base else None))),
            ("JASON - VAP dislocation reversion", lambda: jason_section(
                jas_led, expected, allow_stale,
                cfg.get("jason_url") or (base + "/jason.html" if base else None))),
        ]
        sections = []
        for title, fn in specs:
            try:
                state, count, body, k = fn()
            except Exception as e:
                # A section that blew up must SAY so - silence reads as "no
                # signals", which the reader cannot tell from the real thing.
                state, count, body, k = ("FAILED", 0,
                                         "This section could not be built: %s: %s"
                                         % (type(e).__name__, e), "")
            sections.append((title, state, count, body, k))
            print("daily-notify: %-34s %-8s %d row(s)" % (title, state, count))

        if not any(s == "OK" and c for _, s, c, _, _ in sections):
            print("daily-notify: no live section on the %s bar - nothing sent" % expected)
            return

        subject, body, key = build(sections, expected)
        state = {}
        if os.path.exists(state_path):
            try:
                state = json.load(open(state_path))
            except Exception:
                state = {}
        if not force and state.get("last_hash") == key:
            print("daily-notify: identical payload already sent (key %s) - "
                  "skipping (--force to resend)" % key[:12])
            return
        body += ("\n-- \nSession %s | key %s | composed %s CT\n"
                 % (expected, key[:12],
                    (dt.datetime.now(nb._CHI) if nb._CHI else dt.datetime.now())
                    .strftime("%Y-%m-%d %H:%M")))

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
        print("daily-notify:", r)
    if not test and any(r.startswith("email: sent") for r in results):
        json.dump({"last_hash": key,
                   "sent_at": dt.datetime.now().isoformat(timespec="minutes")},
                  open(state_path, "w"))


if __name__ == "__main__":
    main()
