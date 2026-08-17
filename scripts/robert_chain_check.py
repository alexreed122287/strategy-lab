#!/usr/bin/env python3
"""robert_chain_check.py — RESEARCH ONLY, read-only. The live chain gate that
robert_scan.py defers to order time ("cannot be computed from daily bars and
is rendered as an order-time reminder").

For every name in robert_universe.txt, on the first monthly expiry >= MIN_DTE:
  target call = shallowest strike whose extrinsic < 20% of premium
                (delta lands ~0.78-0.80 as an outcome, per the Robert spec)
  PASS/FAIL vs the program gate  : OI >= 10 AND quoted spread <= 25% of mark
  OI ladder                      : also tag 300 / 200 / 100
  deepest fallback               : the shallowest qualifying strike that still
                                   clears each OI floor, if the target is thin

Quoted spread is reported as-is; the Robert spec's own note is that quoted
overstates realistic cost 2-3x, so a marginal spread is a work-the-mid case,
not an automatic reject. OI is a settled EOD figure and is reliable any day.

Writes data/robert_chain_check.json. Places no orders and touches no live file.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = "https://api.tradier.com"
MIN_DTE = 20
EXTRINSIC_MAX = 0.20
# Amended 08/17/2026 from 250 / 0.05. The old floor was never isolated in a
# backtest - the model-marks run priced options off Black-Scholes, which cannot
# produce open interest, so that gate never bound on anything. The OI floor now
# exists only for size feasibility; read contract volume for fillability.
# NOTE: data/robert_chain_check.json predates this change and records the gate
# in force when it was captured (250 / 0.05) in its own `gate` field.
GATE_OI, GATE_SPREAD = 10, 0.25

NEW13 = ["SPOT", "XPO", "RRX", "MKSI", "BURL", "SNX", "MOD", "EVR", "PAAS",
         "SGI", "AMKR", "ATI", "FORM"]


def _candidates():
    """Every plausible token, in order. ~/.tradier_token is NOT trusted blindly:
    on this Mac it currently holds a dead key that 401s against prod, which is
    why this probes instead of taking the first hit (same lesson as
    rsi2_engine.working_token)."""
    out = []
    for v in (os.environ.get("TRADIER_TOKEN"),
              os.environ.get("TRADIER_ACCESS_TOKEN")):
        if v and v.strip():
            out.append(v.strip())
    p = os.path.expanduser("~/.tradier_token")
    if os.path.exists(p):
        v = open(p).read().strip()
        if v:
            out.append(v)
    p = os.path.expanduser("~/options-platform/.env")
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("TRADIER_ACCESS_TOKEN="):
                v = line.split("=", 1)[1].strip()
                if v:
                    out.append(v)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def token():
    """First candidate that actually authenticates against the data API."""
    for t in _candidates():
        try:
            req = urllib.request.Request(
                API + "/v1/markets/quotes?symbols=SPY",
                headers={"Authorization": f"Bearer {t}",
                         "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15):
                return t
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 401, 403):
                print(f"  token ...{t[-4:]} rejected ({ex.code}) — skipping",
                      file=sys.stderr)
                continue
            raise
    return None


TOK = token()
if not TOK:
    sys.exit("no Tradier token")

_lock = threading.Lock()
_last = [0.0]


def tget(path, params):
    with _lock:
        w = 0.14 - (time.time() - _last[0])
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()
    req = urllib.request.Request(
        f"{API}/v1/markets/{path}?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def spot_of(sym):
    d = tget("quotes", {"symbols": sym})
    q = ((d or {}).get("quotes") or {}).get("quote")
    if isinstance(q, list):
        q = q[0] if q else None
    if not q:
        return None
    return q.get("last") or q.get("close") or q.get("prevclose")


def check(sym):
    today = dt.date.today()
    spot = spot_of(sym)
    if not spot:
        return {"err": "no_quote"}
    spot = float(spot)
    ex = tget("options/expirations", {"symbol": sym, "includeAllRoots": "true"})
    dates = (((ex or {}).get("expirations") or {}).get("date")) or []
    if isinstance(dates, str):
        dates = [dates]
    if not dates:
        return {"err": "no_options", "spot": spot}
    monthly = [dt.date.fromisoformat(d) for d in dates
               if dt.date.fromisoformat(d).weekday() == 4
               and 15 <= dt.date.fromisoformat(d).day <= 21
               and (dt.date.fromisoformat(d) - today).days >= MIN_DTE]
    if not monthly:
        fut = [dt.date.fromisoformat(d) for d in dates
               if (dt.date.fromisoformat(d) - today).days >= MIN_DTE]
        if not fut:
            return {"err": "no_expiry", "spot": spot}
        monthly = [min(fut)]
    exp = min(monthly)
    dte = (exp - today).days
    ch = tget("options/chains", {"symbol": sym, "expiration": exp.isoformat(),
                                 "greeks": "true"})
    opts = (((ch or {}).get("options") or {}).get("option")) or []
    if isinstance(opts, dict):
        opts = [opts]
    calls = [o for o in opts if o.get("option_type") == "call"]
    if not calls:
        return {"err": "no_calls", "spot": spot}

    qualifying = []
    for o in sorted(calls, key=lambda o: -float(o["strike"])):
        K = float(o["strike"])
        if K >= spot:
            continue
        bid, ask = float(o.get("bid") or 0), float(o.get("ask") or 0)
        mark = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
        if mark <= 0:
            continue
        if (mark - max(spot - K, 0.0)) / mark >= EXTRINSIC_MAX:
            continue
        g = o.get("greeks") or {}
        qualifying.append({
            "strike": K, "oi": int(o.get("open_interest") or 0),
            "vol": int(o.get("volume") or 0), "bid": bid, "ask": ask,
            "mark": round(mark, 3),
            "spread_pct": round((ask - bid) / mark, 4),
            "delta": round(float(g.get("delta") or 0), 3),
            "extrinsic_pct": round((mark - max(spot - K, 0.0)) / mark, 4)})
    if not qualifying:
        return {"err": "no_strike_under_20pct_extrinsic", "spot": spot,
                "exp": exp.isoformat(), "dte": dte}

    tgt = qualifying[0]                      # shallowest qualifying
    gate_pass = tgt["oi"] >= GATE_OI and tgt["spread_pct"] <= GATE_SPREAD
    ladder = {}
    for thr in (300, 250, 200, 100):
        hit = next((q for q in qualifying if q["oi"] >= thr), None)
        ladder[str(thr)] = ({"strike": hit["strike"], "oi": hit["oi"],
                             "delta": hit["delta"],
                             "spread_pct": hit["spread_pct"]} if hit else None)
    best_oi = max(q["oi"] for q in qualifying)
    return {"spot": round(spot, 2), "exp": exp.isoformat(), "dte": dte,
            "target": tgt, "gate_pass": gate_pass,
            "gate_reason": ("ok" if gate_pass else
                            ("OI %d < %d" % (tgt["oi"], GATE_OI)
                             if tgt["oi"] < GATE_OI else "") +
                            (" / " if (tgt["oi"] < GATE_OI and
                                       tgt["spread_pct"] > GATE_SPREAD) else "") +
                            ("spread %.1f%% > %d%%" % (tgt["spread_pct"] * 100,
                                                       GATE_SPREAD * 100)
                             if tgt["spread_pct"] > GATE_SPREAD else "")),
            "ladder": ladder, "best_oi_in_zone": best_oi,
            "n_qualifying": len(qualifying)}


def main():
    uni = [s.strip() for s in
           open(os.path.join(ROOT, "robert_universe.txt")).read()
           .replace("\n", " ").split(",") if s.strip()]
    print(f"universe: {len(uni)} names · first monthly >= {MIN_DTE} DTE · "
          f"gate OI>={GATE_OI} & spread<={GATE_SPREAD:.0%}\n")
    out, q = {}, queue.Queue()
    for s in uni:
        q.put(s)
    done = [0]

    def work():
        while True:
            try:
                s = q.get_nowait()
            except queue.Empty:
                return
            try:
                out[s] = check(s)
            except Exception as e:
                out[s] = {"err": f"{type(e).__name__}: {e}"}
            done[0] += 1
            if done[0] % 20 == 0:
                print(f"  {done[0]}/{len(uni)}", flush=True)

    ts = [threading.Thread(target=work, daemon=True) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    ok = {s: v for s, v in out.items() if not v.get("err")}
    passed = [s for s, v in ok.items() if v["gate_pass"]]
    failed = [s for s, v in ok.items() if not v["gate_pass"]]
    errs = {s: v["err"] for s, v in out.items() if v.get("err")}

    print(f"\n{'='*78}\nWHOLE UNIVERSE: {len(passed)}/{len(ok)} PASS the "
          f"OI>={GATE_OI} + spread<={GATE_SPREAD:.0%} gate")
    if errs:
        print(f"  errors/no-chain: {errs}")

    print(f"\n{'='*78}\nTHE 13 ADDED 2026-08-07 (chain check was never run)")
    print(f"{'sym':6s} {'gate':>6s} {'strike':>8s} {'delta':>6s} {'OI':>7s} "
          f"{'spread':>7s} {'DTE':>4s}  {'reason / fallback':<38s}")
    for s in NEW13:
        v = out.get(s, {})
        if v.get("err"):
            print(f"{s:6s} {'ERR':>6s} {'':>8s} {'':>6s} {'':>7s} {'':>7s} "
                  f"{'':>4s}  {v['err']:<38s}")
            continue
        t = v["target"]
        fb = ""
        if not v["gate_pass"]:
            l = v["ladder"].get("250")
            fb = (f"deeper strike {l['strike']:g} has OI {l['oi']} "
                  f"@{l['spread_pct']*100:.1f}%" if l
                  else f"best OI in zone {v['best_oi_in_zone']}")
        print(f"{s:6s} {('PASS' if v['gate_pass'] else 'FAIL'):>6s} "
              f"{t['strike']:>8g} {t['delta']:>6.2f} {t['oi']:>7d} "
              f"{t['spread_pct']*100:>6.1f}% {v['dte']:>4d}  "
              f"{(v['gate_reason'] if not v['gate_pass'] else '')[:20]:<20s}"
              f"{fb:<18s}")

    p13 = [s for s in NEW13 if out.get(s, {}).get("gate_pass")]
    print(f"\n  {len(p13)}/13 clear the gate outright: {', '.join(p13)}")
    f13 = [s for s in NEW13 if s in ok and not out[s]['gate_pass']]
    print(f"  {len(f13)}/13 fail at the target strike: {', '.join(f13)}")
    rescue = [s for s in f13 if out[s]["ladder"].get("250")]
    print(f"    of those, {len(rescue)} have a deeper strike clearing OI 250: "
          f"{', '.join(rescue)}")

    json.dump({"as_of": dt.date.today().isoformat(),
               "gate": {"oi": GATE_OI, "spread": GATE_SPREAD,
                        "min_dte": MIN_DTE, "extrinsic_max": EXTRINSIC_MAX},
               "pass": sorted(passed), "fail": sorted(failed),
               "errors": errs, "detail": out},
              open(os.path.join(ROOT, "data", "robert_chain_check.json"), "w"),
              indent=1)
    print(f"\nwrote data/robert_chain_check.json")


if __name__ == "__main__":
    main()
