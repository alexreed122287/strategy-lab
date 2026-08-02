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


API_BASE = os.environ.get("TRADIER_API_BASE", "https://api.tradier.com")


OHLCV = False


def fetch(sym, token, start):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily", "start": start})
    req = urllib.request.Request(
        API_BASE + "/v1/markets/history?" + q,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    days = (d.get("history") or {}).get("day") or []
    if isinstance(days, dict):
        days = [days]
    if OHLCV:
        return [[x["date"], float(x["open"]), float(x["high"]), float(x["low"]),
                 float(x["close"]), float(x.get("volume") or 0)]
                for x in days if x.get("close") is not None]
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
    global OHLCV
    OHLCV = "--ohlcv" in args
    fp = os.path.expanduser("~/.tradier_token")
    token, token_src = None, "~/.tradier_token"
    if os.path.exists(fp):
        token = open(fp).read().strip()
    if not token:
        token, token_src = os.environ.get("TRADIER_TOKEN"), "TRADIER_TOKEN env var"
    if not token:
        sys.exit("no token: put it in ~/.tradier_token (preferred) or TRADIER_TOKEN")
    # Preflight: one probe request so an auth problem fails in 1 second with the
    # token SOURCE named (a stale exported TRADIER_TOKEN can no longer shadow a
    # good token file - the file now takes precedence).
    try:
        fetch("AAPL", token,
              (datetime.date.today() - datetime.timedelta(days=10)).isoformat())
        print(f"token source {token_src}: preflight OK against {API_BASE}",
              file=sys.stderr)
    except Exception as e:
        sys.exit(f"fail-closed: preflight failed using {token_src} against "
                 f"{API_BASE} -> {e!r}")

    syms = page_tickers(open(index).read())
    syms = sorted(set(syms) | set(extra))
    if cap:
        syms = syms[:cap]
    start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    out, fails, errs = {}, [], []
    for i, s in enumerate(syms):
        try:
            series = fetch(s, token, start)
            if len(series) >= 15:
                out[s] = series
            else:
                fails.append(s)
        except Exception as e:
            fails.append(s)
            if len(errs) < 3:
                errs.append(f"{s}: {e!r}")
        time.sleep(0.5)
        if not out and len(fails) >= 5 and errs:
            print("aborting early - first 5 requests ALL failed. Sample errors:",
                  file=sys.stderr)
            for line in errs:
                print("  " + line, file=sys.stderr)
            print("Hints: HTTP 401 = wrong/rotated token (put the CURRENT one in "
                  "~/.tradier_token); a sandbox token needs "
                  "TRADIER_API_BASE=https://sandbox.tradier.com", file=sys.stderr)
            sys.exit("fail-closed: Tradier auth/endpoint problem")
        if (i + 1) % 50 == 0:
            print(f"...{i + 1}/{len(syms)}", file=sys.stderr)
    print(f"fetched {len(out)}/{len(syms)}; failed: {fails[:15]}"
          f"{'...' if len(fails) > 15 else ''}", file=sys.stderr)
    for line in errs:
        print("  error sample - " + line, file=sys.stderr)
    if len(out) < 0.8 * max(len(syms), 1):
        sys.exit("fail-closed: fewer than 80% of tickers fetched")
    json.dump(out, open(outpath, "w"))
    print(outpath, "written", file=sys.stderr)


if __name__ == "__main__":
    main()
