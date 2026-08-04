#!/usr/bin/env python3
"""FIDELITY GATE for any attempt to port the RSI2/MFI signal generator into
this repo, so the GitHub build can produce SIGNALS without the Mac.

The rule this enforces: a re-implementation is trusted only if it reproduces
the Mac generator's own SIGNALS blob for a known day, name for name. This
program has been burned twice by re-implementations that looked right and
were not (x39's harness-fidelity gate exists for exactly this), so the gate
runs first and the port ships only if it passes.

  python3 scripts/signals_fidelity_gate.py --brain ~/Projects/market-data-brain/daily

RESULT AS OF 2026-08-03 - the port is NOT wired in, because this gate FAILED:
  * indicator math is exact - 0 depth mismatches, 0 close mismatches, and
    0 false positives across every name the candidate flagged
  * but it found only 33 of the Mac's 89 TAKEs, and 26 of its 65 new-today
  * 38 of the 39 missing new-today signals are on names that are NOT vetted
    arms in SCAN -> THE LIVE SCAN UNIVERSE IS BROADER THAN THE VETTED SET,
    and its actual definition is not in this repo
  * the 1 remaining miss, DD/MFI, fired at mfi3 = 15.96 against a < 10
    threshold -> THE LIVE MFI THRESHOLD IS NOT 10. The research archive names
    the book "mfi3<20 -> ema7", which is consistent with 20.

So two facts are needed from the Mac before the port can be finished, and
neither can be derived from the dashboard alone:
  1. the live scan UNIVERSE rule (which names each arm scans)
  2. the exact entry THRESHOLDS per arm (MFI in particular)
Once those are recorded here, re-run this gate. Exact match -> wire it in.
"""
import argparse, json, os, re
import numpy as np, pandas as pd


def frame(path):
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df[(df["volume"] > 0) & (df["close"] > 0)].set_index("date")
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 2, min_periods=2, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / 2, min_periods=2, adjust=False).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn)
    tp = (h + l + c) / 3.0
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0.0)
    neg = mf.where(tp < tp.shift(1), 0.0)
    f["mfi3"] = 100 * pos.rolling(3).sum() / (pos.rolling(3).sum() + neg.rolling(3).sum())
    f["sma200"] = c.rolling(200).mean()
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default=os.path.expanduser("~/Projects/market-data-brain/daily"))
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--rsi2-threshold", type=float, default=10.0)
    ap.add_argument("--mfi-threshold", type=float, default=10.0)
    a = ap.parse_args()

    page = open(a.page).read()
    g = lambda n: json.loads(re.search(r"const %s = (.*?);\n" % n, page, re.S).group(1))
    SIG, SCAN = g("SIGNALS"), g("SCAN")
    as_of = max(x.get("as_of", "") for x in SIG["signals"])
    thr = {"RSI2": a.rsi2_threshold, "MFI": a.mfi_threshold}

    vetted = {arm: {s for s, v in SCAN["tickers"].items()
                    if (v.get("strats", {}).get(arm) or {}).get("vetted")}
              for arm in thr}
    mine = {}
    for arm, trig in (("RSI2", "rsi2"), ("MFI", "mfi3")):
        for s in sorted(vetted[arm]):
            p = f"{a.brain}/{s}.parquet"
            if not os.path.exists(p):
                continue
            try:
                f = frame(p)
            except Exception:
                continue
            d = pd.Timestamp(as_of)
            if d not in f.index:
                continue
            r = f.loc[d]
            if np.isnan(r[trig]) or np.isnan(r["sma200"]):
                continue
            if r[trig] < thr[arm] and r["close"] > r["sma200"]:
                mine[(s, arm)] = {"depth": round(float(r[trig]), 2),
                                  "close": round(float(r["close"]), 2)}

    theirs = {(x["sym"], x["strat"]): x for x in SIG["signals"]
              if x["strat"] in thr and x["state"] == "TAKE"}
    new = {k for k, x in theirs.items() if x.get("new_today")}
    mk, tk = set(mine), set(theirs)
    both = mk & tk
    dmis = [k for k in both if abs(mine[k]["depth"] - (theirs[k]["depth"] or 0)) > 0.02]
    cmis = [k for k in both if abs(mine[k]["close"] - (theirs[k]["close"] or 0)) > 0.02]
    print(f"as_of {as_of}   thresholds RSI2<{thr['RSI2']} MFI<{thr['MFI']}")
    print(f"  candidate TAKEs {len(mk)}   Mac TAKEs {len(tk)}   Mac new-today {len(new)}")
    print(f"  false positives (mine, not Mac's): {len(mk - tk)}")
    print(f"  missed new-today                 : {len(new - mk)}")
    print(f"  depth mismatches / close mismatches: {len(dmis)} / {len(cmis)}")
    outside = [k for k in (new - mk) if k[0] not in vetted[k[1]]]
    print(f"  missed because NOT in the vetted universe: {len(outside)}")
    ok = (not (mk - tk)) and (not (new - mk)) and not dmis and not cmis
    print("VERDICT:", "PASS - safe to wire in" if ok else "FAIL - do not wire in")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
