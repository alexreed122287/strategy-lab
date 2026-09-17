#!/usr/bin/env python3
"""Refresh data/jason_earnings.json - forward earnings dates for the whole
JASON universe, so the ledger's earnings-inside-hold gate is armed for every
name and not just the 69 the ROBERT seed happens to cover.

Source: FMP's earnings calendar (one call per 15-day window, 90 days out),
filtered to the universe. The key comes from FMP_API_KEY or the LevelCheck
engine's env file on the Mac. The cloud build has no key and uses the
committed seed; the Mac build refreshes and commits it.

Never a wrong date: no key, no network, a failed window or an empty answer
leaves the old seed in place rather than writing a thinner one. A partial
fetch is data loss, not a truth update, so any window failure abandons the
whole refresh.

But no longer QUIET about it. Owner's call 2026-09-17: this live fetch is the
authority for the earnings-inside-hold gate, and an authority that can skip
silently is a ghost - the gate then runs on whatever happens to be on disk and
nothing says so. Every leave-as-is path now exits NON-ZERO so the caller can
react; daily_build.sh keeps it non-fatal for the other books but says loudly
what it costs JASON. The failure that prompted this: on 2026-09-15 the Mac
admitted FDX while the cloud, reading the committed seed, blocked it on
earnings two days out - one bar, one rule, two answers.

Usage: jason_earnings_seed.py [--universe jason_universe.txt] [--out data/jason_earnings.json] [--days 90]
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

FMP = "https://financialmodelingprep.com/stable/earnings-calendar"


def opt(a, n, d=None):
    return a[a.index(n) + 1] if n in a else d


def fmp_key():
    k = os.environ.get("FMP_API_KEY")
    if k:
        return k.strip()
    p = os.path.expanduser("~/repos/strikepilot/engine/.env")
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("FMP_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def fmp_symbol(t):
    """Universe spellings use a dash for share classes (BRK-B, BF-B); FMP does too."""
    return t.strip().upper()


def fetch_window(key, start, end):
    q = urllib.parse.urlencode({"from": start.isoformat(), "to": end.isoformat(), "apikey": key})
    with urllib.request.urlopen(FMP + "?" + q, timeout=30) as r:
        d = json.load(r)
    return d if isinstance(d, list) else []


def main():
    a = sys.argv[1:]
    uni_p = opt(a, "--universe", "jason_universe.txt")
    out_p = opt(a, "--out", "data/jason_earnings.json")
    days = int(opt(a, "--days", "90"))
    uni = [t.strip() for t in open(uni_p).read().replace("\n", ",").split(",") if t.strip()]
    want = {fmp_symbol(t): t for t in uni}
    key = fmp_key()
    if not key:
        print("jason_earnings_seed: no FMP key - seed left as is", file=sys.stderr)
        return 1
    today = dt.date.today()
    found = {}
    start = today
    while start <= today + dt.timedelta(days=days):
        end = min(start + dt.timedelta(days=14), today + dt.timedelta(days=days))
        try:
            rows = fetch_window(key, start, end)
        except Exception as e:
            print(f"jason_earnings_seed: window {start}..{end} failed ({e}) - seed left as is", file=sys.stderr)
            return 1
        for r in rows:
            s = str(r.get("symbol") or "").upper()
            d = str(r.get("date") or "")[:10]
            if s in want and d:
                found.setdefault(want[s], set()).add(d)
        start = end + dt.timedelta(days=1)
    if not found:
        print("jason_earnings_seed: empty answer - seed left as is", file=sys.stderr)
        return 1
    out = {t: sorted(ds) for t, ds in sorted(found.items())}
    os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
    json.dump({"as_of": today.isoformat(), "source": "fmp earnings-calendar", "days": days,
               "names": out}, open(out_p, "w"), indent=1)
    print(f"jason_earnings_seed: {len(out)}/{len(uni)} names with a date inside {days} days, "
          f"written to {out_p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
