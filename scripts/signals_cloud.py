#!/usr/bin/env python3
"""Cloud port of the Mac signal generator, wired per owner approval 2026-08-14.

THE MATH IS A LINE-FOR-LINE PORT of the real generator - scripts/signals.py and
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

STDLIB ONLY - this file must import nothing beyond the standard library.
The first wired build (run #26, 2026-08-14) died on `import numpy`: the
Actions runner image has no numpy/pandas and the workflow deliberately has
no pip step (every build script is stdlib-only). The pandas expressions
were rewritten as explicit loops; the rewrite was validated two ways on
2026-08-14 before this replaced the pandas version:
  * byte-identical signals array vs the pandas implementation's saved
    output on the same simulated 07-31 inputs, and
  * the same wiring fidelity verdict vs the Mac's published 07-31 blob
    (145/145 comparable rows, 0 field mismatches).
NaN semantics: indicators carry None where pandas carried NaN, and every
comparison treats None as False, matching NaN comparison semantics. Two
deliberate deltas, both on data that never occurs in clean Tradier bars:
an interior null bar freezes the EWM state (pandas ewm ignore_na=False
would renormalize the next weight), and a malformed earnings date is
treated as no-earnings instead of crashing the run. Both err toward
emitting nothing rather than emitting wrong.

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
import math
import os
import re
import sys
from datetime import date, datetime

VEHICLES = {
    "SMH": ("SOXL", 3, 0.080), "SPY": ("UPRO", 3, 0.060),
    "QQQ": ("TQQQ", 3, 0.052), "XLK": ("TECL", 3, 0.062),
    "XBI": ("LABU", 3, 0.100), "KRE": ("DPST", 3, 0.100),
    "AMD": ("AMUU", 2, 0.101), "MU": ("MULL", 2, 0.170),
    "AAPL": ("AAPU", 2, 0.101), "NFLX": ("NFXL", 2, 0.101),
    "MSFT": ("MSFU", 2, 0.101), "GOOGL": ("GGLL", 2, 0.101),
}


# ---- None-aware primitives standing in for pandas NaN semantics ----

def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _lt(a, b):
    return a is not None and a < b


def _le(a, b):
    return a is not None and a <= b


def _gt(a, b):
    return a is not None and a > b


def _diff(xs):
    out = [None] * len(xs)
    for i in range(1, len(xs)):
        if xs[i] is not None and xs[i - 1] is not None:
            out[i] = xs[i] - xs[i - 1]
    return out


def _ewm_mean(xs, alpha, min_periods=0):
    # pandas ewm(adjust=False): y = (1-a)*y_prev + a*x, seeded at the first
    # valid value; min_periods masks output until that many valid points.
    out = [None] * len(xs)
    state = None
    cnt = 0
    for i, x in enumerate(xs):
        if x is None:
            if state is not None and cnt >= min_periods:
                out[i] = state
            continue
        state = x if state is None else (1.0 - alpha) * state + alpha * x
        cnt += 1
        if cnt >= min_periods:
            out[i] = state
    return out


def _rolling(xs, n, want):
    # want: "sum" | "mean" | "std" (sample std, ddof=1, like pandas).
    # A window containing any None yields None, like a NaN-tainted window.
    out = [None] * len(xs)
    last_bad = -1
    for i, x in enumerate(xs):
        if x is None:
            last_bad = i
        if i >= n - 1 and last_bad <= i - n:
            w = xs[i - n + 1:i + 1]
            s = math.fsum(w)
            if want == "sum":
                out[i] = s
            elif want == "mean":
                out[i] = s / n
            else:
                m = s / n
                var = math.fsum((v - m) * (v - m) for v in w) / (n - 1)
                out[i] = math.sqrt(var)
    return out


# ---- indicator math: ported line-for-line from scan.py ----

def wilder_rsi(close, n):
    d = _diff(close)
    up = [None if x is None else (x if x > 0.0 else 0.0) for x in d]
    dn = [None if x is None else (-x if x < 0.0 else 0.0) for x in d]
    ru = _ewm_mean(up, 1.0 / n, min_periods=n)
    rd = _ewm_mean(dn, 1.0 / n, min_periods=n)
    out = [None] * len(close)
    for i in range(len(close)):
        a, b = ru[i], rd[i]
        if a is None or b is None:
            continue
        if b == 0.0:
            # pandas: ru/0 -> inf -> rsi 100; 0/0 -> NaN
            out[i] = 100.0 if a > 0.0 else None
        else:
            out[i] = 100.0 - 100.0 / (1.0 + a / b)
    return out


def mfi(h, l, c, v, n=3):
    size = len(c)
    tp = [None] * size
    mf = [None] * size
    for i in range(size):
        if h[i] is not None and l[i] is not None and c[i] is not None:
            tp[i] = (h[i] + l[i] + c[i]) / 3.0
            if v[i] is not None:
                mf[i] = tp[i] * v[i]
    # mf.where(tp > tp.shift(1), 0.0): a False/NaN condition gives 0.0,
    # a True condition keeps mf even if mf itself is None.
    up = [0.0] * size
    dn = [0.0] * size
    for i in range(1, size):
        if tp[i] is not None and tp[i - 1] is not None:
            if tp[i] > tp[i - 1]:
                up[i] = mf[i]
            elif tp[i] < tp[i - 1]:
                dn[i] = mf[i]
    ru = _rolling(up, n, "sum")
    rd = _rolling(dn, n, "sum")
    out = [None] * size
    for i in range(size):
        a, b = ru[i], rd[i]
        if a is None or b is None or b == 0.0:  # rd.replace(0, nan)
            continue
        out[i] = 100.0 - 100.0 / (1.0 + a / b)
    return out


def features(bars):
    c, h, l, v = bars["c"], bars["h"], bars["l"], bars["v"]
    size = len(c)
    f = {"c": c}
    f["sma200"] = _rolling(c, 200, "mean")
    f["sma5"] = _rolling(c, 5, "mean")
    f["e5"] = _ewm_mean(c, 2.0 / 6.0)
    f["e7"] = _ewm_mean(c, 2.0 / 8.0)
    f["rsi2"] = wilder_rsi(c, 2)
    f["rsi3"] = wilder_rsi(c, 3)
    f["mfi3"] = mfi(h, l, c, v)
    m50 = _rolling(c, 50, "mean")
    s50 = _rolling(c, 50, "std")
    z = [None] * size
    for i in range(size):
        if c[i] is not None and m50[i] is not None and s50[i] not in (None, 0.0):
            z[i] = (c[i] - m50[i]) / s50[i]
    f["z"] = z
    f["av50"] = _rolling(v, 50, "mean")
    cv = [None if c[i] is None or v[i] is None else c[i] * v[i]
          for i in range(size)]
    f["dvol50"] = _rolling(cv, 50, "mean")
    return f


def _liquid(f, i):
    return (f["av50"][i] is not None and f["av50"][i] >= 3e5
            and f["dvol50"][i] is not None and f["dvol50"][i] >= 5e6)


STRATS = {
    "RSI2": {"entry": lambda f, i: (_lt(f["rsi2"][i], 10.0)
                                    and _gt(f["c"][i], f["sma200"][i])
                                    and _liquid(f, i))},
    "MFI": {"entry": lambda f, i: (_lt(f["mfi3"][i], 20.0)
                                   and _gt(f["c"][i], f["sma200"][i])
                                   and _liquid(f, i))},
    "ZSCORE": {"entry": lambda f, i: (_gt(f["c"][i], 20.0)
                                      and _gt(f["av50"][i], 1e6)
                                      and _gt(f["c"][i], f["sma200"][i])
                                      and _le(f["z"][i], -1.5)
                                      and _lt(f["rsi3"][i], 20.0)
                                      and _liquid(f, i))},
}


def continuity_ok(dates, ref_days_per_year=250, start=date(2019, 1, 1),
                  min_cov=0.95):
    sub = [d for d in dates if d >= start]
    if len(sub) < 60:
        return False
    span_years = (sub[-1] - sub[0]).days / 365.25
    expected = span_years * ref_days_per_year
    return expected <= 0 or len(sub) >= min_cov * expected


# ---- cloud loaders (the only non-verbatim part) ----

def load_bars(bars, sym):
    rec = bars.get(sym)
    if not rec:
        return None
    seen = {}
    for row in rec:  # drop_duplicates("date") keeps the first occurrence
        k = str(row[0])[:10]
        if k not in seen:
            seen[k] = row
    dates, o, h, l, c, v = [], [], [], [], [], []
    for k in sorted(seen):
        row = seen[k]
        dates.append(date.fromisoformat(k))
        o.append(_f(row[1]))
        h.append(_f(row[2]))
        l.append(_f(row[3]))
        c.append(_f(row[4]))
        v.append(_f(row[5]))
    return {"dates": dates, "o": o, "h": h, "l": l, "c": c, "v": v}


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
        b = load_bars(bars, sym)
        # min_bars mirrors the generator's len>=320 gate; the fetch window must
        # clear it (600 calendar days ~= 410 bars) or the whole feed fails
        # closed below rather than emitting warmup-skewed indicators.
        if b is None or len(b["dates"]) < min_bars:
            continue
        if not continuity_ok(b["dates"]):
            continue
        covered += 1
        f = features(b)
        i = len(b["dates"]) - 1
        asof = b["dates"][i]
        c, s200 = f["c"][i], f["sma200"][i]
        if s200 is None:  # np.isfinite(sma200) gate
            continue
        above = c is not None and c > s200
        r2, m3, z, r3 = f["rsi2"][i], f["mfi3"][i], f["z"][i], f["rsi3"][i]
        av = f["av50"][i]
        nxt = earn_next.get(sym)
        earn = False
        if nxt:
            try:  # a malformed date means no-earnings, not a dead feed
                earn = 0 <= (date.fromisoformat(nxt) - asof).days <= 4
            except ValueError:
                earn = False
        for strat, trig, watch, depth in [
            ("RSI2", _lt(r2, 10.0), _lt(r2, 15.0), r2),
            ("MFI", _lt(m3, 20.0), _lt(m3, 30.0), m3),
            ("ZSCORE", (_gt(c, 20.0) and _gt(av, 1e6) and _le(z, -1.5)
                        and _lt(r3, 20.0)),
             (_gt(c, 20.0) and _gt(av, 1e6) and _le(z, -1.25)
              and _lt(r3, 25.0)), z),
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
                   "as_of": asof.isoformat(),
                   "age": age,
                   "buy_date": b["dates"][i - age + 1].isoformat() if age else None,
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

    # Port of demote_stale() added to the Mac generator on 2026-08-14 (lab
    # repo commit 415a884) - this file's parity contract includes it. `age`
    # counts from the symbol's OWN last bar, so a ticker whose feed froze
    # reports age=1/new_today=true forever: EA sat in the TAKE list for ten
    # days after its take-private closed. Universe removal (PR #78) patched
    # that one name; this is the class fix. The market's last close is the max
    # as_of across the corpus, so one frozen name cannot drag it backwards.
    market_asof = max((r["as_of"] for r in signals), default=None)
    for r in signals:
        lag = (date.fromisoformat(market_asof)
               - date.fromisoformat(r["as_of"])).days
        r["stale_days"] = max(lag, 0)
        if lag > 0:
            r["state"] = "PASS-STALE"
            r["new_today"] = False

    order = {"TAKE": 0, "PASS-EARNINGS": 1, "WATCH": 2, "PASS-STALE": 4}
    signals.sort(key=lambda r: (order.get(r["state"], 3), r["depth"]))
    blob = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M")
            + " cloud generator",
            "market_asof": market_asof,
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
