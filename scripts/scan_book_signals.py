#!/usr/bin/env python3
"""Evaluate the strategy books' entry rules on the latest bars and splice a
BOOKSIG blob into the dashboard, so Gap Widen / Z-Score signals appear in the
Signals ranking alongside the generator's RSI2/MFI rows.

Implements the exact specs from the page's BOOKS blob:
  GAPW_RSI2 / GAPW_RSI14 : ema(4/10/21) ignition sequence + stack + widening +
      pullback context + liquidity + variant RSI filter, ranked by rs252 desc
  ZSCORE_000 : close>20, avol50>1M sh, close>sma200, z50<=-1.5, rsi3<20 (Ext-31,
      paper only - book killed for real-money wiring x40/x41/x42). Rows carry
      per-name research stats from BOOKS universe.per_name with the executable
      basis factor applied, and respect the mandatory earnings no-entry rule
      when --earnings is supplied.
  BB_RUBBER  : NO LONGER SCANNED - killed 2026-08-01 by the pre-registered
      SPEC C fill-mode gate (retention 0.096, era flag, hybrid PF ~1). The
      meanrev_entry(use_bb=True) path is kept for reference only.

Input bars.json: {"SYM": [[date, open, high, low, close, volume], ...]} ascending
(dump_closes.py --ohlcv --days 400). Indicator math matches the specs exactly.
Optional earnings.json: {"SYM": "YYYY-MM-DD"} next confirmed report per symbol.

Usage:
  python3 scan_book_signals.py --bars bars.json --page index.html
      [--earnings earnings.json] [--splice]
  (--splice replaces the `const BOOKSIG = ...;` line; without it, prints JSON)
"""
import datetime
import json
import re
import sys


def ema_series(closes, n):
    a = 2.0 / (n + 1)
    out = [closes[0]]
    for c in closes[1:]:
        out.append(a * c + (1 - a) * out[-1])
    return out


def rsi(closes, n):
    if len(closes) < n + 1:
        return None
    a = 1.0 / n
    g = l = None
    for prev, cur in zip(closes, closes[1:]):
        ch = cur - prev
        gain, loss = max(ch, 0.0), max(-ch, 0.0)
        if g is None:
            g, l = gain, loss
        else:
            g = a * gain + (1 - a) * g
            l = a * loss + (1 - a) * l
    return 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def stdev(vals, n):
    if len(vals) < n:
        return None
    w = vals[-n:]
    m = sum(w) / n
    return (sum((x - m) ** 2 for x in w) / (n - 1)) ** 0.5


def crossed_above(a, b, i):
    return a[i] > b[i] and a[i - 1] <= b[i - 1]


def gapw_entry(bars, rsi_kind):
    """bars: list of [date,o,h,l,c,v]. Returns metrics dict if entry true at EOD."""
    if len(bars) < 60:
        return None
    c = [b[4] for b in bars]
    h = [b[2] for b in bars]
    lo = [b[3] for b in bars]
    v = [b[5] for b in bars]
    e4, e10, e21 = ema_series(c, 4), ema_series(c, 10), ema_series(c, 21)
    t = len(c) - 1
    # ignition: e4 crossed e21 on bar r; e10 crossed e21 on bar s; 0<=s-r<=3; t-2<=s<=t
    s_bar = next((i for i in range(t, max(t - 3, 0), -1) if crossed_above(e10, e21, i)), None)
    if s_bar is None:
        return None
    r_bar = next((i for i in range(s_bar, max(s_bar - 4, 0), -1) if crossed_above(e4, e21, i)), None)
    if r_bar is None or not (0 <= s_bar - r_bar <= 3):
        return None
    if not (e4[t] > e10[t] > e21[t]):
        return None
    if not ((e4[t] - e10[t]) > (e4[t - 1] - e10[t - 1])):
        return None
    if not (min(lo[-20:]) <= 0.93 * max(h[-40:])):
        return None
    avol = sum(v[-50:]) / min(len(v), 50)
    if avol <= 1_000_000 or c[-1] < 3:
        return None
    if rsi_kind == 2 and not ((rsi(c, 2) or 100) < 80):
        return None
    if rsi_kind == 14 and not ((rsi(c, 14) or 100) < 60):
        return None
    rs252 = (c[-1] / c[-253] - 1) * 100 if len(c) >= 253 else None
    return {"close": round(c[-1], 4), "rs252": round(rs252, 1) if rs252 is not None else None,
            "rsi": round(rsi(c, rsi_kind), 1)}


def meanrev_entry(bars, use_bb):
    if len(bars) < 210:
        return None
    c = [b[4] for b in bars]
    v = [b[5] for b in bars]
    close = c[-1]
    if close <= 20:
        return None
    if sum(v[-50:]) / 50 <= 1_000_000:
        return None
    s200 = sma(c, 200)
    if s200 is None or close <= s200:
        return None
    r3 = rsi(c, 3)
    s50, sd50 = sma(c, 50), stdev(c, 50)
    s20, sd20 = sma(c, 20), stdev(c, 20)
    z50 = (close - s50) / sd50 if sd50 else None
    if use_bb:
        # BB (reference only - book killed): ACTUAL MIO oversold gate is
        # rsi(2) < 10 (screenshot-verified 2026-08-02; the earlier port
        # encoded rsi(3) < 20).
        r2 = rsi(c, 2)
        if r2 is None or r2 >= 10:
            return None
        if s20 is None or sd20 is None or close >= s20 - 2 * sd20:
            return None
    else:
        if r3 is None or r3 >= 20:
            return None
        if z50 is None or z50 > -1.5:
            return None
    return {"close": round(close, 4), "z50": round(z50, 2) if z50 is not None else None,
            "rsi3": round(r3, 1) if r3 is not None else None}


def main():
    args = sys.argv[1:]
    def opt(name):
        return args[args.index(name) + 1] if name in args else None
    bars_path, page_path = opt("--bars"), opt("--page")
    if not bars_path or not page_path:
        sys.exit("--bars bars.json --page index.html required")
    bars = json.load(open(bars_path))
    earnings = json.load(open(opt("--earnings"))) if opt("--earnings") else {}
    page = open(page_path).read()
    books = json.loads(re.search(r"const BOOKS = (.*?);\n", page, re.S).group(1))
    S = {s["id"]: s for s in books["strategies"]}
    as_of = max((v[-1][0] for v in bars.values() if v), default=None)

    def earnings_imminent(sym):
        """Mandatory z-score rule: no entry if a report falls on the signal day
        or before the next session (weekend-aware). No date -> no constraint."""
        nxt = earnings.get(sym)
        if not nxt or not as_of:
            return False
        d0 = datetime.date.fromisoformat(as_of)
        nx = d0 + datetime.timedelta(days=1)
        while nx.weekday() >= 5:
            nx += datetime.timedelta(days=1)
        return as_of <= nxt <= nx.isoformat()

    rows = []
    for sid, strat, kind in [("gap_widen_rsi2", "GAPW_RSI2", 2),
                             ("gap_widen_rsi14", "GAPW_RSI14", 14)]:
        u = S[sid]["universe"]
        stats = {e["signal"]: e for e in u.get("qualified", [])}
        veh = {e["signal"]: e["trade"] for e in u.get("qualified", []) if e["trade"] != e["signal"]}
        cands = []
        for sym in {e["signal"] for e in u.get("qualified", [])} | set(u.get("scan", [])):
            b = bars.get(sym)
            if not b or b[-1][0] != as_of:
                continue
            m = gapw_entry(b, kind)
            if m:
                e = stats.get(sym)
                cands.append({"sym": sym, "strat": strat, "state": "TAKE", **m,
                              "vehicle": veh.get(sym),
                              "n": e and e["n"], "win": e and round(e["win"] * 100, 1),
                              "avg": e and round(e["avg_net"] * 100, 2),
                              "pf": e and e.get("pf")})
        cands.sort(key=lambda x: -(x["rs252"] if x["rs252"] is not None else -1e9))
        for i, x in enumerate(cands):
            x["book_rank"] = i + 1
        rows += cands

    # Z-Score only. BB was killed 2026-08-01 (SPEC C fill-mode gate) and per the
    # pre-registered rule drops from this scanner rather than lingering as paper.
    zuni = S["zscore_000"]["universe"]
    zstats = {e["signal"]: e for e in zuni.get("per_name", [])}
    zfactor = S["zscore_000"].get("exec_basis_factor") or 1.0
    # x44/x45 (2026-08-02): the paper book scans the ACTUAL MIO universe -
    # preferring the x45 live list (delisted removed, session-fetched names
    # included), then the x44 runnable subset, then Ext-31 as last fallback.
    zscan = (zuni.get("mio_universe_live") or zuni.get("mio_universe_runnable")
             or zuni.get("extended_31", []))
    cands = []
    for sym in zscan:
        b = bars.get(sym)
        if not b or b[-1][0] != as_of:
            continue
        m = meanrev_entry(b, use_bb=False)
        if not m:
            continue
        if earnings_imminent(sym):
            cands.append({"sym": sym, "strat": "ZSCORE", "state": "PASS-EARNINGS", **m})
            continue
        e = zstats.get(sym)
        cands.append({"sym": sym, "strat": "ZSCORE", "state": "TAKE", **m,
                      "n": e and e["n"], "win": e and round(e["win"] * 100, 1),
                      "avg": e and round(e["avg_net"] * 100 * zfactor, 2),
                      "pf": e and e.get("pf")})
    cands.sort(key=lambda x: x["rsi3"])
    for i, x in enumerate(cands):
        x["book_rank"] = i + 1
    rows += cands

    sig = {"as_of": as_of, "rows": rows}
    line = "const BOOKSIG = " + json.dumps(sig, separators=(",", ":")) + ";"
    assert "</" not in line
    if "--splice" in args:
        page2, n = re.subn(r"const BOOKSIG = .*?;\n", lambda _m: line + "\n", page, count=1, flags=re.S)
        if n != 1:
            sys.exit("no `const BOOKSIG = ...;` line in page")
        open(page_path, "w").write(page2)
        print(f"BOOKSIG spliced: {len(rows)} book signals as of {as_of}", file=sys.stderr)
    else:
        print(line)


if __name__ == "__main__":
    main()
