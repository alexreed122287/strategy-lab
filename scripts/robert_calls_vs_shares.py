#!/usr/bin/env python3
"""robert_calls_vs_shares.py — RESEARCH ONLY. The apples-to-apples the prior
vehicle study never ran.

robert.html compares "ROBERT" (90 single names, DITM calls) against
"Shares (live)" — but that comparator is the Agentic leveraged-ETF config
(SMH->SOXL, SPY->UPRO, QQQ->TQQQ, XLK->TECL, 2 slots x 27.5%, ~4.5% average
capital deployed). Three things differ at once: vehicle, universe, and
capital deployment. A 6x deployment gap alone explains most of a 6x CAGR gap.

This holds universe, signal, exit, slots and deployment FIXED and varies
only the vehicle:

  same 90 names · same Robert rules · same $100k / 3 slots / 1-3 equity
  SHARES : buy the stock at the next open, sell at the exit close
  CALLS  : same dates, DITM call (shallowest strike with extrinsic < 20% of
           premium, first monthly 30-50 DTE), premium sized to the slot,
           priced at MID / half the quoted spread / full quoted spread using
           each name's live measured spread from data/robert_chain_check.json
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
sys.path.insert(0, "/Users/alex/repos/agentic-cron")

import rsi2_call_model as cm                                  # noqa: E402
import robert_scan as RS                                      # noqa: E402

BARS = json.load(open("/tmp/robert_hc_bars.json"))
EARN = json.load(open(os.path.join(ROOT, "data", "robert_earnings.json")))
CH = json.load(open(os.path.join(ROOT, "data", "robert_chain_check.json")))
UNI = [s.strip() for s in
       open(os.path.join(ROOT, "robert_universe.txt")).read()
       .replace("\n", " ").split(",") if s.strip()]
UNI = [s for s in UNI if s in BARS and len(BARS[s]) > 300]
SPY = BARS["SPY"]
SPY_C = [r[4] for r in SPY]
SPY_D = [r[0] for r in SPY]
SPY_I = {d: i for i, d in enumerate(SPY_D)}
CAP0, SLOTS = 100_000.0, 3
K_IV, CRUSH, COMM = 1.25, 0.90, 0.0005

HS = {}
for s, v in (CH.get("detail") or {}).items():
    t = v.get("target") if isinstance(v, dict) else None
    if t and t.get("spread_pct") is not None:
        HS[s] = t["spread_pct"] / 2.0


def sma_a(c, n):
    out, run = [None] * len(c), 0.0
    for i, v in enumerate(c):
        run += v
        if i >= n:
            run -= c[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def rsi_a(c, n):
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


def third_friday(y, m):
    d = dt.date(y, m, 1)
    f = [d + dt.timedelta(days=x) for x in range(31)
         if (d + dt.timedelta(days=x)).month == m
         and (d + dt.timedelta(days=x)).weekday() == 4]
    return f[2]


def first_monthly(ds, lo=30, hi=50):
    d0 = dt.date.fromisoformat(ds)
    for k in range(6):
        y, m = d0.year + (d0.month - 1 + k) // 12, (d0.month - 1 + k) % 12 + 1
        tf = third_friday(y, m)
        if lo <= (tf - d0).days <= hi:
            return (tf - d0).days
    return None


def pick(S, sig, T):
    for mult in [x / 200 for x in range(200, 99, -1)]:
        K = S * mult
        prem = cm.bs_call(S, K, T, sig)
        if prem <= 0.01:
            continue
        if (prem - max(S - K, 0.0)) / prem < 0.20:
            return K, prem
    return None


def hv20(c, i):
    if i < 20:
        return None
    r = [math.log(c[j] / c[j - 1]) for j in range(i - 19, i + 1)]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / len(r) * 252)


def build():
    """Robert trades on the 90 names, with both vehicles priced."""
    out = []
    for s in UNI:
        seq = BARS[s]
        d = [r[0] for r in seq]
        o = [r[1] for r in seq]
        c = [r[4] for r in seq]
        r2 = rsi_a(c, 2)
        s5, s200 = sma_a(c, 5), sma_a(c, 200)
        ev = [dt.date.fromisoformat(x) for x in EARN.get(s, [])]
        i, held = 260, -1
        while i < len(c) - 1:
            if i <= held:
                i += 1
                continue
            if (r2[i] is None or r2[i] >= 10 or s200[i] is None
                    or c[i] <= s200[i]):
                i += 1
                continue
            si = SPY_I.get(d[i])
            if si is None or si < 253 or i < 253:
                i += 1
                continue
            if c[i] / c[i - 252] - 1 - (SPY_C[si] / SPY_C[si - 252] - 1) <= 0.40:
                i += 1
                continue
            d0 = dt.date.fromisoformat(d[i])
            if any(0 <= (e - d0).days <= 7 for e in ev):
                i += 1
                continue
            rv = RS.rv_blend(c[:i + 1])
            if rv is None or rv > 0.60:
                i += 1
                continue
            j = i + 1
            if s5[i] is not None and o[j] > s5[i]:
                i += 1
                continue
            k = j
            ex = None
            while k < len(c):
                if (s5[k] is not None and c[k] > s5[k]) or (k - j) >= 10:
                    ex = k
                    break
                k += 1
            if ex is None:
                break
            rec = {"s": s, "ent": d[j], "ex": d[ex], "rank": r2[i],
                   "sh_ret": c[ex] / o[j] - 1}
            hv = hv20(c, i)
            dte = first_monthly(d[j])
            if hv and dte:
                sig = hv * K_IV
                T = dte / 365.0
                pk = pick(o[j], sig, T)
                if pk:
                    K, prem = pk
                    cal = (dt.date.fromisoformat(d[ex])
                           - dt.date.fromisoformat(d[j])).days
                    T1 = max(T - cal / 365.0, 0.0)
                    mark = max(cm.bs_call(c[ex], K, T1, sig * CRUSH),
                               max(c[ex] - K, 0.0))
                    rec["prem"] = prem
                    rec["mark"] = mark
            out.append(rec)
            held = ex
            i = ex + 1
    out.sort(key=lambda t: t["ent"])
    return out


def replay(trades, vehicle, hs_div=None, start=None, end=None):
    from collections import defaultdict
    byent = defaultdict(list)
    for t in trades:
        if start and t["ent"] < start:
            continue
        if end and t["ent"] >= end:
            continue
        if vehicle == "calls" and "prem" not in t:
            continue
        byent[t["ent"]].append(t)
    ds = [d for d in SPY_D if (not start or d >= start) and (not end or d < end)]
    cash, pos, curve, rets = CAP0, {}, [], []
    for d in ds:
        for s in list(pos):
            if pos[s]["ex"] <= d:
                p = pos.pop(s)
                cash += p["units"] * p["exit_px"]
                rets.append(p["exit_px"] / p["entry_px"] - 1)
        eq = cash + sum(p["units"] * p["entry_px"] for p in pos.values())
        for t in sorted(byent.get(d, []), key=lambda x: x["rank"]):
            s = t["s"]
            if len(pos) >= SLOTS or s in pos:
                continue
            if vehicle == "shares":
                ep = t["ent_px"] if "ent_px" in t else None
                epx = (1 + COMM)
                entry = t["sh_entry"]
                exit_ = t["sh_exit"]
            else:
                hs = (HS.get(s, 0.05) / hs_div) if hs_div else 0.0
                entry = t["prem"] * (1 + hs + COMM)
                exit_ = t["mark"] * (1 - hs - COMM)
            budget = min(eq / SLOTS, cash)
            units = budget / entry if entry > 0 else 0
            if units <= 0 or budget < 100:
                continue
            cash -= units * entry
            pos[s] = {"units": units, "entry_px": entry, "exit_px": exit_,
                      "ex": t["ex"]}
        curve.append(cash + sum(p["units"] * p["entry_px"]
                                for p in pos.values()))
    for s in list(pos):
        p = pos.pop(s)
        cash += p["units"] * p["exit_px"]
        rets.append(p["exit_px"] / p["entry_px"] - 1)
    yrs = max(len(ds) / 252.0, 0.5)
    cagr = (cash / CAP0) ** (1 / yrs) - 1
    peak = mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak) if peak else 0
    w = [r for r in rets if r > 0]
    l = [r for r in rets if r <= 0]
    pf = (sum(w) / abs(sum(l))) if l and sum(l) else 99.0
    dr = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve))
          if curve[i - 1] > 0]
    mu = sum(dr) / len(dr) if dr else 0
    sd = math.sqrt(sum((r - mu) ** 2 for r in dr) / (len(dr) - 1)) if len(dr) > 1 else 0
    return {"n": len(rets), "wr": len(w) / len(rets) * 100 if rets else 0,
            "avg": sum(rets) / len(rets) * 100 if rets else 0,
            "pf": pf, "cagr": cagr, "mdd": mdd,
            "calmar": cagr / mdd if mdd else 0,
            "sharpe": (mu * 252) / (sd * math.sqrt(252)) if sd else 0,
            "final": cash}


def main():
    tr = build()
    for t in tr:
        seq = BARS[t["s"]]
        di = {r[0]: i for i, r in enumerate(seq)}
        t["sh_entry"] = seq[di[t["ent"]]][1] * (1 + COMM)
        t["sh_exit"] = seq[di[t["ex"]]][4] * (1 - COMM)
    withopt = sum(1 for t in tr if "prem" in t)
    print(f"Robert trades on the 90-name universe: {len(tr)} "
          f"({withopt} with a priced call)   span {SPY_D[0]} -> {SPY_D[-1]}\n")
    hdr = (f"  {'vehicle':32s} {'n':>5s} {'win%':>6s} {'avg/tr':>8s} "
           f"{'PF':>6s} {'CAGR':>8s} {'maxDD':>7s} {'Calmar':>7s} {'Sharpe':>7s}")
    for wl, (a, b) in (("FULL 2014-2026", (None, None)),
                       ("IN-SAMPLE  ->2022", (None, "2022-01-01")),
                       ("OUT-OF-SAMPLE 2022+", ("2022-01-01", None))):
        print("=" * 104)
        print(wl)
        print("=" * 104)
        print(hdr)
        cells = [("SHARES", "shares", None),
                 ("CALLS - pure mid", "calls", None),
                 ("CALLS - 1/3 quoted spread", "calls", 3.0),
                 ("CALLS - 1/2 quoted spread", "calls", 2.0),
                 ("CALLS - full quoted spread", "calls", 1.0)]
        for lab, veh, div in cells:
            r = replay(tr, veh, div, a, b)
            print(f"  {lab:32s} {r['n']:>5d} {r['wr']:>5.1f}% "
                  f"{r['avg']:>+7.2f}% {r['pf']:>6.2f} {r['cagr']*100:>7.2f}% "
                  f"{r['mdd']*100:>6.1f}% {r['calmar']:>7.2f} {r['sharpe']:>7.2f}")
        print()


if __name__ == "__main__":
    main()
