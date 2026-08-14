#!/usr/bin/env python3
"""Cloud port of the Mac signal generator, wired per owner approval 2026-08-14.

THE MATH IS VENDORED VERBATIM from the real generator - scripts/signals.py and
scripts/scan.py in the strategy-lab-dashboard repo - which was located, read,
and executed against the 07-31 brain mirror on 2026-08-14: 145 of 145
comparable rows matched the Mac's published blob on all seven fields (see
signals_fidelity_gate.py's docstring for the full record). Only the three
LOADERS differ, because the cloud has different plumbing:

    bars      /tmp/bars.json from dump_closes.py (Tradier split-only daily -
              the brain's own native basis, per scan.py's data-grade table)
    earnings  /tmp/earnings.json from next_earnings.py ({sym: next-date}),
              replacing the per-symbol brain earnings files
    universe  data/signals_universe.json - the Mac's membership rule
              (brain names minus manifest-flagged minus full-history
              len/continuity failures, plus observed x26-side names) baked
              from the 08-01 mirror. Baked, not recomputed, because the
              cloud's ~410-bar window is too short to catch pre-2024 splices
              (SW) that the Mac's full history rejects.

Known, documented deltas vs the Mac feed:
  * x26-only names beyond the 33 observed ones are absent until the brain
    mirror or the x26 snapshot is pushed current.
  * Wilder/EWM indicators warm up from the fetch start rather than 2019;
    at >=320 bars the drift is below the 0.02 display rounding (verified in
    the wiring fidelity test on 07-31).

Fail-quiet by design: any error leaves the existing SIGNALS blob untouched,
which the page already handles as a stale feed (freshness gate + banner).

Usage:
  signals_cloud.py --bars /tmp/bars.json --earnings /tmp/earnings.json \
      [--universe data/signals_universe.json] [--out out.json] \
      [--splice index.html] [--min-bars 320]
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd

# ---- indicator math: verbatim from strategy-lab-dashboard/scripts/scan.py ----

VEHICLES = {
    "SMH": ("SOXL", 3, 0.080), "SPY": ("UPRO", 3, 0.060),
    "QQQ": ("TQQQ", 3, 0.052), "XLK": ("TECL", 3, 0.062),
    "XBI": ("LABU", 3, 0.100), "KRE": ("DPST", 3, 0.100),
    "AMD": ("AMUU", 2, 0.101), "MU": ("MULL", 2, 0.170),
    "AAPL": ("AAPU", 2, 0.101), "NFLX": ("NFXL", 2, 0.101),
    "MSFT": ("MSFU", 2, 0.101), "GOOGL": ("GGLL", 2, 0.101),
}


def wilder_rsi(close, n):
    d = close.diff()
    ru = d.clip(lower=0.0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rd = (-d).clip(lower=0.0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + ru / rd)


def mfi(h, l, c, v, n=3):
    tp = (h + l + c) / 3.0
    mf = tp * v
    up = mf.where(tp > tp.shift(1), 0.0)
    dn = mf.where(tp < tp.shift(1), 0.0)
    ru = up.rolling(n).sum()
    rd = dn.rolling(n).sum()
    return 100 - 100 / (1 + ru / rd.replace(0.0, np.nan))


def features(df):
    c = df["c"]
    f = pd.DataFrame(index=df.index)
    f["c"] = c
    f["sma200"] = c.rolling(200).mean()
    f["sma5"] = c.rolling(5).mean()
    f["e5"] = c.ewm(span=5, adjust=False).mean()
    f["e7"] = c.ewm(span=7, adjust=False).mean()
    f["rsi2"] = wilder_rsi(c, 2)
    f["rsi3"] = wilder_rsi(c, 3)
    f["mfi3"] = mfi(df["h"], df["l"], c, df["v"])
    f["z"] = (c - c.rolling(50).mean()) / c.rolling(50).std()
    f["av50"] = df["v"].rolling(50).mean()
    f["dvol50"] = (c * df["v"]).rolling(50).mean()
    return f


def _liquid(f, i):
    return f["av50"].iat[i] >= 3e5 and f["dvol50"].iat[i] >= 5e6


STRATS = {
    "RSI2": {"entry": lambda f, i: (f["rsi2"].iat[i] < 10
                                    and f["c"].iat[i] > f["sma200"].iat[i]
                                    and _liquid(f, i))},
    "MFI": {"entry": lambda f, i: (f["mfi3"].iat[i] < 20
                                   and f["c"].iat[i] > f["sma200"].iat[i]
                                   and _liquid(f, i))},
    "ZSCORE": {"entry": lambda f, i: (f["c"].iat[i] > 20 and f["av50"].iat[i] > 1e6
                                      and f["c"].iat[i] > f["sma200"].iat[i]
                                      and f["z"].iat[i] <= -1.5
                                      and f["rsi3"].iat[i] < 20
                                      and _liquid(f, i))},
}


def continuity_ok(df, ref_days_per_year=250, start="2019-01-01", min_cov=0.95):
    sub = df.loc[start:]
    if len(sub) < 60:
        return False
    span_years = (sub.index[-1] - sub.index[0]).days / 365.25
    expected = span_years * ref_days_per_year
    return expected <= 0 or len(sub) >= min_cov * expected


# ---- cloud loaders (the only non-verbatim part) ----

def load_bars(bars, sym):
    rec = bars.get(sym)
    if not rec:
        return None
    df = pd.DataFrame(rec, columns=["date", "o", "h", "l", "c", "v"])
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates("date").set_index("date").sort_index()


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    bars_p = opt("--bars") or sys.exit("--bars required")
    earn_p = opt("--earnings")
    uni_p = opt("--universe", "data/signals_universe.json")
    out_p = opt("--out")
    page_p = opt("--splice")
    min_bars = int(opt("--min-bars", "320"))

    bars = json.load(open(bars_p))
    earn_next = {}
    if earn_p and os.path.exists(earn_p):
        try:
            earn_next = {k: str(v)[:10] for k, v in json.load(open(earn_p)).items()}
        except Exception:
            earn_next = {}
    uni = json.load(open(uni_p))["names"]

    signals = []
    covered = 0
    for sym in uni:
        df = load_bars(bars, sym)
        # min_bars mirrors the generator's len>=320 gate; the fetch window must
        # clear it (600 calendar days ~= 410 bars) or the whole feed fails
        # closed below rather than emitting warmup-skewed indicators.
        if df is None or len(df) < min_bars:
            continue
        if not continuity_ok(df):
            continue
        covered += 1
        f = features(df)
        i = len(f) - 1
        asof = f.index[i]
        c, s200 = f["c"].iat[i], f["sma200"].iat[i]
        if not np.isfinite(s200):
            continue
        above = c > s200
        r2, m3, z, r3 = (f["rsi2"].iat[i], f["mfi3"].iat[i],
                         f["z"].iat[i], f["rsi3"].iat[i])
        av = f["av50"].iat[i]
        nxt = earn_next.get(sym)
        earn = bool(nxt) and 0 <= (pd.Timestamp(nxt) - asof).days <= 4
        for strat, trig, watch, depth in [
            ("RSI2", r2 < 10, r2 < 15, r2),
            ("MFI", m3 < 20, m3 < 30, m3),
            ("ZSCORE", (c > 20 and av > 1e6 and z <= -1.5 and r3 < 20),
             (c > 20 and av > 1e6 and z <= -1.25 and r3 < 25), z),
        ]:
            if not above:
                continue
            state = "TAKE" if trig else ("WATCH" if watch else None)
            if state is None:
                continue
            if earn and strat == "ZSCORE":
                state = "PASS-EARNINGS"
            age = 0
            if trig:
                k = i
                while k > max(i - 30, 210) and STRATS[strat]["entry"](f, k):
                    age += 1
                    k -= 1
            rec = {"sym": sym, "strat": strat, "state": state,
                   "depth": round(float(depth), 2),
                   "close": round(float(c), 2),
                   "as_of": str(asof.date()),
                   "age": age,
                   "buy_date": str(f.index[i - age + 1].date()) if age else None,
                   "new_today": age == 1,
                   "earnings_soon": bool(earn)}
            if sym in VEHICLES and strat == "RSI2":
                rec["vehicle"] = VEHICLES[sym][0]
            signals.append(rec)

    # fail closed on thin coverage: a half-fetched bars file must not publish
    # as a full scan (the stale-cache lesson, again)
    if covered < 0.6 * len(uni):
        sys.exit("fail-closed: only %d of %d universe names had usable bars"
                 % (covered, len(uni)))

    order = {"TAKE": 0, "PASS-EARNINGS": 1, "WATCH": 2}
    signals.sort(key=lambda r: (order.get(r["state"], 3), r["depth"]))
    blob = {"generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
            + " cloud generator",
            "signals": signals}
    if out_p:
        json.dump(blob, open(out_p, "w"), indent=1)
    if page_p:
        html = open(page_p).read()
        line = "const SIGNALS = " + json.dumps(blob, separators=(",", ":")) + ";"
        assert "</" not in line
        html2, n = re.subn(r"const SIGNALS = .*?;\n", lambda _m: line + "\n",
                           html, count=1, flags=re.S)
        assert n == 1, "no SIGNALS line found"
        open(page_p, "w").write(html2)
    print("signals_cloud: %d rows from %d/%d names, as_of %s"
          % (len(signals), covered, len(uni),
             max((r["as_of"] for r in signals), default="n/a")), file=sys.stderr)


if __name__ == "__main__":
    main()
