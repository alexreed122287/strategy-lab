#!/usr/bin/env python3
"""BB Rubber Band per-name screen over the market-data-brain parquets.

Paths: SL_BRAIN_DIR env (default ~/Projects/market-data-brain), SL_BB_OUT for
the output JSON. First run 2026-08-02 in the strategy-lab session produced the
per-name table embedded in the dashboard BOOKS blob.

Machinery is VERBATIM from market-data-brain/scripts/wide_pipeline.py
(build_frame / screen_symbol / stats — the panel-audited z-score wide screen),
with exactly one change: the entry's stretch condition is the BB(20,2) lower
band (close < SMA20 - 2*SD20, sample std) instead of z50 <= -1.5.

Also re-runs the UNMODIFIED z-score screen as a harness anchor and diffs it
against the audited results/wide_screen_results.json (data has been refreshed
2026-08-01, so small trade-count drift is expected and reported, not hidden).

Exclusions: the 14 data-corrupt/spliced series flagged in manifest.json and the
adversarial review (WEC CSX TPL EG EXE FER CRH FISV CL AIG ROK NOC TDG NBIS).
BF.B / BRK.B are kept (flag is earnings-missing, not data-corrupt) and trade
with no earnings constraints, as in the audited run.
"""
import json, os, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

BRAIN = os.path.expanduser(os.environ.get("SL_BRAIN_DIR", "~/Projects/market-data-brain"))
OUT = os.environ.get("SL_BB_OUT", "bb_per_name_results.json")
CORRUPT = {"WEC","CSX","TPL","EG","EXE","FER","CRH","FISV","CL","AIG","ROK","NOC","TDG","NBIS"}

manifest = json.load(open(f"{BRAIN}/manifest.json"))
have = {f[:-8] for f in os.listdir(f"{BRAIN}/daily") if f.endswith(".parquet")}
SYMS = sorted(have - CORRUPT)  # every clean cached series, incl. ext31/core15 names outside the SP500/NDX wide universe
print(f"parquets {len(have)}, screened {len(SYMS)} (corrupt excluded: {sorted(CORRUPT & have)})", flush=True)

def rsi_wilder(close, n=3):
    d = close.diff()
    ru = d.clip(lower=0.0).ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    rd = (-d).clip(lower=0.0).ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + ru / rd)

def build_frame(s):
    df = pd.read_parquet(f"{BRAIN}/daily/{s}.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    c = df["close"]; v = df["volume"]
    out = pd.DataFrame(index=df.index)
    out["close"] = c
    out["sma200"] = c.rolling(200).mean()
    out["sma50"] = c.rolling(50).mean()
    out["sd50"] = c.rolling(50).std()
    out["z"] = (c - out["sma50"]) / out["sd50"]
    out["sma20"] = c.rolling(20).mean()
    out["sd20"] = c.rolling(20).std()
    out["r3"] = rsi_wilder(c)
    out["e5"] = c.ewm(span=5, adjust=False).mean()
    out["av50"] = v.rolling(50).mean()
    epath = f"{BRAIN}/earnings/{s}.json"
    edates = json.load(open(epath)) if os.path.exists(epath) else []
    eset = set(pd.Timestamp(d) for d in edates)
    idx = out.index; n = len(out)
    eb = np.zeros(n, bool); enx = np.zeros(n, bool)
    for i in range(n):
        d0 = idx[i].normalize()
        d1 = idx[i + 1].normalize() if i + 1 < n else d0 + pd.Timedelta(days=4)
        up = any(d0 < e <= d1 for e in eset)
        eb[i] = (d0 in eset) or up
        enx[i] = up
    out["eb"] = eb; out["enext"] = enx
    return out

def screen_symbol(F, mode):
    c = F["close"].values; e5 = F["e5"].values
    base = (F["close"] > 20) & (F["av50"] > 1e6) & (F["close"] > F["sma200"]) & (F["r3"] < 20)
    if mode == "bb":
        entry = (base & (F["close"] < F["sma20"] - 2 * F["sd20"])).values
    else:
        entry = (base & (F["z"] <= -1.5)).values
    eb = F["eb"].values; enx = F["enext"].values
    idx = F.index
    start = idx.searchsorted(pd.Timestamp("2019-01-01"))
    trades = []; in_pos = False; ent_px = 0.0; ent_i = 0
    for i in range(start, len(F)):
        if in_pos:
            held = i - ent_i
            reason = None
            if c[i] > e5[i]: reason = "ema"
            elif enx[i]: reason = "earn"
            elif held >= 10: reason = "time"
            if reason:
                trades.append({"ret": c[i]/ent_px - 1.0, "days": held, "why": reason,
                               "entry_date": str(idx[ent_i].date())})
                in_pos = False
        if not in_pos and entry[i] and not eb[i] and not np.isnan(c[i]):
            in_pos = True; ent_px = c[i]; ent_i = i
    return trades

def stats(trades):
    if not trades: return {"trades": 0}
    r = np.array([t["ret"] for t in trades])
    gl = -r[r <= 0].sum()
    return {"trades": len(r), "win_pct": round(100.0*(r > 0).mean(), 1),
            "avg_ret": round(100.0*r.mean() - 0.02, 3),
            "pf": round(float(r[r > 0].sum()/gl) if gl > 0 else 999, 2),
            "avg_days": round(float(np.mean([t["days"] for t in trades])), 1),
            "worst": round(100.0*r.min(), 2),
            "n_2025_26": sum(1 for t in trades if t["entry_date"] >= "2025-01-01"),
            "earn_exits": sum(1 for t in trades if t["why"] == "earn")}

bb, zrep = {}, {}
for i, s in enumerate(SYMS):
    try:
        F = build_frame(s)
        bb[s] = stats(screen_symbol(F, "bb"))
        zrep[s] = stats(screen_symbol(F, "z"))
    except Exception as ex:
        bb[s] = {"trades": -1, "err": str(ex)[:60]}
        zrep[s] = {"trades": -1}
    if (i + 1) % 75 == 0: print(f"[screen] {i+1}/{len(SYMS)}", flush=True)

# Anchor: replicate of the unmodified z screen vs the audited artifact.
audited = json.load(open(f"{BRAIN}/results/wide_screen_results.json"))["per_symbol"]
diffs, exact = [], 0
for s in SYMS:
    a, b = audited.get(s), zrep.get(s)
    if not a or not b or b.get("trades", -1) < 0: continue
    dt_ = b.get("trades", 0) - a.get("trades", 0)
    if dt_ == 0 and abs((b.get("avg_ret") or 0) - (a.get("avg_ret") or 0)) < 0.05:
        exact += 1
    else:
        diffs.append((s, a.get("trades"), b.get("trades"),
                      a.get("avg_ret"), b.get("avg_ret")))
print(f"[anchor] z replicate vs audited: {exact}/{exact+len(diffs)} match "
      f"(data refreshed since the audited run; drift list capped at 15):", flush=True)
for row in diffs[:15]:
    print("   ", row, flush=True)

pooled = [t for s in SYMS if bb.get(s, {}).get("trades", 0) > 0
          for t in [bb[s]]]
n_names = sum(1 for s in bb.values() if s.get("trades", 0) > 0)
n_trades = sum(s.get("trades", 0) for s in bb.values() if s.get("trades", 0) > 0)
print(f"[bb] names with >=1 trade: {n_names}, pooled trades: {n_trades}", flush=True)

json.dump({"meta": {
    "run": "strategy-lab session 2026-08-02, brain@877d82c parquets (refreshed 2026-08-01)",
    "basis": "idealized same-close fills, -0.02pp spread, earnings rules on, one pos/symbol",
    "spec": "close>20 & av50>1M & close>sma200 & close<sma20-2*sd20 (sample std) & rsi3<20; exit close>ema5 | pre-earnings | 10 bars",
    "grade": "RESEARCH - book KILLED at executable basis (fill-mode study 2026-08-01)",
    "screened": len(SYMS), "excluded_corrupt": sorted(CORRUPT & have)},
    "per_symbol": bb,
    "z_extra": {s: zrep[s] for s in SYMS if s not in audited
                and zrep.get(s, {}).get("trades", 0) >= 1},
    "z_replicate_anchor": {"exact": exact, "drift": len(diffs)}},
    open(OUT, "w"), indent=1)
print("wrote", OUT, flush=True)
