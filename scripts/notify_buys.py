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
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate


# Ported verbatim from index.html so the email and the Signals tab cannot drift.
EXITS = {"RSI2": "close>SMA5 | 10 bars", "RSI2_LEV": "close>SMA5 | 10 bars",
         "MFI": "close>EMA7 | 10 bars",
         "ZSCORE": "close>EMA5 | 10 bars | pre-earnings",
         "GAPW_RSI2": "rsi2>80 3:45->MOC | 10 bars",
         "GAPW_RSI14": "rsi14>60 3:45->MOC | 10 bars"}
TRIGL = {"RSI2": "RSI2", "RSI2_LEV": "RSI2", "MFI": "MFI",
         "GAPW_RSI2": "RSI2", "GAPW_RSI14": "RSI14", "ZSCORE": "RSI3"}


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
            "state": x.get("state"), "new": bool(x.get("new_today")),
            "exit": EXITS.get(x["strat"], ""), "vehicle": st.get("vehicle") or "1x",
            "trig": ("%s %s" % (TRIGL.get(x["strat"], ""), x.get("depth"))).strip(),
            "earnings": bool(x.get("earnings_soon")),
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
                   "state": r.get("state"), "new": True,
                   "exit": EXITS.get(strat, ""), "vehicle": r.get("vehicle") or "1x",
                   "trig": ("%s %s" % (TRIGL.get(strat, ""), r.get("rsi"))).strip(),
                   "earnings": False,
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
                "state": r.get("state"), "new": True,
                "exit": EXITS.get(strat, ""), "vehicle": "1x",
                "trig": ("RSI3 %s" % r.get("rsi3")) if r.get("rsi3") is not None else "",
                "earnings": r.get("state") == "PASS-EARNINGS",
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
    """The daily ranked digest: every new signal, in the dashboard Signals tab's
    own columns and its own top-to-bottom order (Strength descending).

    Returns (subject, text, html). Sixteen columns cannot be aligned in plain
    text without wrapping in most mail clients, so the HTML table is the real
    deliverable and the text part is a readable fallback.

    The honest label rides along deliberately. This goes to people who have not
    sat through the research, and every book here has now failed at least one
    era test - a table of tickers and win rates with no context would read as a
    recommendation."""
    rows, seen = [], set()
    for r in list(ranked) + list(gw_book) + list(paper):
        key = (r["sym"], r["strat"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    rows.sort(key=lambda x: -(x["score"] if x.get("score") is not None else -1e9))
    for i, r in enumerate(rows, 1):
        r["_rank"] = i

    NAME = {"GAPW_RSI2": "Gap Widen RSI2", "GAPW_RSI14": "Gap Widen RSI14",
            "ZSCORE": "Z-Score", "RSI2": "RSI2", "MFI": "MFI"}
    COLS = [("Ticker", "sym", "l"), ("Rank", "_rank", "r"), ("State", "state", "l"),
            ("New", "new", "c"), ("Strategy", "strat", "l"), ("Exit", "exit", "l"),
            ("Vehicle", "vehicle", "l"), ("Strength", "score", "r"),
            ("Win %", "win", "r"), ("PF", "pf", "r"), ("Avg/trade %", "avg", "r"),
            ("Trades", "n", "r"), ("PF 19-22", "pf1922", "r"),
            ("PF 23-26", "pf2326", "r"), ("Trigger", "trig", "l"),
            ("Earnings", "earnings", "c")]
    DEC = {"score": 2, "win": 1, "pf": 2, "avg": 2, "pf1922": 2, "pf2326": 2}

    def val(r, key):
        v = r.get(key)
        if key == "strat":
            return NAME.get(v, v or "")
        if key == "new":
            return "NEW" if v else ""
        if key == "earnings":
            return "yes" if v else ""
        if v is None or v == "":
            return "-"
        if key in DEC and isinstance(v, (int, float)):
            return "%.*f" % (DEC[key], v)
        return str(v)

    def esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    # ---------- HTML ----------
    ALIGN = {"l": "left", "r": "right", "c": "center"}
    th = "".join('<th style="padding:6px 9px;border-bottom:2px solid #444;'
                 'text-align:%s;white-space:nowrap;font-size:12px">%s</th>'
                 % (ALIGN[a], esc(h)) for h, _, a in COLS)
    trs = []
    for i, r in enumerate(rows):
        bg = "#fafafa" if i % 2 else "#ffffff"
        tds = "".join('<td style="padding:5px 9px;border-bottom:1px solid #e6e6e6;'
                      'text-align:%s;white-space:nowrap;font-size:12px">%s</td>'
                      % (ALIGN[a], esc(val(r, k))) for _, k, a in COLS)
        trs.append('<tr style="background:%s">%s</tr>' % (bg, tds))
    html = """<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#111">
<h2 style="margin:0 0 2px 0;font-size:17px">Strategy Lab &mdash; new buys</h2>
<p style="margin:0 0 14px 0;color:#555;font-size:13px">Signals confirmed at the close of %s &middot; ranked by Strength, exactly as the dashboard's Signals tab</p>
<div style="overflow-x:auto"><table cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">
<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>
<p style="margin:14px 0 4px 0;font-size:12px;color:#555">
<b>Strength</b> = avg/trade weighted by sample size &mdash; the sort key.
<b>PF 19-22 / PF 23-26</b> = profit factor by era; both healthy is the era-robustness read, and a dash means the book has no per-era record.</p>
<h3 style="margin:16px 0 4px 0;font-size:14px">How to act</h3>
<p style="margin:0;font-size:13px">Buy at the market open, next session. These are end-of-day signals &mdash; buying intraday is not what was tested.</p>
<h3 style="margin:16px 0 4px 0;font-size:14px">What this is</h3>
<p style="margin:0;font-size:13px;color:#333">Paper research. No real money is in any of these strategies and none is authorised for it.
Every strategy here has failed at least one historical era test: both Gap Widen books earn roughly zero in 2011-2018, and the Z-Score book
earns nothing over simply owning the same stocks in that period. The recent results describe one favourable regime, not a forecast, and the
per-name figures above are idealised fills that read better than reality.</p>
<p style="margin:10px 0 0 0;font-size:13px">Full evidence, including what failed: <a href="%s">%s</a></p>
</div>""" % (esc(as_of or "the last session"), th, "".join(trs),
             esc(url or "#"), esc(url or "(dashboard)"))

    # ---------- plain-text fallback ----------
    w = [max(len(h), max((len(val(r, k)) for r in rows), default=0)) for h, k, _ in COLS]
    def line(cells):
        return "  " + "  ".join(
            (c.ljust(w[i]) if COLS[i][2] == "l" else c.rjust(w[i]))
            for i, c in enumerate(cells))
    T = ["STRATEGY LAB - new buys",
         "Signals confirmed at the close of %s" % (as_of or "the last session"),
         "Ranked by Strength, exactly as the dashboard's Signals tab.",
         "(View in HTML for the aligned table.)", "",
         line([h for h, _, _ in COLS]),
         "  " + "-" * (sum(w) + 2 * (len(w) - 1))]
    T += [line([val(r, k) for _, k, _ in COLS]) for r in rows]
    T += ["",
          "  Strength = avg/trade weighted by sample size - the sort key.",
          "  PF 19-22 / PF 23-26 = profit factor by era; both healthy is the",
          "  era-robustness read, a dash means no per-era record.",
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
    return ("Strategy Lab - %d new signal%s (%s)"
            % (len(rows), "" if len(rows) == 1 else "s", as_of or ""),
            "\n".join(T), html)


def send_email(cfg, subject, body, html=None):
    to = cfg.get("to") or []
    host = cfg.get("smtp_host")
    if not (to and host):
        return "email: skipped (no to/smtp_host in config)"
    port = int(cfg.get("smtp_port") or (465 if cfg.get("smtp_ssl") else 587))
    user, pw = cfg.get("smtp_user"), cfg.get("smtp_pass")
    if html:
        # multipart/alternative: clients that render HTML get the aligned
        # table, everything else falls back to the text part.
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html, "html"))
    else:
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
    html = None

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
        if simple:
            subject, body, html = compose_simple(as_of, ranked, gw_book, paper,
                                                 cfg.get("dashboard_url"))
        else:
            subject, body = compose(as_of, ranked, gw_book, paper, exits,
                                    cfg.get("dashboard_url"))

    # The digest may go to a wider list than the personal alert. "to_digest"
    # wins when --simple is set; otherwise it falls back to "to".
    if simple and cfg.get("to_digest"):
        cfg = dict(cfg, to=cfg["to_digest"])

    if dry:
        print("--- DRY RUN (nothing sent) ---")
        print("To:", ", ".join(cfg.get("to") or []) or "(no recipients configured)")
        print("Subject:", subject)
        print(body)
        if html and "--html" in args:
            print("\n--- HTML PART ---\n" + html)
        return

    results, failures = [], []
    for fn in (send_email, send_push, send_sms):
        try:
            results.append(send_email(cfg, subject, body, html)
                           if fn is send_email else fn(cfg, subject, body))
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
