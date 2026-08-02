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
        pool.append({
            "sym": x["sym"], "strat": x["strat"], "close": x.get("close"),
            "n": st.get("n"), "win": st.get("win_pct"), "pf": st.get("pf"),
            "avg": st.get("avg_pct"), "score": score(st.get("avg_pct"), st.get("n")),
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
    return as_of, ranked, gw_book, paper


def fmt(v, suffix=""):
    return ("-" if v is None else str(v) + suffix)


def compose(as_of, ranked, gw_book, paper, url):
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
    lines += ["",
              "Exits: each book's rule is on the Positions tab (sell flags run daily).",
              "Numbers are backtest-derived decision support - nothing here places orders.",
              "Dashboard: " + (url or "(set dashboard_url in the notify config)")]
    subject = ("Strategy Lab %s: %d ranked buy%s%s%s" % (
        as_of or "", len(ranked), "" if len(ranked) == 1 else "s",
        (", %d gap-widen" % len(gw_book)) if gw_book else "",
        (", %d paper" % len(paper)) if paper else ""))
    return subject, "\n".join(lines)


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


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    page = opt("--page") or sys.exit("--page /path/to/index.html required")
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    state_path = os.path.expanduser("~/.strategy_lab_notify_state.json")
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
        as_of, ranked, gw_book, paper = collect(page)
        if not ranked and not gw_book and not paper:
            print("notify: no new buys for", as_of or "latest scan", "- nothing sent")
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
        subject, body = compose(as_of, ranked, gw_book, paper, cfg.get("dashboard_url"))

    if dry:
        print("--- DRY RUN (nothing sent) ---")
        print("Subject:", subject)
        print(body)
        return

    results, failures = [], []
    for fn in (send_email, send_push):
        try:
            results.append(fn(cfg, subject, body))
        except Exception as e:
            failures.append("%s failed: %r" % (fn.__name__, e))
    for line in results + failures:
        print("notify:", line)
    if not test and not failures and any(r.startswith(("email: sent", "push: sent")) for r in results):
        as_of = collect(page)[0]
        json.dump({"last_sent": as_of}, open(state_path, "w"))
    if failures and not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
