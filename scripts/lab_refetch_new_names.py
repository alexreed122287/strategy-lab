#!/usr/bin/env python3
"""Re-fetch the x45 session names from Tradier into the local brain, and diff
them against the Robinhood-basis series the session used.

Why: x45 completed the z-score's MIO universe using a session Robinhood fetch
for names the brain lacked. Robinhood is a usable but second-choice vendor -
it pads pre-listing history with zero-volume flat rows (x45 v2 removed 29,856
such bars) and adjusts spin-offs/special dividends differently (GE p99 4.7%,
OHI 1.8%). Tradier is the program's data authority. This script replaces the
RH-basis series with Tradier history and reports where the two disagree, so
the book trades on audited data.

Run on the Mac (TRADIER_TOKEN must be in the shell env - never committed):

  export TRADIER_TOKEN=...            # already set if daily_build.sh works
  python3 scripts/lab_refetch_new_names.py \
      --brain ~/Projects/market-data-brain \
      --names data/x45_rh_basis_names.json \
      --rh-dir ""                     # optional: dir of session RH parquets to diff
      [--start 2018-01-01] [--dry-run]

What it does per symbol:
  1. GET /v1/markets/history (daily, split-adjusted) from --start to today
  2. writes {brain}/daily/{SYM}.parquet with the brain's schema
     (date, open, high, low, close, volume, source="tradier")
  3. if --rh-dir points at the session parquets, computes the close-price
     divergence (median / p99 / worst day) on overlapping dates
  4. writes a JSON report next to the brain: results/x45_tradier_refetch.json

Names that Tradier cannot serve are listed as "unavailable" - they stay on
the RH basis and remain flagged on the dashboard. Nothing is deleted: a
symbol that fails to fetch keeps whatever series it already had.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.environ.get("TRADIER_API_BASE", "https://api.tradier.com")


def fetch_history(sym, token, start, end):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily",
                                "start": start, "end": end})
    req = urllib.request.Request(
        f"{API_BASE}/v1/markets/history?{q}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    days = ((data or {}).get("history") or {}).get("day")
    if not days:
        return []
    if isinstance(days, dict):
        days = [days]
    return [d for d in days if d.get("close") is not None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", required=True)
    ap.add_argument("--names", required=True,
                    help="JSON list of symbols (data/x45_rh_basis_names.json)")
    ap.add_argument("--rh-dir", default="",
                    help="optional dir of session RH parquets, for the diff")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--earnings", action="store_true",
                    help="also seed empty earnings/{SYM}.json files for these "
                         "names so the brain's refresh_earnings.py (Yahoo) "
                         "picks them up, then run it")
    ap.add_argument("--earnings-only", action="store_true",
                    help="skip the price re-fetch; do the earnings step only")
    a = ap.parse_args()

    token = os.environ.get("TRADIER_TOKEN")
    if not token and not a.earnings_only:
        sys.exit("TRADIER_TOKEN not set - export it in your shell, never commit it")

    import pandas as pd

    brain = os.path.expanduser(a.brain)
    daily = os.path.join(brain, "daily")
    os.makedirs(daily, exist_ok=True)
    names = json.load(open(a.names))
    if isinstance(names, dict):
        names = names.get("names") or names.get("rh_names") or []
    end = datetime.date.today().isoformat()

    report = {"as_of": end, "start": a.start, "n_requested": len(names),
              "written": [], "unavailable": [], "diffs": {}, "flags": []}

    if a.earnings or a.earnings_only:
        # refresh_earnings.py only iterates symbols that ALREADY have a file,
        # so seed empties first; then Yahoo fills real history (limit=40).
        edir = os.path.join(brain, "earnings")
        os.makedirs(edir, exist_ok=True)
        seeded = []
        for sym in sorted(names):
            p = os.path.join(edir, f"{sym}.json")
            if not os.path.exists(p):
                if not a.dry_run:
                    json.dump([], open(p, "w"))
                seeded.append(sym)
        print(f"earnings: seeded {len(seeded)} empty files in {edir}",
              file=sys.stderr)
        report["earnings_seeded"] = seeded
        rp = os.path.join(brain, "scripts", "refresh_earnings.py")
        if os.path.exists(rp) and not a.dry_run:
            print("earnings: running the brain's refresh_earnings.py (Yahoo) - "
                  "this takes a while for a few hundred names ...", file=sys.stderr)
            os.system(f"python3 {rp!r}")
            filled = sum(1 for s in seeded
                         if json.load(open(os.path.join(edir, f"{s}.json"))))
            print(f"earnings: {filled}/{len(seeded)} seeded names now carry dates",
                  file=sys.stderr)
            report["earnings_filled"] = filled
        else:
            print(f"earnings: {rp} not found - seed files written, run the "
                  "brain's refresher yourself", file=sys.stderr)
        if a.earnings_only:
            outdir = os.path.join(brain, "results")
            os.makedirs(outdir, exist_ok=True)
            json.dump(report, open(os.path.join(outdir, "x45_tradier_refetch.json"), "w"), indent=1)
            print("earnings-only run complete; retire data/earnings_seed/ from "
                  "the repo once the brain files are populated.", file=sys.stderr)
            return

    for i, sym in enumerate(sorted(names), 1):
        try:
            days = fetch_history(sym, token, a.start, end)
        except urllib.error.HTTPError as e:
            print(f"[{i}/{len(names)}] {sym}: HTTP {e.code}", file=sys.stderr)
            report["unavailable"].append({"symbol": sym, "reason": f"HTTP {e.code}"})
            continue
        except Exception as e:                                  # noqa: BLE001
            print(f"[{i}/{len(names)}] {sym}: {e}", file=sys.stderr)
            report["unavailable"].append({"symbol": sym, "reason": str(e)[:120]})
            continue
        if not days:
            report["unavailable"].append({"symbol": sym, "reason": "no data"})
            print(f"[{i}/{len(names)}] {sym}: no data", file=sys.stderr)
            continue

        df = pd.DataFrame(days)[["date", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values("date").reset_index(drop=True)
        df["source"] = "tradier"
        # same hygiene x45 v2 applied to the RH series: no zero-volume padding
        pad = int((df["volume"] <= 0).sum())
        if pad:
            df = df[df["volume"] > 0].reset_index(drop=True)
            report["flags"].append({"symbol": sym, "zero_volume_rows_dropped": pad})

        if a.rh_dir:
            rp = os.path.join(os.path.expanduser(a.rh_dir), f"{sym}.parquet")
            if os.path.exists(rp):
                rh = pd.read_parquet(rp)
                rh["date"] = pd.to_datetime(rh["date"]).dt.strftime("%Y-%m-%d")
                m = df.merge(rh[["date", "close"]], on="date", suffixes=("_td", "_rh"))
                if len(m) > 50:
                    rel = ((m["close_td"] - m["close_rh"]).abs()
                           / m["close_td"].abs() * 100)
                    worst = m.loc[rel.idxmax()]
                    report["diffs"][sym] = {
                        "overlap_days": int(len(m)),
                        "median_pct": round(float(rel.median()), 4),
                        "p99_pct": round(float(rel.quantile(0.99)), 3),
                        "worst_pct": round(float(rel.max()), 3),
                        "worst_date": str(worst["date"])}

        if not a.dry_run:
            df.to_parquet(os.path.join(daily, f"{sym}.parquet"), index=False)
        report["written"].append(sym)
        print(f"[{i}/{len(names)}] {sym}: {len(df)} bars "
              f"{df['date'].iloc[0]}->{df['date'].iloc[-1]}", file=sys.stderr)
        time.sleep(0.35)                                   # be kind to the API

    big = sorted((s for s, d in report["diffs"].items() if d["p99_pct"] > 0.5),
                 key=lambda s: -report["diffs"][s]["p99_pct"])
    report["material_divergence"] = [{"symbol": s, **report["diffs"][s]} for s in big]

    outdir = os.path.join(brain, "results")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "x45_tradier_refetch.json")
    json.dump(report, open(out, "w"), indent=1)
    print(f"\nwrote {len(report['written'])} symbols; "
          f"{len(report['unavailable'])} unavailable; "
          f"{len(big)} with p99 close divergence > 0.5% -> {out}", file=sys.stderr)
    if big:
        print("material divergences (re-check these before trusting their stats):",
              file=sys.stderr)
        for s in big[:25]:
            d = report["diffs"][s]
            print(f"  {s:6s} p99 {d['p99_pct']:6.2f}%  worst {d['worst_pct']:6.2f}% "
                  f"on {d['worst_date']}", file=sys.stderr)
    print("\nNext: re-run the z-score sim against the refreshed brain and compare "
          "to data/x45v2_results.json before treating any of it as real-money "
          "evidence.", file=sys.stderr)


if __name__ == "__main__":
    main()
