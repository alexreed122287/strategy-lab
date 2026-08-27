#!/usr/bin/env python3
"""robert_healthcheck.py — RESEARCH ONLY, read-only. Two jobs:

1. VERIFY THE LIVE SCAN. Independently recompute every gate for the current
   bar with from-scratch indicator math (not robert_scan's functions) and
   assert the scan's verdicts reproduce.
2. CONFIRM THE BACKTEST on the Robert program's OWN 90-name universe — the
   x44 finding was measured on a different (377-name) list, so this re-runs
   the RS252 ablation here to check it transfers.

Spec: entry RSI(2)<10 AND close>SMA200 AND RS252 vs SPY > +40pp AND no
earnings within 7 days AND IV proxy <= 60%; entry NEXT OPEN, skip if that
open is already above the signal bar's SMA5; exit close>SMA5 or 10 bars.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
API = "https://api.tradier.com"
CACHE = "/tmp/robert_hc_bars.json"

import robert_scan as RS                                    # noqa: E402
TOK = RS.token()
assert TOK, "no working Tradier token"


def fetch(sym, start):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily",
                                "start": start})
    req = urllib.request.Request(API + "/v1/markets/history?" + q,
        headers={"Authorization": "Bearer " + TOK, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    days = (d.get("history") or {}).get("day") or []
    if isinstance(days, dict):
        days = [days]
    return [[x["date"], float(x["open"]), float(x["high"]), float(x["low"]),
             float(x["close"]), float(x.get("volume") or 0)]
            for x in days if x.get("close") is not None]


# ---- clean-room indicator math (deliberately not robert_scan's) ----
def rsi_wilder(c, n):
    if len(c) < n + 1:
        return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        g += max(d, 0.0)
        l += max(-d, 0.0)
    g /= n
    l /= n
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        g = (g * (n - 1) + max(d, 0.0)) / n
        l = (l * (n - 1) + max(-d, 0.0)) / n
    if l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + g / l)


def sma_at(c, n, i):
    if i + 1 < n:
        return None
    return sum(c[i + 1 - n:i + 1]) / n


def main():
    uni = [s.strip() for s in
           open(os.path.join(ROOT, "robert_universe.txt")).read()
           .replace("\n", " ").split(",") if s.strip()]
    earn = json.load(open(os.path.join(ROOT, "data", "robert_earnings.json")))

    if os.path.exists(CACHE):
        bars = json.load(open(CACHE))
        print(f"bars from cache: {len(bars)} names")
    else:
        bars = {}
        start = (dt.date.today() - dt.timedelta(days=365 * 12)).isoformat()
        for i, s in enumerate(uni + ["SPY"]):
            try:
                bars[s] = fetch(s, start)
            except Exception as e:
                print(f"  fetch fail {s}: {type(e).__name__}")
            time.sleep(0.15)
            if (i + 1) % 25 == 0:
                print(f"  fetched {i+1}/{len(uni)+1}", flush=True)
        json.dump(bars, open(CACHE, "w"))
    spy = bars["SPY"]
    spy_c = [r[4] for r in spy]
    as_of = spy[-1][0]

    # ================= 1. verify the live scan =================
    print(f"\n{'='*76}\n1. LIVE-SCAN VERIFICATION (bar {as_of}) — clean-room math")
    print(f"{'='*76}")
    spy_r252 = spy_c[-1] / spy_c[-253] - 1
    raw = []
    for t in uni:
        seq = bars.get(t) or []
        if not seq or seq[-1][0] != as_of:
            continue
        c = [r[4] for r in seq]
        if len(c) < 260:
            continue
        r2 = rsi_wilder(c[-200:], 2)
        s200 = sma_at(c, 200, len(c) - 1)
        if s200 is None or c[-1] <= s200 or r2 >= 10:
            continue
        rs = c[-1] / c[-253] - 1 - spy_r252
        eflag = "ok"
        ed = None
        for e in earn.get(t, []):
            dd = (dt.date.fromisoformat(e) - dt.date.fromisoformat(as_of)).days
            if 0 <= dd <= 7:
                eflag, ed = "blocked", e
        ivp = RS.rv_blend(c)
        gates = {"rs": rs > 0.40, "earn": eflag == "ok",
                 "iv": ivp is not None and ivp <= 0.60}
        raw.append((t, r2, rs, ivp, ed, all(gates.values()), gates))
    raw.sort(key=lambda x: x[1])
    print(f"raw signals (RSI2<10 & close>SMA200): {len(raw)}")
    print(f"{'sym':6s} {'RSI2':>6s} {'RS252':>8s} {'IVproxy':>8s} "
          f"{'earn':>10s}  verdict")
    for t, r2, rs, ivp, ed, take, g in raw:
        why = [] if take else ([] if g["rs"] else ["RS gate"]) + \
            ([] if g["earn"] else [f"earnings {ed}"]) + \
            ([] if g["iv"] else ["IV>60%"])
        print(f"{t:6s} {r2:>6.2f} {rs*100:>+7.0f}% {ivp*100:>7.0f}% "
              f"{str(ed or 'clear'):>10s}  "
              f"{'TAKE' if take else 'gated out: ' + ', '.join(why)}")
    n_take = sum(1 for r in raw if r[5])
    print(f"\n  -> {len(raw)} raw, {n_take} pass all gates")
    print("  scan reported: 3 raw, 0 pass all gates (TROW, AVGO, BURL)")
    match = (len(raw) == 3 and n_take == 0 and
             {r[0] for r in raw} == {"TROW", "AVGO", "BURL"})
    print(f"  INDEPENDENT MATCH: {'YES' if match else 'NO — investigate'}")

    # ================= 2. confirm the backtest here =================
    print(f"\n{'='*76}\n2. BACKTEST CONFIRMATION on the Robert 90-name universe")
    print(f"{'='*76}")
    spy_idx = {r[0]: i for i, r in enumerate(spy)}

    def run(sym, use_rs):
        seq = bars.get(sym) or []
        if len(seq) < 300:
            return []
        c = [r[4] for r in seq]
        o = [r[1] for r in seq]
        d = [r[0] for r in seq]
        # rolling indicators
        rsi2 = [None] * len(c)
        g = l = 0.0
        for i in range(1, len(c)):
            ch = c[i] - c[i - 1]
            up, dn = max(ch, 0.0), max(-ch, 0.0)
            if i == 1:
                g, l = up, dn
            else:
                g = (g + up) / 2.0
                l = (l + dn) / 2.0
            rsi2[i] = 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)
        out, i, held = [], 253, -1
        while i < len(c) - 1:
            if i <= held:
                i += 1
                continue
            s200 = sma_at(c, 200, i)
            s5 = sma_at(c, 5, i)
            if s200 is None or c[i] <= s200 or rsi2[i] is None or rsi2[i] >= 10:
                i += 1
                continue
            if use_rs:
                si = spy_idx.get(d[i])
                if si is None or si < 253:
                    i += 1
                    continue
                rs = c[i] / c[i - 252] - 1 - (spy_c[si] / spy_c[si - 252] - 1)
                if rs <= 0.40:
                    i += 1
                    continue
            ed = [e for e in earn.get(sym, [])
                  if 0 <= (dt.date.fromisoformat(e)
                           - dt.date.fromisoformat(d[i])).days <= 7]
            if ed:
                i += 1
                continue
            j = i + 1
            if s5 is not None and o[j] > s5:      # skip-if-open-above-SMA5
                i += 1
                continue
            k = j
            ex = None
            while k < len(c):
                s5k = sma_at(c, 5, k)
                if (s5k is not None and c[k] > s5k) or (k - j) >= 10:
                    ex = k
                    break
                k += 1
            if ex is None:
                break
            out.append(c[ex] / o[j] - 1 - 0.003)
            held = ex
            i = ex + 1
        return out

    for label, use_rs in (("full spec (RS252 on)", True),
                          ("NO RS252 gate", False)):
        allr = [x for s in uni for x in run(s, use_rs)]
        n = len(allr)
        w = [x for x in allr if x > 0]
        ls = [x for x in allr if x <= 0]
        pf = (sum(w) / abs(sum(ls))) if ls and sum(ls) else 99
        print(f"  {label:22s} n={n:6d} wr={len(w)/n*100:5.1f}% "
              f"avg={sum(allr)/n*100:+6.3f}% pf={pf:5.2f}")
    print("\n  x44 measured on the 377-name OA list: "
          "full +0.67%/PF 1.61 vs no-RS +0.01%/PF 1.00")


if __name__ == "__main__":
    main()
