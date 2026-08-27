#!/usr/bin/env python3
"""robert_validate.py — RESEARCH ONLY. Retest and validate the LOCKED Robert
spec exactly as specified (Alex, 2026-08-16).

  SIGNAL  RSI(2) < 10 (Wilder, alpha 1/2) AND close > SMA200, completed bar
  GATES   RS252 vs SPY > +40pp, MEASURED AS OF THE PRIOR DAY
          ATM IV <= 60%   (rv-blend proxy in research)
          no earnings within 7 days
          skip if the next open is already above the prior SMA5
  ENTRY   next open (~09:45 ET limit worked at the mid)
  CONTRACT shallowest strike with extrinsic < 20% of premium (delta lands
          0.78-0.80 as an OUTCOME), first standard monthly 30-50 DTE, skip
          if none; OI >= 250 and quoted spread <= 8% of mark at order time
  SIZING  15% of sleeve per position, 6 slots max, one position per symbol
  EXIT    close over SMA5, or 10-bar time stop. No stop, no target, no rolls.

Every earlier run in this session used 3 slots x 33%, which is NOT the spec
and materially overstates concentration risk. This is the corrected run.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, "/Users/alex/repos/agentic-cron")
import rsi2_call_model as cm                                   # noqa: E402
import robert_scan as RS                                       # noqa: E402

BARS = json.load(open("/tmp/robert_hc_bars.json"))
EARN = json.load(open(os.path.join(ROOT, "data", "robert_earnings.json")))
UNI = [s.strip() for s in
       open(os.path.join(ROOT, "robert_universe.txt")).read()
       .replace("\n", " ").split(",") if s.strip()]
UNI = [s for s in UNI if s in BARS and len(BARS[s]) > 300]
SPY = BARS["SPY"]
SPY_C = [r[4] for r in SPY]
SPY_D = [r[0] for r in SPY]
SPY_I = {d: i for i, d in enumerate(SPY_D)}

CAP0 = 100_000.0
SLOTS, SLOT_PCT = 6, 0.15          # <- the locked spec
COMM = 0.0005
K_IV, CRUSH = 1.25, 0.90
SPREAD_CAP = 0.08                  # <- updated: 8% of mark

CH = json.load(open(os.path.join(ROOT, "data", "robert_chain_check.json")))
HS, OI = {}, {}
for s, v in (CH.get("detail") or {}).items():
    t = v.get("target") if isinstance(v, dict) else None
    if t and t.get("spread_pct") is not None:
        HS[s] = t["spread_pct"] / 2.0
        OI[s] = t.get("oi", 0)


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


def first_monthly(ds):
    d0 = dt.date.fromisoformat(ds)
    for k in range(6):
        y, m = d0.year + (d0.month - 1 + k) // 12, (d0.month - 1 + k) % 12 + 1
        tf = third_friday(y, m)
        if 30 <= (tf - d0).days <= 50:
            return (tf - d0).days
    return None                       # skip if none - per spec


def pick(S, sig, T):
    for mult in [x / 200 for x in range(200, 99, -1)]:
        K = S * mult
        prem = cm.bs_call(S, K, T, sig)
        if prem <= 0.01:
            continue
        if (prem - max(S - K, 0.0)) / prem < 0.20:
            d1 = ((math.log(S / K) + (cm.R + sig * sig / 2) * T)
                  / (sig * math.sqrt(T))) if T > 0 and sig > 0 else 9
            return K, prem, cm.ncdf(d1)
    return None


def hv20(c, i):
    if i < 20:
        return None
    r = [math.log(c[j] / c[j - 1]) for j in range(i - 19, i + 1)]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / len(r) * 252)


def build():
    out, deltas = [], []
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
            # RS252 AS OF THE PRIOR DAY
            si = SPY_I.get(d[i - 1])
            if si is None or si < 253 or i < 254:
                i += 1
                continue
            rs = (c[i - 1] / c[i - 253] - 1) - (SPY_C[si] / SPY_C[si - 252] - 1)
            if rs <= 0.40:
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
            dte = first_monthly(d[j])
            if dte is None:
                i += 1
                continue                      # skip if no 30-50 DTE monthly
            k, ex = j, None
            while k < len(c):
                if (s5[k] is not None and c[k] > s5[k]) or (k - j) >= 10:
                    ex = k
                    break
                k += 1
            if ex is None:
                break
            rec = {"s": s, "ent": d[j], "ex": d[ex], "rank": r2[i],
                   "bars": ex - j,
                   "sh_in": o[j] * (1 + COMM), "sh_out": c[ex] * (1 - COMM)}
            hv = hv20(c, i)
            if hv:
                sig = hv * K_IV
                T = dte / 365.0
                pk = pick(o[j], sig, T)
                if pk:
                    K, prem, delta = pk
                    cal = (dt.date.fromisoformat(d[ex])
                           - dt.date.fromisoformat(d[j])).days
                    T1 = max(T - cal / 365.0, 0.0)
                    mark = max(cm.bs_call(c[ex], K, T1, sig * CRUSH),
                               max(c[ex] - K, 0.0))
                    rec["prem"], rec["mark"], rec["dte"] = prem, mark, dte
                    deltas.append(delta)
            out.append(rec)
            held = ex
            i = ex + 1
    out.sort(key=lambda t: t["ent"])
    return out, deltas


def replay(tr, vehicle, hs_div=None, start=None, end=None, chain_gate=False):
    byent = defaultdict(list)
    for t in tr:
        if start and t["ent"] < start:
            continue
        if end and t["ent"] >= end:
            continue
        if vehicle == "calls":
            if "prem" not in t:
                continue
            if chain_gate:
                s = t["s"]
                if OI.get(s, 0) < 250 or (HS.get(s, 1) * 2) > SPREAD_CAP:
                    continue
        byent[t["ent"]].append(t)
    ds = [d for d in SPY_D if (not start or d >= start) and (not end or d < end)]
    cash, pos, curve, rets = CAP0, {}, [], []
    for d in ds:
        for s in list(pos):
            if pos[s]["ex"] <= d:
                p = pos.pop(s)
                cash += p["u"] * p["xp"]
                rets.append(p["xp"] / p["ep"] - 1)
        eq = cash + sum(p["u"] * p["ep"] for p in pos.values())
        for t in sorted(byent.get(d, []), key=lambda x: x["rank"]):
            s = t["s"]
            if len(pos) >= SLOTS or s in pos:
                continue
            if vehicle == "shares":
                ep, xp = t["sh_in"], t["sh_out"]
            else:
                hs = (HS.get(s, 0.05) / hs_div) if hs_div else 0.0
                ep = t["prem"] * (1 + hs + COMM)
                xp = t["mark"] * (1 - hs - COMM)
            budget = min(SLOT_PCT * eq, cash)
            if budget < 100 or ep <= 0:
                continue
            u = budget / ep
            cash -= u * ep
            pos[s] = {"u": u, "ep": ep, "xp": xp, "ex": t["ex"]}
        curve.append(cash + sum(p["u"] * p["ep"] for p in pos.values()))
    for s in list(pos):
        p = pos.pop(s)
        cash += p["u"] * p["xp"]
        rets.append(p["xp"] / p["ep"] - 1)
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
    sd = (math.sqrt(sum((r - mu) ** 2 for r in dr) / (len(dr) - 1))
          if len(dr) > 1 else 0)
    return {"n": len(rets), "wr": len(w) / len(rets) * 100 if rets else 0,
            "avg": sum(rets) / len(rets) * 100 if rets else 0,
            "pf": pf, "cagr": cagr, "mdd": mdd,
            "calmar": cagr / mdd if mdd else 0,
            "sharpe": (mu * 252) / (sd * math.sqrt(252)) if sd else 0,
            "final": cash}


def main():
    tr, deltas = build()
    deltas.sort()
    print(f"LOCKED SPEC — {SLOTS} slots x {SLOT_PCT:.0%}, spread cap "
          f"{SPREAD_CAP:.0%}, RS252 as of prior day")
    print(f"universe {len(UNI)} names · {SPY_D[0]} -> {SPY_D[-1]}")
    print(f"signals {len(tr)} · with a 30-50 DTE monthly priced "
          f"{sum(1 for t in tr if 'prem' in t)}")
    if deltas:
        print(f"resulting delta (an OUTCOME): median {deltas[len(deltas)//2]:.3f}"
              f", p10 {deltas[len(deltas)//10]:.3f}, "
              f"p90 {deltas[9*len(deltas)//10]:.3f}, "
              f"share in 0.78-0.80 band "
              f"{sum(1 for x in deltas if 0.78<=x<=0.80)/len(deltas)*100:.0f}%")
    hold = [t["bars"] for t in tr]
    hold.sort()
    print(f"hold: median {hold[len(hold)//2]} bars, max {hold[-1]}\n")
    hdr = (f"  {'vehicle':34s} {'n':>5s} {'win%':>6s} {'avg/tr':>8s} {'PF':>6s} "
           f"{'CAGR':>8s} {'maxDD':>7s} {'Calmar':>7s} {'Sharpe':>7s}")
    for wl, (a, b) in (("FULL 2014-2026", (None, None)),
                       ("IN-SAMPLE ->2022", (None, "2022-01-01")),
                       ("OUT-OF-SAMPLE 2022+", ("2022-01-01", None))):
        print("=" * 106)
        print(wl)
        print("=" * 106)
        print(hdr)
        for lab, veh, div, cg in (
                ("SHARES", "shares", None, False),
                ("CALLS - mid", "calls", None, False),
                ("CALLS - 1/3 quoted", "calls", 3.0, False),
                ("CALLS - 1/2 quoted", "calls", 2.0, False),
                ("CALLS - full quoted", "calls", 1.0, False),
                ("CALLS - 1/2 qtd, chain-gated", "calls", 2.0, True),
                ("CALLS - full qtd, chain-gated", "calls", 1.0, True)):
            r = replay(tr, veh, div, a, b, cg)
            print(f"  {lab:34s} {r['n']:>5d} {r['wr']:>5.1f}% "
                  f"{r['avg']:>+7.2f}% {r['pf']:>6.2f} {r['cagr']*100:>7.2f}% "
                  f"{r['mdd']*100:>6.1f}% {r['calmar']:>7.2f} {r['sharpe']:>7.2f}")
        print()


if __name__ == "__main__":
    main()
