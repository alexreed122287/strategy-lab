#!/usr/bin/env python3
"""robert_vs_x45.py — RESEARCH ONLY, read-only. Head-to-head on identical
terms: same 90-name universe, same bars, same portfolio model, same costs.

Per-trade averages cannot answer "which has the higher CAGR / risk-adjusted
return" — that needs capital, slots, compounding and a daily equity curve.
So both rules run through one simulator:

  $100,000 · 3 concurrent slots · 1/3 of equity per slot · signal on bar t,
  fill at the OPEN of t+1 · T+1 settled cash · daily mark-to-market for the
  drawdown · when more signals than slots, each rule ranks by its own
  most-oversold-first (Robert by RSI(2), x45 by RSI(5)).

ROBERT   entry RSI(2)<10 & close>SMA200 [+ optional RS252>+40, earnings-7d,
         IV proxy<=60]; skip if next open > signal-bar SMA5
         exit  close>SMA5 OR 10 bars
X45      entry close<SMA5 & RSI(5)<27 & SMA200 rising & SMA2[t-1]>SMA200
         exit  (green AND RSI(2)>70 AND close>EMA5) OR 10 bars

x45 fires ~4x more often, so the per-side cost assumption is not neutral
between them: both are run at 5bp and 15bp per side.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
CACHE = "/tmp/robert_hc_bars.json"
CAP0 = 100_000.0
SLOTS = 3
IV_CAP, RS_THR = 0.60, 0.40

import robert_scan as RS                                     # noqa: E402

bars = json.load(open(CACHE))
earn = json.load(open(os.path.join(ROOT, "data", "robert_earnings.json")))
uni = [s.strip() for s in
       open(os.path.join(ROOT, "robert_universe.txt")).read()
       .replace("\n", " ").split(",") if s.strip()]
uni = [s for s in uni if s in bars and len(bars[s]) > 300]
SPY = bars["SPY"]
spy_dates = [r[0] for r in SPY]
spy_c = [r[4] for r in SPY]
spy_i = {d: i for i, d in enumerate(spy_dates)}


def sma_arr(c, n):
    out, run = [None] * len(c), 0.0
    for i, v in enumerate(c):
        run += v
        if i >= n:
            run -= c[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def ema_arr(c, n):
    out = [None] * len(c)
    if len(c) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(c[:n]) / n
    out[n - 1] = e
    for i in range(n, len(c)):
        e = c[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_arr(c, n):
    out = [None] * len(c)
    g = l = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            g += up / n
            l += dn / n
            if i < n:
                continue
        else:
            g = (g * (n - 1) + up) / n
            l = (l * (n - 1) + dn) / n
        out[i] = 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)
    return out


IND = {}
for s in uni:
    seq = bars[s]
    c = [r[4] for r in seq]
    IND[s] = {"d": [r[0] for r in seq], "o": [r[1] for r in seq], "c": c,
              "i": {r[0]: k for k, r in enumerate(seq)},
              "rsi2": rsi_arr(c, 2), "rsi5": rsi_arr(c, 5),
              "sma2": sma_arr(c, 2), "sma5": sma_arr(c, 5),
              "sma200": sma_arr(c, 200), "ema5": ema_arr(c, 5),
              "rv": None}
    ed = set(earn.get(s, []))
    IND[s]["earn"] = sorted(dt.date.fromisoformat(x) for x in ed)


def near_earn(s, d):
    d0 = dt.date.fromisoformat(d)
    return any(0 <= (e - d0).days <= 7 for e in IND[s]["earn"])


def signal(s, i, rule, gates):
    """True if bar i is an entry signal for `rule`."""
    X = IND[s]
    c, d = X["c"], X["d"]
    if rule == "robert":
        if X["rsi2"][i] is None or X["rsi2"][i] >= 10:
            return None
        if X["sma200"][i] is None or c[i] <= X["sma200"][i]:
            return None
        rank = X["rsi2"][i]
    else:
        if X["sma5"][i] is None or c[i] >= X["sma5"][i]:
            return None
        if X["rsi5"][i] is None or X["rsi5"][i] >= 27:
            return None
        if (X["sma200"][i] is None or X["sma200"][i - 1] is None
                or X["sma200"][i] <= X["sma200"][i - 1]):
            return None
        if X["sma2"][i - 1] is None or X["sma2"][i - 1] <= X["sma200"][i]:
            return None
        rank = X["rsi5"][i]
    if gates:
        si = spy_i.get(d[i])
        if si is None or si < 253 or i < 253:
            return None
        rs = c[i] / c[i - 252] - 1 - (spy_c[si] / spy_c[si - 252] - 1)
        if rs <= RS_THR:
            return None
        if near_earn(s, d[i]):
            return None
        rv = RS.rv_blend(c[:i + 1])
        if rv is None or rv > IV_CAP:
            return None
    return rank


def exit_hit(s, i, rule, entry_px):
    X = IND[s]
    c = X["c"]
    if rule == "robert":
        return X["sma5"][i] is not None and c[i] > X["sma5"][i]
    return (c[i] / entry_px - 1 >= 0 and X["rsi2"][i] is not None
            and X["rsi2"][i] > 70 and X["ema5"][i] is not None
            and c[i] > X["ema5"][i])


def sim(rule, gates, cost, start="2005-01-01"):
    dates = [d for d in spy_dates if d >= start]
    cash, pending, pos = CAP0, [], {}
    eq_curve, trades = [], []
    queued = []
    for d in dates:
        cash += sum(a for dd, a in pending if dd <= d)
        pending = [(dd, a) for dd, a in pending if dd > d]
        # ---- exits at today's close
        for s in list(pos):
            X = IND[s]
            i = X["i"].get(d)
            if i is None:
                continue
            p = pos[s]
            held = i - p["i0"]
            if exit_hit(s, i, rule, p["px"]) or held >= 10:
                px = X["c"][i] * (1 - cost)
                proceeds = p["sh"] * px
                pending.append((_plus1(d), proceeds))
                trades.append(px / p["px"] - 1)
                del pos[s]
        # ---- fills at today's open from yesterday's queue
        eq = cash + sum(pending_amt for _, pending_amt in pending)
        for s in list(pos):
            i = IND[s]["i"].get(d)
            if i is not None:
                eq += pos[s]["sh"] * IND[s]["c"][i]
        for rank, s in sorted(queued):
            if len(pos) >= SLOTS or s in pos:
                continue
            X = IND[s]
            i = X["i"].get(d)
            if i is None or i == 0:
                continue
            op = X["o"][i]
            s5prev = X["sma5"][i - 1]
            if s5prev is not None and op > s5prev:      # gap-recovered skip
                continue
            budget = min(eq / SLOTS, cash)
            px = op * (1 + cost)
            sh = int(budget // px) if px > 0 else 0
            if sh < 1:
                continue
            cash -= sh * px
            pos[s] = {"sh": sh, "px": px, "i0": i}
        queued = []
        # ---- tonight's signals -> tomorrow's queue
        for s in uni:
            if s in pos:
                continue
            i = IND[s]["i"].get(d)
            if i is None or i < 260:
                continue
            r = signal(s, i, rule, gates)
            if r is not None:
                queued.append((r, s))
        # ---- mark to market
        mtm = cash + sum(a for _, a in pending)
        for s in pos:
            i = IND[s]["i"].get(d)
            mtm += pos[s]["sh"] * (IND[s]["c"][i] if i is not None
                                   else pos[s]["px"])
        eq_curve.append(mtm)
    final = eq_curve[-1]
    yrs = len(eq_curve) / 252.0
    cagr = (final / CAP0) ** (1 / yrs) - 1
    peak = mdd = 0.0
    for v in eq_curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    w = [t for t in trades if t > 0]
    l = [t for t in trades if t <= 0]
    pf = (sum(w) / abs(sum(l))) if l and sum(l) else 99.0
    rets = [eq_curve[i] / eq_curve[i - 1] - 1 for i in range(1, len(eq_curve))]
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
    sharpe = (mu * 252) / (sd * math.sqrt(252)) if sd else 0.0
    return {"cagr": cagr, "mdd": mdd,
            "calmar": (cagr / mdd if mdd else 0.0), "sharpe": sharpe,
            "pf": pf, "wr": len(w) / len(trades) * 100 if trades else 0,
            "n": len(trades), "final": final,
            "exposure": sum(1 for v in eq_curve if v) and None}


def _plus1(d):
    i = spy_i.get(d)
    return spy_dates[i + 1] if i is not None and i + 1 < len(spy_dates) else d


def main():
    print(f"universe {len(uni)} names · {spy_dates[0]} -> {spy_dates[-1]} · "
          f"${CAP0:,.0f} · {SLOTS} slots\n")
    for cost, clab in ((0.0005, "5bp/side"), (0.0015, "15bp/side")):
        print(f"{'='*94}\nCOSTS {clab}")
        print(f"{'='*94}")
        print(f"{'strategy':>28s} {'n':>6s} {'win%':>6s} {'PF':>6s} "
              f"{'CAGR':>8s} {'maxDD':>7s} {'Calmar':>7s} {'Sharpe':>7s} "
              f"{'final $':>11s}")
        rows = {}
        for rule, gates, label in (
                ("robert", True, "ROBERT (full gates)"),
                ("robert", False, "Robert, no RS/earn/IV"),
                ("x45", False, "X45 (as written)"),
                ("x45", True, "X45 + RS252/earn/IV")):
            r = sim(rule, gates, cost)
            rows[label] = r
            print(f"{label:>28s} {r['n']:>6d} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
                  f"{r['cagr']*100:>7.2f}% {r['mdd']*100:>6.1f}% "
                  f"{r['calmar']:>7.2f} {r['sharpe']:>7.2f} "
                  f"{r['final']:>11,.0f}")
        if cost == 0.0005:
            best = {}
            for k, fn in (("PF", lambda r: r["pf"]),
                          ("CAGR", lambda r: r["cagr"]),
                          ("win%", lambda r: r["wr"]),
                          ("Calmar", lambda r: r["calmar"]),
                          ("Sharpe", lambda r: r["sharpe"])):
                w = max(rows, key=lambda l: fn(rows[l]))
                best[k] = (w, fn(rows[w]))
            print("\n  winners at 5bp:")
            for k, (w, v) in best.items():
                print(f"    {k:>7s}: {w}  ({v:.2f})")
        print()


if __name__ == "__main__":
    main()
