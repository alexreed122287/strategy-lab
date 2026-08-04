#!/usr/bin/env python3
"""x59 - BB Rubber Band harness. Spec verbatim from the screenshot-corrected
BOOKS entry: price>20, avol50>1M, close>sma200, close<bblb(20,2), rsi(2)<10.
Exit close>ema(5) or the 10-bar stop. Mechanics are the program standard
($100k, 3 slots, 40%/position). Zero-volume rows are dropped at load - the
x45/x54 hygiene lesson, without which Robinhood padding enters the sim.
"""
import json, os, sys
import numpy as np, pandas as pd

SLOTS, CAP0 = 3, 100_000.0
ALLOC = 0.40


def frame(path):
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df[(df["volume"] > 0) & (df["close"] > 0)]          # hygiene
    df = df.set_index("date")
    c, v = df["close"], df["volume"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c
    f["open"] = df["open"] if "open" in df else c
    f["sma200"] = c.rolling(200).mean()
    f["sma20"] = c.rolling(20).mean()
    f["sd20"] = c.rolling(20).std(ddof=1)
    f["bblb"] = f["sma20"] - 2 * f["sd20"]
    f["ema5"] = c.ewm(span=5, adjust=False).mean()
    f["av50"] = v.rolling(50).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn)
    return f


def frame_rows(rows):
    """Same indicators as frame(), from dump_closes --ohlcv rows:
    [[date, open, high, low, close, volume], ...] ascending."""
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("date")
    df = df[(df["volume"] > 0) & (df["close"] > 0)].set_index("date")
    c, v = df["close"], df["volume"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c
    f["open"] = df["open"]
    f["sma200"] = c.rolling(200).mean()
    f["sma20"] = c.rolling(20).mean()
    f["sd20"] = c.rolling(20).std(ddof=1)
    f["bblb"] = f["sma20"] - 2 * f["sd20"]
    f["ema5"] = c.ewm(span=5, adjust=False).mean()
    f["av50"] = v.rolling(50).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn)
    return f


def load_json(bars, start, end):
    """Load from a dump_closes --ohlcv bars.json instead of parquet."""
    fr = {}
    for s, rows in bars.items():
        try:
            f = frame_rows(rows)
        except Exception:
            continue
        f = f[(f.index >= pd.Timestamp(start)) & (f.index <= pd.Timestamp(end))]
        if len(f) >= 300:
            fr[s] = f
    return fr


def load(sources, start, end):
    fr = {}
    for s, p in sources.items():
        try:
            f = frame(p)
        except Exception:
            continue
        f = f[(f.index >= pd.Timestamp(start)) & (f.index <= pd.Timestamp(end))]
        if len(f) >= 300:
            fr[s] = f
    return fr


def simulate(frames, mode="ideal_close", trade_start=None, slip=0.0):
    """mode:
      ideal_close - both legs at the signal close (the idealised basis)
      hybrid      - MOO entry at the NEXT open, exit at the close (MOC). This
                    is the book's OWN spec: the exit rule reads "price>ema(5)
                    at the 3:45 screen -> MOC", so exits fill at the close.
                    This is the executable basis the program validates on.
      next_open   - both legs at the next open. Harsher than the spec; kept
                    as the worst-case leg only.
    slip is per side, on top of the mode."""
    cal = sorted(set().union(*[set(f.index) for f in frames.values()]))
    if trade_start:
        cal = [d for d in cal if d >= pd.Timestamp(trade_start)]
    names = list(frames)
    ent, ex, c, o, r2 = {}, {}, {}, {}, {}
    for s, f in frames.items():
        ent[s] = ((f["close"] > 20) & (f["av50"] > 1e6) & (f["close"] > f["sma200"])
                  & (f["close"] < f["bblb"]) & (f["rsi2"] < 10))
        ex[s] = f["close"] > f["ema5"]
        c[s], o[s], r2[s] = f["close"], f["open"], f["rsi2"]

    def nxt_open(s, day, fb):
        idx = o[s].index
        j = idx.searchsorted(day, side="right")
        return float(o[s].iloc[j]) if j < len(idx) else fb

    cash, pos, trades, eq, log = CAP0, {}, [], [], []
    for i, day in enumerate(cal):
        for s in list(pos):
            p = pos[s]
            if day not in c[s].index:
                continue
            if bool(ex[s].get(day, False)) or (i - p["i"]) >= 10:
                # exits fill at the CLOSE except in the worst-case leg
                px = (nxt_open(s, day, c[s][day]) if mode == "next_open"
                      else c[s][day])
                px *= (1 - slip)
                cash += p["sh"] * px
                trades.append(px / p["px"] - 1)
                # Attribution only - the return recorded is identical. The x59
                # prereg asks whether a result is carried by the levered ETFs in
                # MIO's list, and that cannot be answered from aggregates.
                log.append({"sym": s, "entry": str(p["day"]), "exit": str(day),
                            "ret": px / p["px"] - 1, "cost": p["sh"] * p["px"]})
                del pos[s]
        if len(pos) < SLOTS:
            cand = [(r2[s].get(day, np.nan), s) for s in names
                    if s not in pos and day in ent[s].index and bool(ent[s][day])]
            cand = [x for x in cand if not np.isnan(x[0])]
            cand.sort()                              # most oversold first
            for _, s in cand[:SLOTS - len(pos)]:
                # entries fill MOO at the next open on both executable legs
                px = (c[s][day] if mode == "ideal_close"
                      else nxt_open(s, day, c[s][day]))
                px *= (1 + slip)
                eqty = cash + sum(p["sh"] * c[k].get(day, p["px"]) for k, p in pos.items())
                size = min(ALLOC * eqty, cash)
                sh = np.floor(size / px)
                if sh < 1:
                    continue
                cash -= sh * px
                pos[s] = {"px": px, "sh": sh, "i": i, "day": day}
        eq.append((day, cash + sum(p["sh"] * c[s].get(day, p["px"]) for s, p in pos.items())))
    E = pd.Series(dict(eq))
    yrs = (E.index[-1] - E.index[0]).days / 365.25
    r = np.array(trades)
    gl = -r[r <= 0].sum() if len(r) else 0
    yby = {}
    for y, g in E.groupby(E.index.year):
        base = E[E.index < g.index[0]]
        s0 = base.iloc[-1] if len(base) else CAP0
        yby[int(y)] = round(100 * (g.iloc[-1] / s0 - 1), 2)
    return {"cagr": round(100 * ((E.iloc[-1] / CAP0) ** (1 / yrs) - 1), 2),
            "maxdd": round(100 * float((E / E.cummax() - 1).min()), 2),
            "trades": len(r), "win": round(100 * float((r > 0).mean()), 1) if len(r) else 0,
            "avg": round(100 * float(r.mean()), 3) if len(r) else 0,
            "pf": round(float(r[r > 0].sum() / gl), 2) if gl > 0 else None,
            "yby": yby,
            # First date the rule could actually fire. If the fetch window is
            # too short, sma200 is NaN for months and the book sits in cash -
            # which silently skips whatever happened in that stretch (for the
            # 2600-day fetch, the entire COVID crash) and flatters every
            # comparison against buy-and-hold. Published so it cannot hide.
            "first_trade": str(min((t["entry"] for t in log), default="")),
            "window": [str(E.index[0].date()), str(E.index[-1].date())],
            "log": log}


def buy_hold(frames, start):
    px = pd.DataFrame({s: f["close"] for s, f in frames.items()})
    px = px[px.index >= pd.Timestamp(start)]
    eq = (1 + px.pct_change().replace([np.inf, -np.inf], np.nan)
          .mean(axis=1, skipna=True).fillna(0.0)).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    return {"cagr": round(100 * (eq.iloc[-1] ** (1 / yrs) - 1), 2),
            "maxdd": round(100 * float((eq / eq.cummax() - 1).min()), 2)}
