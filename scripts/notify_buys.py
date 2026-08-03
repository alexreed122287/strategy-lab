#!/usr/bin/env python3
"""Send the day's NEW BUYS to email recipients and/or as a phone push.

Reads the freshly built dashboard (index.html), assembles the same picks the
Signals tab shows, and delivers them two ways - both optional, both config-only
(no credentials ever live in this repo):

  EMAIL  - any SMTP account (Gmail: use an app password). Sent as plain text
           to every address in "to".
  PUSH   - ntfy.sh topic. Anyone (you, your buddies) installs the free ntfy
           app and subscribes to the topic name; no accounts, no keys. Treat
           the topic name as a password - anyone who knows it can read AND
           post to it, so pick something unguessable.

Config file (default ~/.strategy_lab_notify.json - create it locally, never
commit it):
  {
    "to": ["you@example.com", "buddy@example.com"],
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_ssl": false,                  // true = implicit TLS (port 465)
    "smtp_user": "you@gmail.com",
    "smtp_pass": "abcd efgh ijkl mnop", // Gmail APP password, not your login
    "from": "you@gmail.com",            // optional, defaults to smtp_user
    "to_digest": ["a@x.com", "b@y.com"], // optional: --simple digest list;
                                        // falls back to "to" when absent
    "ntfy_topic": "alex-strategy-lab-8f3k2",
    "dashboard_url": "https://alexreed122287.github.io/strategy-lab/"
  }
Any part may be omitted: no "to"/"smtp_host" -> email skipped; no "ntfy_topic"
-> push skipped. Empty/missing config -> the script explains and exits 0 so the
daily build never fails on notifications.

State: ~/.strategy_lab_notify_state.json remembers the last as-of date sent, so
build re-runs do not re-send. Override with --force.

Usage:
  python3 notify_buys.py --page /path/to/index.html [--dry-run] [--force]
      [--simple]  plain-language digest: ranked new buys + the strategy that
                  fired + that name's backtest record, one screen. Keeps its
                  own dedupe state so it never collides with the full alert.
      [--state P] override the dedupe state file
      [--config /path/to/config.json] [--test]
  --dry-run : print exactly what would be sent, send nothing
  --test    : send a "wiring works" message through every configured channel
"""
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from email.mime.text import MIMEText
from email.utils import formatdate


def blob(html, name):
    m = re.search(r"const %s = (.*?);\n" % name, html, re.S)
    return json.loads(m.group(1)) if m else None


def score(avg, n):
    if avg is None or n is None:
        return None
    return round(avg * (n / (n + 10.0)), 3)


def collect(page_path):
    """Rebuild the Signals tab's actionable picks from the page blobs."""
    html = open(page_path).read()
    scan = blob(html, "SCAN") or {"tickers": {}}
    signals = blob(html, "SIGNALS") or {"signals": []}
    booksig = blob(html, "BOOKSIG") or {"rows": []}
    books = blob(html, "BOOKS") or {"strategies": []}
    S = {s.get("id"): s for s in books.get("strategies", [])}
    zuni = (S.get("zscore_000") or {}).get("universe", {})
    zstats = {e["signal"]: e for e in zuni.get("per_name", [])}
    zfactor = (S.get("zscore_000") or {}).get("exec_basis_factor") or 1.0

    pool, gw_book, paper = [], [], []
    as_of = booksig.get("as_of") or ""

    # Generator arms (RSI2 / MFI): vetted, new today only.
    for x in signals.get("signals", []):
        if x.get("state") != "TAKE" or not x.get("new_today"):
            continue
        st = (scan["tickers"].get(x.get("sym"), {}).get("strats", {})
              .get(x.get("strat")))
        if not st or not st.get("vetted"):
            continue
        as_of = max(as_of, x.get("as_of") or "")
        e19, e23 = st.get("era_1922") or {}, st.get("era_2326") or {}
        pool.append({
            "sym": x["sym"], "strat": x["strat"], "close": x.get("close"),
            "n": st.get("n"), "win": st.get("win_pct"), "pf": st.get("pf"),
            "avg": st.get("avg_pct"), "score": score(st.get("avg_pct"), st.get("n")),
            # Signals-tab parity columns: the two era profit factors are the
            # program's own era-robustness read, and depth is the trigger depth.
            "pf1922": e19.get("pf"), "pf2326": e23.get("pf"),
            "depth": x.get("depth"),
            "entry": "at the close" if x["strat"].startswith("RSI2")
                     else "close-validated (next-morning OK)"})

    # Book scanner rows: GAPW (validated book, small per-name samples by
    # design); ZSCORE is paper-only. BB never notifies (killed 2026-08-01).
    for r in booksig.get("rows", []):
        strat = r.get("strat", "")
        if strat == "BB" or r.get("state") != "TAKE":
            continue
        if strat.startswith("GAPW"):
            row = {"sym": r["sym"], "strat": strat, "close": r.get("close"),
                   "n": r.get("n"), "win": r.get("win"), "pf": None,
                   "avg": r.get("avg"), "score": score(r.get("avg"), r.get("n")),
                   "rank": r.get("book_rank"), "rs252": r.get("rs252"),
                   "pf1922": None, "pf2326": None, "depth": r.get("rs252"),
                   "entry": "MOO next 9:30 open (validated basis)"}
            gw_book.append(row)
            pool.append(row)
        elif strat == "ZSCORE":
            e = zstats.get(r["sym"])
            avg = (round(e["avg_net"] * 100 * zfactor, 2) if e else r.get("avg"))
            n = e["n"] if e else r.get("n")
            win = round(e["win"] * 100, 1) if e else r.get("win")
            paper.append({
                "sym": r["sym"], "strat": strat, "close": r.get("close"),
                "n": n, "win": win, "avg": avg, "score": score(avg, n),
                "pf": (e or {}).get("pf"), "pf1922": None, "pf2326": None,
                "depth": r.get("z50"),
                "entry": "MOO next open - PAPER only (book killed for wiring)"})

    # RANKED = the page's exact pool: vetted, 30+ trades, one best arm per
    # ticker, strength order (avg x n/(n+10)).
    pool.sort(key=lambda x: -(x["score"] if x["score"] is not None else -1e9))
    ranked, seen = [], set()
    for b in pool:
        if (b["n"] or 0) < 30 or b["score"] is None or b["sym"] in seen:
            continue
        seen.add(b["sym"])
        ranked.append(b)
    gw_book.sort(key=lambda x: (x["strat"], x["rank"] or 99))
    paper.sort(key=lambda x: -(x["score"] if x["score"] is not None else -1e9))

    # shadow-book exits that hit their rule at today's close (sell side)
    shadow = blob(html, "SHADOW") or {}
    exits = list(shadow.get("exits_today") or []) if shadow.get("as_of") == (as_of or shadow.get("as_of")) else []
    return as_of, ranked, gw_book, paper, exits


def fmt(v, suffix=""):
    return ("-" if v is None else str(v) + suffix)


def compose(as_of, ranked, gw_book, paper, exits, url):
    lines = ["Strategy Lab - new buys for " + (as_of or "latest scan"), ""]
    if ranked:
        lines.append("RANKED (vetted arms, 30+ trades, one best arm per ticker - the Top-4 pool):")
        for i, b in enumerate(ranked, 1):
            lines.append(
                f" {i}. {b['sym']:<6} {b['strat']:<11} {b['entry']}"
                f" | close {fmt(b['close'])} | strength {fmt(b['score'])}"
                f" | win {fmt(b['win'],'%')} | avg {fmt(b['avg'],'%')} | n {fmt(b['n'])}")
    else:
        lines.append("RANKED: none today (no new vetted 30+ trade signals).")
    if gw_book:
        lines.append("")
        lines.append("GAP WIDEN BOOK (book-level validated at MOO; per-name samples are small "
                     "by design - in-book order is rs252):")
        for b in gw_book:
            lines.append(
                f"  #{fmt(b['rank'])} {b['sym']:<6} {b['strat']:<11}"
                f" | close {fmt(b['close'])} | rs252 {fmt(b['rs252'],'%')}"
                f" | win {fmt(b['win'],'%')} | avg {fmt(b['avg'],'%')} | n {fmt(b['n'])}")
    if paper:
        lines.append("")
        lines.append("PAPER / RESEARCH (z-score - killed for real-money wiring; forward test only):")
        for b in paper:
            lines.append(
                f"  - {b['sym']:<6} {b['strat']:<7} {b['entry']}"
                f" | close {fmt(b['close'])} | win {fmt(b['win'],'%')}"
                f" | avg {fmt(b['avg'],'%')} (exec est) | n {fmt(b['n'])}")
    if exits:
        lines.append("")
        lines.append("SELLS - shadow-book positions whose exit rule hit at today's close:")
        for x in exits:
            net = ("%+.2f%%" % (x["net"] * 100)) if x.get("net") is not None else "-"
            lines.append(f"  - {x.get('sym',''):<6} {x.get('book',''):<11} {x.get('why','')} | {net}")
        lines.append("  (If you hold these manually, check your own sell flags on the Positions tab.)")
    lines += ["",
              "Exits: each book's rule is on the Positions tab (sell flags run daily).",
              "Numbers are backtest-derived decision support - nothing here places orders.",
              "Dashboard: " + (url or "(set dashboard_url in the notify config)")]
    subject = ("Strategy Lab %s: %d ranked buy%s%s%s%s" % (
        as_of or "", len(ranked), "" if len(ranked) == 1 else "s",
        (", %d gap-widen" % len(gw_book)) if gw_book else "",
        (", %d paper" % len(paper)) if paper else "",
        (", %d sell%s" % (len(exits), "" if len(exits) == 1 else "s")) if exits else ""))
    return subject, "\n".join(lines)


def compose_simple(as_of, ranked, gw_book, paper, url):
    """The plain-language digest: today's new buys, ranked, with the strategy
    that fired and that name's own backtest record. One screen, no jargon.

    Deliberately carries the honest label. This goes to people who have not sat
    through the research, and every book on this page has now failed at least
    one era test - an email that lists tickers without saying so would be
    misleading, which is a worse failure than being wordy."""
    rows, seen = [], set()
    for r in list(ranked) + list(gw_book) + list(paper):
        key = (r["sym"], r["strat"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    rows.sort(key=lambda x: -(x["score"] if x.get("score") is not None else -1e9))

    NAME = {"GAPW_RSI2": "Gap Widen RSI2", "GAPW_RSI14": "Gap Widen RSI14",
            "ZSCORE": "Z-Score", "RSI2": "RSI2", "MFI": "MFI"}
    # The account holds ONE position per strategy, so the buy list is each
    # strategy's top-ranked signal - not every name that triggered. Listing all
    # of them would imply 20-odd buys the account never makes.
    top, rest = {}, {}
    for r in rows:
        if r["strat"] not in top:
            top[r["strat"]] = r
        else:
            rest.setdefault(r["strat"], []).append(r["sym"])

    def bt(r):
        parts = []
        if r.get("n"):
            parts.append("%s trades" % r["n"])
        if r.get("win") is not None:
            parts.append("%.0f%% win" % r["win"])
        if r.get("avg") is not None:
            parts.append("%+.2f%%/trade" % r["avg"])
        if r.get("pf"):
            parts.append("PF %s" % r["pf"])
        return ", ".join(parts) if parts else "no per-name record"

    def cell(v, w, dec=None):
        if v is None or v == "":
            return " " * (w - 1) + "-"
        t = ("%.*f" % (dec, v)) if (dec is not None and isinstance(v, (int, float))) else str(v)
        return t.rjust(w)

    L = ["STRATEGY LAB - new buys",
         "Signals confirmed at the close of %s" % (as_of or "the last session"),
         "",
         "BUY THESE (one per strategy - its top-ranked signal)", ""]
    for r in top.values():
        px = ("$%s" % r["close"]) if r.get("close") is not None else ""
        L.append("  %-6s %-16s %s" % (r["sym"], NAME.get(r["strat"], r["strat"]), px))
        L.append("  %-6s %s" % ("", bt(r)))
        L.append("")

    # Full ranking, same columns and same top-to-bottom order as the dashboard's
    # Signals tab (strength descending). Fixed-width so it lines up in any mail
    # client that renders monospace; view in a monospace font if it looks ragged.
    L += ["ALL NEW SIGNALS - ranked exactly as the dashboard's Signals tab", "",
          "  #  TICKER STRATEGY          STR   WIN%     PF   AVG%    N  PF19-22 PF23-26    CLOSE",
          "  " + "-" * 84]
    for i, r in enumerate(rows, 1):
        L.append(cell(i, 3) + "  " +
                 ("%-6s " % r["sym"]) +
                 ("%-14s" % NAME.get(r["strat"], r["strat"])) +
                 cell(r.get("score"), 7, 2) +
                 cell(r.get("win"), 7, 1) +
                 cell(r.get("pf"), 7, 2) +
                 cell(r.get("avg"), 7, 2) +
                 cell(r.get("n"), 5) +
                 cell(r.get("pf1922"), 9, 2) +
                 cell(r.get("pf2326"), 8, 2) +
                 cell(r.get("close"), 9, 2))
    L += ["",
          "  STR = strength (avg/trade weighted by sample size) - the sort key.",
          "  PF 19-22 / PF 23-26 = profit factor by era. Both healthy is the",
          "  era-robustness read; a blank means the book has no per-era record.",
          "",
          "HOW TO ACT",
          "  Buy at the market open, next session. These are end-of-day",
          "  signals - buying intraday is not what was tested.",
          "",
          "WHAT THIS IS",
          "  Paper research. No real money is in any of these strategies,",
          "  and none is authorised for it. Every strategy here has failed",
          "  at least one historical era test: both Gap Widen books earn",
          "  roughly zero in 2011-2018, and the Z-Score book earns nothing",
          "  over simply owning the same stocks in that period. The recent",
          "  results describe one favourable regime, not a forecast. The",
          "  per-name figures above are idealised fills and read better",
          "  than reality.",
          "",
          "  Full evidence, including what failed: %s" % (url or "(dashboard)")]
    n = len(top)
    return ("Strategy Lab - %d new buy%s, %d signals (%s)"
            % (n, "" if n == 1 else "s", len(rows), as_of or ""), "\n".join(L))


def send_email(cfg, subject, body):
    to = cfg.get("to") or []
    host = cfg.get("smtp_host")
    if not (to and host):
        return "email: skipped (no to/smtp_host in config)"
    port = int(cfg.get("smtp_port") or (465 if cfg.get("smtp_ssl") else 587))
    user, pw = cfg.get("smtp_user"), cfg.get("smtp_pass")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = cfg.get("from") or user or "strategy-lab"
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    if cfg.get("smtp_ssl"):
        srv = smtplib.SMTP_SSL(host, port, timeout=30,
                               context=ssl.create_default_context())
    else:
        srv = smtplib.SMTP(host, port, timeout=30)
        srv.starttls(context=ssl.create_default_context())
    try:
        if user and pw:
            srv.login(user, pw)
        srv.sendmail(msg["From"], to, msg.as_string())
    finally:
        srv.quit()
    return "email: sent to %d recipient(s)" % len(to)


def send_push(cfg, subject, body):
    topic = cfg.get("ntfy_topic")
    if not topic:
        return "push: skipped (no ntfy_topic in config)"
    req = urllib.request.Request(
        "https://ntfy.sh/" + topic, data=body.encode(),
        headers={"Title": subject, "Priority": "default", "Tags": "chart_with_upwards_trend",
                 **({"Click": cfg["dashboard_url"]} if cfg.get("dashboard_url") else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    return "push: sent to ntfy topic"


def send_sms(cfg, subject, body):
    """Text subscribers collected by the page's signup card (sms_to list).
    Needs a Twilio account: set twilio_sid / twilio_token / twilio_from in the
    config (~$0.01 per text). Until those exist, numbers queue and this reports
    how many are waiting."""
    nums = cfg.get("sms_to") or []
    if not nums:
        return "sms: skipped (no sms_to subscribers)"
    sid, tok = cfg.get("twilio_sid"), cfg.get("twilio_token")
    frm = cfg.get("twilio_from")
    if not (sid and tok and frm):
        return ("sms: %d number(s) waiting - add twilio_sid/twilio_token/"
                "twilio_from to the config to enable texting" % len(nums))
    import base64
    text = subject + ("\n" + cfg["dashboard_url"] if cfg.get("dashboard_url") else "")
    auth = base64.b64encode(("%s:%s" % (sid, tok)).encode()).decode()
    sent = 0
    for n in nums:
        data = urllib.parse.urlencode({"To": n, "From": frm, "Body": text}).encode()
        req = urllib.request.Request(
            "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % sid,
            data=data, headers={"Authorization": "Basic " + auth})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        sent += 1
    return "sms: sent to %d number(s)" % sent


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    page = opt("--page") or sys.exit("--page /path/to/index.html required")
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    simple = "--simple" in args
    # The digest keeps its OWN dedupe state, so the 12:30 send and the
    # post-build send never suppress each other.
    state_path = os.path.expanduser(opt(
        "--state", "~/.strategy_lab_digest_state.json" if simple
        else "~/.strategy_lab_notify_state.json"))
    dry, force, test = "--dry-run" in args, "--force" in args, "--test" in args

    if not os.path.exists(cfg_path):
        print("notify: no config at %s - nothing sent. Create it (see the header "
              "of this script or docs/notifications.md) to enable email/push."
              % cfg_path)
        return
    cfg = json.load(open(cfg_path))

    if test:
        subject, body = ("Strategy Lab - test notification",
                         "Wiring works. Daily new-buy alerts will arrive after "
                         "each green build.")
    else:
        as_of, ranked, gw_book, paper, exits = collect(page)
        if not ranked and not gw_book and not paper and not exits:
            print("notify: no new buys or sells for", as_of or "latest scan", "- nothing sent")
            return
        state = {}
        if os.path.exists(state_path):
            try:
                state = json.load(open(state_path))
            except Exception:
                state = {}
        if not force and state.get("last_sent") == as_of and as_of:
            print("notify: already sent for", as_of, "- skipping (--force to resend)")
            return
        subject, body = (compose_simple(as_of, ranked, gw_book, paper, cfg.get("dashboard_url"))
                         if simple else
                         compose(as_of, ranked, gw_book, paper, exits, cfg.get("dashboard_url")))

    # The digest may go to a wider list than the personal alert. "to_digest"
    # wins when --simple is set; otherwise it falls back to "to".
    if simple and cfg.get("to_digest"):
        cfg = dict(cfg, to=cfg["to_digest"])

    if dry:
        print("--- DRY RUN (nothing sent) ---")
        print("To:", ", ".join(cfg.get("to") or []) or "(no recipients configured)")
        print("Subject:", subject)
        print(body)
        return

    results, failures = [], []
    for fn in (send_email, send_push, send_sms):
        try:
            results.append(fn(cfg, subject, body))
        except Exception as e:
            failures.append("%s failed: %r" % (fn.__name__, e))
    for line in results + failures:
        print("notify:", line)
    if not test and not failures and any(r.startswith(("email: sent", "push: sent", "sms: sent")) for r in results):
        as_of = collect(page)[0]
        json.dump({"last_sent": as_of}, open(state_path, "w"))
    if failures and not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
