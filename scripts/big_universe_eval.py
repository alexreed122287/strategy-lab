#!/usr/bin/env python3
"""big_universe_eval.py — RESEARCH ONLY. Consume big_universe_test.py's trade
lists and answer two questions:

  1. WHICH RULE IS BETTER on the full optionable universe — one $100k /
     3-slot account replay per rule, identical terms, CAGR / maxDD / Calmar /
     Sharpe / PF / win%.
  2. WHAT SHOULD BE IN THE BASKET for the winner — and does that selection
     survive out of sample? Names are picked on 2010-2021 only, then the
     basket is re-run on 2022-2026 untouched data. Picking names on the full
     sample and quoting the full-sample result is the hindsight this program
     has killed twice; the OOS split is the check.

Account replay convention (the program's own): the per-name trade lists are
skip-free; the account takes them in rank order and skips anything arriving
with no free slot.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

TR = json.load(open("/tmp/bigtest_trades.json"))
CAP0, SLOTS, COST = 100_000.0, 3, 0.0005
IS_END, OOS_START = "2022-01-01", "2022-01-01"


def all_dates():
    ds = set()
    for v in TR.values():
        for arm in ("robert", "hybrid"):
            for t in v[arm]:
                ds.add(t["ent"])
                ds.add(t["ex"])
    return sorted(ds)


DATES = all_dates()


def replay(arm, names=None, start=None, end=None, min_dv=0):
    """$100k / SLOTS account replay over the skip-free trade set."""
    byent = defaultdict(list)
    for s, v in TR.items():
        if names is not None and s not in names:
            continue
        for t in v[arm]:
            if start and t["ent"] < start:
                continue
            if end and t["ent"] >= end:
                continue
            if t["dv"] < min_dv:
                continue
            byent[t["ent"]].append((t["rank"], s, t))
    ds = [d for d in DATES if (not start or d >= start) and (not end or d < end)]
    if not ds:
        return None
    cash, pos, eq_curve, rets = CAP0, {}, [], []
    for d in ds:
        for s in list(pos):
            if pos[s]["ex"] <= d:
                p = pos.pop(s)
                cash += p["sh"] * p["xp"] * (1 - COST)
                rets.append(p["xp"] * (1 - COST) / (p["ep"] * (1 + COST)) - 1)
        eq = cash + sum(p["sh"] * p["ep"] for p in pos.values())
        for rank, s, t in sorted(byent.get(d, [])):
            if len(pos) >= SLOTS or s in pos:
                continue
            px = t["ep"] * (1 + COST)
            sh = int(min(eq / SLOTS, cash) // px) if px > 0 else 0
            if sh < 1:
                continue
            cash -= sh * px
            pos[s] = {"sh": sh, "ep": px, "xp": t["xp"], "ex": t["ex"]}
        eq_curve.append(cash + sum(p["sh"] * p["ep"] for p in pos.values()))
    for s in list(pos):
        p = pos.pop(s)
        cash += p["sh"] * p["xp"]
        rets.append(p["xp"] / p["ep"] - 1)
    final = cash
    yrs = max(len(ds) / 252.0, 0.5)
    cagr = (final / CAP0) ** (1 / yrs) - 1
    peak = mdd = 0.0
    for v in eq_curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak) if peak else 0
    dr = [eq_curve[i] / eq_curve[i - 1] - 1 for i in range(1, len(eq_curve))
          if eq_curve[i - 1] > 0]
    mu = sum(dr) / len(dr) if dr else 0
    sd = math.sqrt(sum((r - mu) ** 2 for r in dr) / (len(dr) - 1)) if len(dr) > 1 else 0
    w = [r for r in rets if r > 0]
    l = [r for r in rets if r <= 0]
    pf = (sum(w) / abs(sum(l))) if l and sum(l) else 99.0
    return {"cagr": cagr, "mdd": mdd, "calmar": cagr / mdd if mdd else 0,
            "sharpe": (mu * 252) / (sd * math.sqrt(252)) if sd else 0,
            "pf": pf, "wr": len(w) / len(rets) * 100 if rets else 0,
            "n": len(rets), "final": final, "yrs": yrs}


def pername(arm, start=None, end=None, min_dv=0):
    out = {}
    for s, v in TR.items():
        r = [t for t in v[arm]
             if (not start or t["ent"] >= start) and (not end or t["ent"] < end)
             and t["dv"] >= min_dv]
        if not r:
            continue
        rr = [t["xp"] * (1 - COST) / (t["ep"] * (1 + COST)) - 1 for t in r]
        w = [x for x in rr if x > 0]
        l = [x for x in rr if x <= 0]
        out[s] = {"n": len(rr), "avg": sum(rr) / len(rr),
                  "wr": len(w) / len(rr) * 100,
                  "pf": (sum(w) / abs(sum(l))) if l and sum(l) else 99.0,
                  "sum": sum(rr),
                  "dv": sorted(t["dv"] for t in r)[len(r) // 2]}
    return out


def show(tag, r):
    if not r:
        print(f"  {tag:34s}  (no trades)")
        return
    print(f"  {tag:34s} {r['n']:>6d} {r['wr']:>5.1f}% {r['pf']:>6.2f} "
          f"{r['cagr']*100:>7.2f}% {r['mdd']*100:>6.1f}% {r['calmar']:>7.2f} "
          f"{r['sharpe']:>7.2f}")


def main():
    print(f"names with trades: {len(TR)}   "
          f"span {DATES[0]} -> {DATES[-1]}\n")
    hdr = (f"  {'cell':34s} {'n':>6s} {'win%':>6s} {'PF':>6s} {'CAGR':>8s} "
           f"{'maxDD':>7s} {'Calmar':>7s} {'Sharpe':>7s}")

    print("=" * 104)
    print("1. FULL OPTIONABLE UNIVERSE — whole-sample account replay")
    print("=" * 104)
    print(hdr)
    for arm in ("robert", "hybrid"):
        show(f"{arm.upper()} (all names)", replay(arm))
    print()
    for dv in (5e6, 25e6, 100e6):
        for arm in ("robert", "hybrid"):
            show(f"{arm.upper()} dv>=${dv/1e6:.0f}M", replay(arm, min_dv=dv))
        print()

    print("=" * 104)
    print("2. BASKET — selected on 2010-2021 ONLY, verified on 2022-2026")
    print("=" * 104)
    winner = None
    best = -9
    for arm in ("robert", "hybrid"):
        r = replay(arm, min_dv=25e6)
        if r and r["calmar"] > best:
            best, winner = r["calmar"], arm
    print(f"  (ranking by Calmar at dv>=$25M -> winner: {winner.upper()})\n")

    ins = pername(winner, end=IS_END, min_dv=25e6)
    cand = {s: v for s, v in ins.items() if v["n"] >= 8 and v["avg"] > 0}
    ranked = sorted(cand, key=lambda s: -cand[s]["sum"])
    print(f"  in-sample (2010-2021) names with n>=8 and avg>0: {len(cand)}")

    for k in (15, 25, 40, 60, 100):
        basket = set(ranked[:k])
        i_r = replay(winner, names=basket, end=IS_END, min_dv=25e6)
        o_r = replay(winner, names=basket, start=OOS_START, min_dv=25e6)
        print(f"\n  --- top {k} names by in-sample total return")
        print(hdr)
        show(f"IN-SAMPLE 2010-2021", i_r)
        show(f"OUT-OF-SAMPLE 2022-2026", o_r)
    print(f"\n  benchmark - ALL dv>=$25M names, no name selection:")
    print(hdr)
    show("IN-SAMPLE 2010-2021", replay(winner, end=IS_END, min_dv=25e6))
    show("OUT-OF-SAMPLE 2022-2026", replay(winner, start=OOS_START, min_dv=25e6))

    json.dump({"winner": winner, "ranked_in_sample": ranked[:120],
               "per_name_is": {s: cand[s] for s in ranked[:120]}},
              open("/tmp/bigtest_basket.json", "w"), indent=1)
    print("\nwrote /tmp/bigtest_basket.json")


if __name__ == "__main__":
    main()
