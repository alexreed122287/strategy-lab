#!/usr/bin/env python3
"""big_universe_test.py — RESEARCH ONLY, read-only. Head-to-head of the
existing ROBERT rule and the HYBRID rule across the full US optionable
universe (3,568 names), on identical terms.

  ROBERT entry : RSI(2)<10 AND close>SMA200
  HYBRID entry : close<SMA5 AND RSI(5)<27 AND SMA200 rising AND SMA2[t-1]>SMA200
  BOTH gates   : RS252 vs SPY > +40pp, rv-blend IV proxy <= 60%
  BOTH entry   : next OPEN, skip if that open is already above the signal SMA5
  ROBERT exit  : close>SMA5 OR 10 bars
  HYBRID exit  : (position green AND RSI(2)>70 AND close>EMA5) OR 10 bars

The earnings-within-7-days gate is OFF FOR BOTH ARMS: earnings history for
3,568 names is not obtainable here, and x44 measured the gate as slightly
NEGATIVE on returns, so dropping it is near-neutral and — critically —
identical for both arms, so the comparison stays fair. It is restored for
the final basket names, which are few enough to fetch.

Streams: fetch a name, compute its trades, keep only the trade list. Never
holds the full price universe in memory.

Writes /tmp/bigtest_trades.json (per-name trade lists + summary).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import robert_scan as RS                                      # noqa: E402

API = "https://api.tradier.com"
START = "2010-01-01"
OUT = "/tmp/bigtest_trades.json"
TOK = RS.token()
assert TOK, "no working Tradier token"

_lk = threading.Lock()
_last = [0.0]
RATE = 0.05


def fetch(sym):
    with _lk:
        w = RATE - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily",
                                "start": START})
    req = urllib.request.Request(API + "/v1/markets/history?" + q,
        headers={"Authorization": "Bearer " + TOK, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    days = (d.get("history") or {}).get("day") or []
    if isinstance(days, dict):
        days = [days]
    return [(x["date"], float(x["open"]), float(x["close"]),
             float(x.get("volume") or 0))
            for x in days if x.get("close") is not None and x.get("open")]


# ---------------- indicators (rolling, single pass) ----------------
def wilder(c, n):
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


def sma_a(c, n):
    out, run = [None] * len(c), 0.0
    for i, v in enumerate(c):
        run += v
        if i >= n:
            run -= c[i - n]
        if i >= n - 1:
            out[i] = run / n
    return out


def ema_a(c, n):
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


def rv_a(c):
    """rv_blend per bar: 0.25*rv5 + 0.40*rv20 + 0.35*rv60, annualized."""
    n = len(c)
    lr = [0.0] * n
    for i in range(1, n):
        lr[i] = math.log(c[i] / c[i - 1]) if c[i - 1] > 0 and c[i] > 0 else 0.0
    out = [None] * n

    def roll_sd(w):
        res = [None] * n
        s = s2 = 0.0
        for i in range(1, n):
            s += lr[i]
            s2 += lr[i] * lr[i]
            if i > w:
                s -= lr[i - w]
                s2 -= lr[i - w] * lr[i - w]
            if i >= w:
                m = s / w
                v = max(s2 / w - m * m, 0.0) * w / (w - 1)
                res[i] = math.sqrt(v) * math.sqrt(252)
        return res
    a, b, d = roll_sd(5), roll_sd(20), roll_sd(60)
    for i in range(n):
        if a[i] is not None and b[i] is not None and d[i] is not None:
            out[i] = max(0.25 * a[i] + 0.40 * b[i] + 0.35 * d[i], 0.05)
    return out


SPY_ROWS = fetch("SPY")
SPY_C = [r[2] for r in SPY_ROWS]
SPY_I = {r[0]: i for i, r in enumerate(SPY_ROWS)}


def trades_for(rows, rule):
    d = [r[0] for r in rows]
    o = [r[1] for r in rows]
    c = [r[2] for r in rows]
    v = [r[3] for r in rows]
    n = len(c)
    if n < 300:
        return []
    r2, r5 = wilder(c, 2), wilder(c, 5)
    s2, s5, s200 = sma_a(c, 2), sma_a(c, 5), sma_a(c, 200)
    e5 = ema_a(c, 5)
    rv = rv_a(c)
    out, i, held = [], 260, -1
    while i < n - 1:
        if i <= held:
            i += 1
            continue
        ok = False
        rank = None
        if rule == "robert":
            if (r2[i] is not None and r2[i] < 10 and s200[i] is not None
                    and c[i] > s200[i]):
                ok, rank = True, r2[i]
        else:
            if (s5[i] is not None and c[i] < s5[i] and r5[i] is not None
                    and r5[i] < 27 and s200[i] is not None
                    and s200[i - 1] is not None and s200[i] > s200[i - 1]
                    and s2[i - 1] is not None and s2[i - 1] > s200[i]):
                ok, rank = True, r5[i]
        if not ok:
            i += 1
            continue
        si = SPY_I.get(d[i])
        if si is None or si < 253 or i < 253:
            i += 1
            continue
        rs = c[i] / c[i - 252] - 1 - (SPY_C[si] / SPY_C[si - 252] - 1)
        if rs <= 0.40:
            i += 1
            continue
        if rv[i] is None or rv[i] > 0.60:
            i += 1
            continue
        j = i + 1
        if s5[i] is not None and o[j] > s5[i]:
            i += 1
            continue
        k, ex = j, None
        while k < n:
            if rule == "robert":
                hit = s5[k] is not None and c[k] > s5[k]
            else:
                hit = (c[k] / o[j] - 1 >= 0 and r2[k] is not None
                       and r2[k] > 70 and e5[k] is not None and c[k] > e5[k])
            if hit or (k - j) >= 10:
                ex = k
                break
            k += 1
        if ex is None:
            break
        out.append({"sig": d[i], "ent": d[j], "ex": d[ex],
                    "ep": round(o[j], 4), "xp": round(c[ex], 4),
                    "rank": round(rank, 2), "bars": ex - j,
                    "dv": round(sum(c[m] * v[m] for m in
                                    range(max(0, i - 62), i + 1)) / 63)})
        held = ex
        i = ex + 1
    return out


def main():
    uni = json.load(open("/tmp/opt_universe.json"))
    res, errs = {}, {}
    q = queue.Queue()
    for s in uni:
        q.put(s)
    done = [0]
    lock = threading.Lock()

    def work():
        while True:
            try:
                s = q.get_nowait()
            except queue.Empty:
                return
            try:
                rows = fetch(s)
                if len(rows) >= 300:
                    rb = trades_for(rows, "robert")
                    hy = trades_for(rows, "hybrid")
                    if rb or hy:
                        with lock:
                            res[s] = {"robert": rb, "hybrid": hy,
                                      "first": rows[0][0], "last": rows[-1][0]}
            except Exception as e:
                with lock:
                    errs[s] = type(e).__name__
            with lock:
                done[0] += 1
                if done[0] % 250 == 0:
                    print(f"  {done[0]}/{len(uni)} names "
                          f"({len(res)} with trades, {len(errs)} err)",
                          flush=True)

    ts = [threading.Thread(target=work, daemon=True) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    json.dump(res, open(OUT, "w"))
    nrb = sum(len(v["robert"]) for v in res.values())
    nhy = sum(len(v["hybrid"]) for v in res.values())
    print(f"\nnames with data+trades: {len(res)} / {len(uni)}   errors: {len(errs)}")
    print(f"ROBERT trades {nrb:,}   HYBRID trades {nhy:,}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
