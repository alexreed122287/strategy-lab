#!/usr/bin/env python3
"""Freeze a REAL option quote at a ROBERT decision moment.

WHY. The shadow book prices its option leg with Black-Scholes because the
nightly build runs after the close and ROBERT enters at the next open, ~09:45
ET - a moment no evening process can observe. That was acceptable while the
book was a stopgap on the way to a capital pilot. It is not acceptable as the
permanent basis of an indefinite paper test: a model mark carries a 4.5% mean
absolute error against real chains, which is most of a typical trade's return,
and it cannot report a spread at all.

So the quote is captured AT the moment instead of reconstructed after it:

  entry   this script, on a 09:45 ET weekday workflow, over every name the
          previous night's build queued for today's open
  exit    the nightly build, over every position that closed on today's bar -
          the exit is an MOC print, so the build already runs at the right
          moment for it

Both write into data/robert_chain_snaps.json, keyed TICKER|DATE|E or |X, and a
key is never rewritten once present. robert_shadow.py prefers a snapshot over
its model whenever one exists for the leg it is freezing.

Contract selection is the SPEC's rule - shallowest strike whose extrinsic is
under 20% of premium - scored on the real mid. Deliberately not the
delta-nearest-0.80 rule robert_chain_gate.py uses: that one exists to pick
something representative for a liquidity check, while this one has to pick the
contract the strategy would actually buy.

Every name queued is snapped, not just the ones that will fill. Whether a
queued row survives the gap-recovered skip is decided by the nightly build off
daily bars, and duplicating that decision here at 09:45 would be a second
implementation of a rule that must not disagree with itself. An unused
snapshot costs one API call.

Usage:
  robert_chain_snap.py                 snap today's queued entries (windowed)
  robert_chain_snap.py --force         ignore the market-hours window
  robert_chain_snap.py --ticker T --side X --date D --expiry E --strike K
                                       snap ONE known contract (the exit path)
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE = "https://api.tradier.com/v1"
SNAPS = "data/robert_chain_snaps.json"
LEDGER = "data/robert_shadow.json"
MIN_DTE = 30
MAX_EXTRINSIC = 0.20


def token():
    t = os.environ.get("TRADIER_TOKEN")
    if t:
        return t.strip()
    p = os.path.expanduser("~/.tradier_token")
    return open(p).read().strip() if os.path.exists(p) else None


def get(tok, path, **params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(BASE + path + "?" + q,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def third_friday(y, m):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7 + 14)


def is_monthly(ds):
    d = dt.date.fromisoformat(ds)
    return d == third_friday(d.year, d.month)


def load(path=SNAPS):
    if not os.path.exists(path):
        return {"schema": 1, "snaps": {}}
    with open(path) as fh:
        d = json.load(fh)
    d.setdefault("snaps", {})
    return d


def save(d, path=SNAPS):
    d["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    d["count"] = len(d["snaps"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(d, fh, indent=1)
        fh.write("\n")


def quote_row(o, spot):
    """Turn one chain row into a snapshot, or None if it has no two-sided
    market. A one-sided book cannot produce a mid, and a mid is the reference
    every downstream number is expressed against."""
    try:
        bid, ask = float(o.get("bid") or 0), float(o.get("ask") or 0)
    except (TypeError, ValueError):
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    k = float(o.get("strike") or 0)
    g = o.get("greeks") or {}
    intr = max(spot - k, 0.0)
    return {"strike": k, "bid": round(bid, 4), "ask": round(ask, 4),
            "mid": round(mid, 4),
            "spread_pct": round(100.0 * (ask - bid) / mid, 2),
            "delta": round(float(g.get("delta") or 0), 3) or None,
            "iv": round(float(g.get("mid_iv") or 0), 4) or None,
            "oi": int(o.get("open_interest") or 0),
            "volume": int(o.get("volume") or 0),
            "extrinsic_pct": round(100.0 * (mid - intr) / mid, 1)}


def pick_contract(tok, sym, today):
    """The spec contract on the live chain: first monthly >=30 DTE, then the
    shallowest strike whose extrinsic is under 20% of the real mid."""
    q = get(tok, "/markets/quotes", symbols=sym)["quotes"]["quote"]
    if isinstance(q, list):
        q = q[0]
    spot = float(q.get("last") or q.get("close") or q.get("prevclose") or 0)
    if spot <= 0:
        return None, "no_spot"
    ex = get(tok, "/markets/options/expirations", symbol=sym, includeAllRoots="true")
    exps = ((ex.get("expirations") or {}).get("date")) or []
    if isinstance(exps, str):
        exps = [exps]
    monthly = [e for e in exps
               if is_monthly(e) and (dt.date.fromisoformat(e) - today).days >= MIN_DTE]
    if not monthly:
        return None, "no_monthly_expiry"
    exp = monthly[0]
    ch = get(tok, "/markets/options/chains", symbol=sym, expiration=exp, greeks="true")
    opts = ((ch.get("options") or {}).get("option")) or []
    if isinstance(opts, dict):
        opts = [opts]
    best = None
    for o in sorted([c for c in opts if c.get("option_type") == "call"],
                    key=lambda c: float(c.get("strike") or 0)):
        k = float(o.get("strike") or 0)
        if k <= 0 or k >= spot:
            continue
        r = quote_row(o, spot)
        if r and r["extrinsic_pct"] < MAX_EXTRINSIC * 100:
            best = r
    if not best:
        return None, "no_qualifying_strike"
    best.update({"expiry": exp, "spot": round(spot, 4),
                 "dte": (dt.date.fromisoformat(exp) - today).days})
    return best, "ok"


def snap_one(tok, store, sym, side, day, expiry=None, strike=None):
    """Snapshot one leg. Frozen: an existing key is left exactly as it was."""
    key = f"{sym}|{day}|{side}"
    if key in store["snaps"]:
        print(f"already snapped: {key}", file=sys.stderr)
        return False
    stamp = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    try:
        if expiry and strike is not None:
            # Exit path: the contract is already known, so quote exactly it
            # rather than re-selecting - re-selection at exit would silently
            # measure a different option than the one the entry priced.
            occ = "%s%s%s%sC%08d" % (sym, expiry[2:4], expiry[5:7], expiry[8:10],
                                     round(float(strike) * 1000))
            d = get(tok, "/markets/quotes", symbols=occ, greeks="true")
            qt = (d.get("quotes") or {}).get("quote")
            if isinstance(qt, list):
                qt = qt[0] if qt else None
            if not qt:
                print(f"{key}: no quote for {occ}", file=sys.stderr)
                return False
            u = get(tok, "/markets/quotes", symbols=sym)["quotes"]["quote"]
            if isinstance(u, list):
                u = u[0]
            spot = float(u.get("last") or u.get("close") or 0)
            row = quote_row(qt, spot)
            if not row:
                print(f"{key}: {occ} has no two-sided market", file=sys.stderr)
                return False
            row.update({"expiry": expiry, "spot": round(spot, 4),
                        "dte": (dt.date.fromisoformat(expiry)
                                - dt.date.fromisoformat(day)).days,
                        "occ": occ})
            status = "ok"
        else:
            row, status = pick_contract(tok, sym, dt.date.fromisoformat(day))
    except Exception as e:
        print(f"{key}: error {type(e).__name__}: {e}", file=sys.stderr)
        return False
    if status != "ok" or not row:
        print(f"{key}: {status}", file=sys.stderr)
        return False
    row.update({"ticker": sym, "side": side, "date": day, "captured": stamp})
    store["snaps"][key] = row
    print(f"snapped {key}: {row['expiry']} {row['strike']}C "
          f"{row['bid']}/{row['ask']} mid {row['mid']} spread {row['spread_pct']}%")
    return True


def main():
    a = sys.argv[1:]
    tok = token()
    if not tok:
        sys.exit("no Tradier token (TRADIER_TOKEN or ~/.tradier_token)")
    store = load()

    def opt(n, d=None):
        return a[a.index(n) + 1] if n in a else d

    if "--ticker" in a:
        sym = opt("--ticker").upper()
        side = (opt("--side", "E") or "E").upper()
        day = opt("--date") or dt.date.today().isoformat()
        exp, k = opt("--expiry"), opt("--strike")
        changed = snap_one(tok, store, sym, side, day, exp,
                           float(k) if k else None)
        if changed:
            save(store)
        return

    now = dt.datetime.now(ZoneInfo("America/New_York"))
    # A window, not an hour. Same lesson robert_chain_gate.py records: GitHub's
    # scheduler drifted to 10:03 and 10:56 ET on 2026-08-17 and an `hour == 9`
    # guard rejected both firings while the workflow still reported success.
    # The frozen-key check below, not the clock, is what prevents a duplicate.
    ok_window = (now.weekday() < 5
                 and (9, 30) <= (now.hour, now.minute) <= (11, 30))
    if not ok_window and "--force" not in a:
        print(f"outside the entry window ({now:%a %H:%M ET}) - nothing snapped")
        return

    if not os.path.exists(LEDGER):
        sys.exit(f"no ledger at {LEDGER}")
    led = json.load(open(LEDGER))
    queued = led.get("queued") or []
    if not queued:
        print("nothing queued for this open - nothing to snap")
        return
    day = now.date().isoformat()
    changed = 0
    for row in queued:
        if snap_one(tok, store, row["t"], "E", day):
            changed += 1
    if changed:
        save(store)
    print(f"{changed} entry snapshot(s) taken; store holds {len(store['snaps'])}")


if __name__ == "__main__":
    main()
