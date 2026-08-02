#!/usr/bin/env python3
"""Fetch EOD closes from Tradier for every ticker the dashboard needs and write
the closes.json that track_snapshot_reference.py consumes. Dependency-free.

Ticker set is parsed from the page itself: all SCAN tickers plus every strategy
-book universe symbol (priority/qualified/core/extended tiers), deduped.

Usage:
  TRADIER_TOKEN=... python3 dump_closes.py --index /path/to/index.html \
      --out closes.json [--days 90] [--extra SYM,SYM] [--max N]

Fail-closed: exits nonzero if fewer than 80% of tickers fetch, so the daily
build keeps serving the previous good TRACK rather than a hollow one.
Rate: ~2 requests/sec (well under Tradier's market-data limit); ~700 names
take roughly 6 minutes.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request


def page_tickers(html):
    scan = json.loads(re.search(r"const SCAN = (.*?);\n", html, re.S).group(1))
    syms = set(scan["tickers"])
    m = re.search(r"const BOOKS = (.*?);\n", html, re.S)
    if m:
        books = json.loads(m.group(1))
        for s in books.get("strategies", []):
            for v in (s.get("universe") or {}).values():
                if isinstance(v, list):
                    for e in v:
                        sym = e if isinstance(e, str) else (e or {}).get("signal")
                        if sym:
                            syms.add(sym)
    return sorted(s for s in syms if s and re.fullmatch(r"[A-Z.]{1,6}", s))


def fetch(sym, token, start):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily", "start": start})
    req = urllib.request.Request(
        "https://api.tradier.com/v1/markets/history?" + q,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    days = (d.get("history") or {}).get("day") or []
    if isinstance(days, dict):
        days = [days]
    return [[x["date"], float(x["close"])] for x in days if x.get("close") is not None]


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    index = opt("--index") or sys.exit("--index path/to/index.html required")
    outpath = opt("--out", "closes.json")
    days = int(opt("--days", "90"))
    cap = int(opt("--max", "0"))
    extra = [s for s in (opt("--extra", "") or "").upper().split(",") if s]
    token = os.environ.get("TRADIER_TOKEN")
    if not token and os.path.exists(os.path.expanduser("~/.tradier_token")):
        token = open(os.path.expanduser("~/.tradier_token")).read().strip()
    if not token:
        sys.exit("TRADIER_TOKEN not set (env var or ~/.tradier_token)")

    syms = page_tickers(open(index).read())
    syms = sorted(set(syms) | set(extra))
    if cap:
        syms = syms[:cap]
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    out, fails = {}, []
    for i, s in enumerate(syms):
        try:
            series = fetch(s, token, start)
            if len(series) >= 15:
                out[s] = series
            else:
                fails.append(s)
        except Exception:
            fails.append(s)
        time.sleep(0.5)
        if (i + 1) % 50 == 0:
            print(f"...{i + 1}/{len(syms)}", file=sys.stderr)
    print(f"fetched {len(out)}/{len(syms)}; failed: {fails[:15]}"
          f"{'...' if len(fails) > 15 else ''}", file=sys.stderr)
    if len(out) < 0.8 * max(len(syms), 1):
        sys.exit("fail-closed: fewer than 80% of tickers fetched")
    json.dump(out, open(outpath, "w"))
    print(outpath, "written", file=sys.stderr)


if __name__ == "__main__":
    main()
