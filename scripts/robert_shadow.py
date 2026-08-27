#!/usr/bin/env python3
"""ROBERT shadow forward book - the automated paper ledger for the ROBERT arm.

Same law as shadow_book.py, kept in its own state file so the central ledger
is untouched: each nightly build this script
  1. FILLS entries queued at the previous build at the NEXT session's open
     (ROBERT's validated basis is next-open; the spec's gap-recovered skip
     applies - a queued fill whose open is already above the prior SMA5 is
     skipped and counted, exactly as production would skip it),
  2. EVALUATES every open position on the newest bar and closes at that bar's
     close when close > SMA5 or the hold reaches 10 bars (MOC print),
  3. QUEUES tonight's TAKEs - RSI(2)<10, close>SMA200, RS252 vs SPY>+40%,
     no earnings within 7 days, rv-blend IV proxy <=60% - one open or queued
     position per symbol.

This is the STOCK LEG, recorded at 0.02%/side (the vehicle-study assumption)
and labeled as such. The option wrapper clears its own cost only when the
stock leg averages >= +0.9%/trade - that bar is drawn on the ledger. The
wrapper's realized friction is measured separately, by hand, in the
Paper-Fill Log; this ledger is the skip-free signal-evidence machine, and 20
closed trades here is one leg of the go-live gate.

State: data/robert_shadow.json (committed by the daily build).
Output: static HTML spliced between ROBSHADOW markers in robert.html.

Usage:
  robert_shadow.py --bars bars.json --page robert.html --universe robert_universe.txt
      [--earnings earnings.json] [--ledger data/robert_shadow.json] [--splice]
"""
import json, os, re, sys, time, urllib.parse, urllib.request
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robert_option_leg as OL

API = "https://api.tradier.com"
SM, EM = "<!-- ROBSHADOW:START -->", "<!-- ROBSHADOW:END -->"
FR_SIDE = 0.0002
GATE_TARGET = 20
WRAPPER_BAR = 0.009

def opt(a, n, d=None): return a[a.index(n)+1] if n in a else d

def token():
    t = os.environ.get("TRADIER_TOKEN")
    if t: return t.strip()
    p = os.path.expanduser("~/.tradier_token")
    return open(p).read().strip() if os.path.exists(p) else None

def fetch(sym, tok, start):
    q = urllib.parse.urlencode({"symbol": sym, "interval": "daily", "start": start})
    req = urllib.request.Request(API + "/v1/markets/history?" + q,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    days = (d.get("history") or {}).get("day") or []
    if isinstance(days, dict): days = [days]
    return [[x["date"], float(x["open"]), float(x["high"]), float(x["low"]),
             float(x["close"]), float(x.get("volume") or 0)]
            for x in days if x.get("close") is not None]

def wilder_rsi2(cl):
    au = ad = None; prev = cl[0]
    for c in cl[1:]:
        d = c - prev; prev = c
        up, dn = max(d, 0.0), max(-d, 0.0)
        au = up if au is None else au + 0.5*(up-au)
        ad = dn if ad is None else ad + 0.5*(dn-ad)
    if not ad: return 100.0
    return 100.0 - 100.0/(1.0 + au/ad)

def sma(v, n): return sum(v[-n:])/n if len(v) >= n else None

def rv_blend(cl):
    import math
    lr = [math.log(cl[i]/cl[i-1]) for i in range(1, len(cl))]
    if len(lr) < 60: return None
    def sd(x):
        m = sum(x)/len(x)
        return (sum((y-m)**2 for y in x)/(len(x)-1))**0.5 if len(x) > 1 else 0.0
    r5, r20, r60 = (sd(lr[-n:])*(252**0.5) for n in (5, 20, 60))
    return max(0.25*r5 + 0.40*r20 + 0.35*r60, 0.05)


# ---------------------------------------------------------------- option leg
#
# The ledger above is the STOCK leg and stays the ledger: it is what the 20-row
# go-live gate counts and what the +0.9%/trade wrapper bar is drawn against.
# What follows expresses the same rows in the vehicle the spec actually buys.
#
# FROZEN ON FIRST SIGHT. A row's contract, its entry premium and its sizing are
# written once and never recomputed. The reason is the same one that put a
# `gate` field in robert_chain_gate.py: a figure recomputed under later inputs
# is a figure that silently restates history. rv_blend at the entry bar drifts
# as bars accumulate, so a nightly recompute would quietly rewrite what an
# already-closed trade "made". Instead the pricing inputs are stored beside the
# output, and the output is re-derivable from them at any time.

def sigma_at(seq, entry_date):
    """rv-blend IV proxy from the closes STRICTLY BEFORE the entry bar - the
    same number the scan card prints and gates at <=60%, computed on the
    information a 09:45 entry could actually have had."""
    cl = []
    for r in seq:
        if r[0] >= entry_date:
            break
        cl.append(r[4])
    return rv_blend(cl) if len(cl) >= 61 else None


_STRIKES = {}


def real_strikes(t, expiry, tok):
    """The listed strike set for one expiry, cached for the run. Fail-soft:
    None hands select_strike back to its offline grid, which is wrong often
    enough (PWR lists 10s, not 5s) that the frozen leg records which path it
    took in `strike_src`."""
    if not tok:
        return None
    key = (t, expiry)
    if key in _STRIKES:
        return _STRIKES[key]
    out = None
    try:
        q = urllib.parse.urlencode({"symbol": t, "expiration": expiry})
        req = urllib.request.Request(API + "/v1/markets/options/strikes?" + q,
            headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        ks = (d.get("strikes") or {}).get("strike") or []
        if isinstance(ks, (int, float)):
            ks = [ks]
        ks = [float(k) for k in ks]
        out = ks or None
    except Exception:
        out = None
    _STRIKES[key] = out
    return out


def freeze_entry(row, bars, tok=None):
    """Attach the frozen entry leg to an open/closed row that lacks one."""
    if row.get("opt") or row["t"] not in bars:
        return
    sig = sigma_at(bars[row["t"]], row["entry_date"])
    if not sig:
        return
    exp = OL.first_monthly(dt.date.fromisoformat(row["entry_date"])).isoformat()
    leg = OL.price_leg(row["entry_px"], row["entry_date"], sig, expiry=exp,
                       strikes=real_strikes(row["t"], exp, tok))
    if leg:
        row["opt"] = leg


def freeze_exit(opt, entry_px, entry_date, exit_px, exit_date):
    """Graft the exit onto an already-frozen contract. Reprices the SAME strike
    and expiry at the frozen sigma, so prem_paid below is bit-identical to the
    frozen one and the return is computed against what was actually recorded."""
    leg = OL.price_leg(entry_px, entry_date, opt["sigma"], exit_px, exit_date,
                       expiry=opt["expiry"], strike=opt["strike"])
    if not leg:
        return
    for k in ("exit_mid", "exit_recv", "ret", "pnl"):
        opt[k] = leg[k]


def occ(t, expiry, strike):
    y, m, d = expiry.split("-")
    return "%s%s%s%sC%08d" % (t, y[2:], m, d, round(strike * 1000))


def chain_mid(t, expiry, strike, tok):
    """Live quoted mid for one contract. Fail-soft by design: a mark that
    cannot be fetched falls back to the model rather than blanking the row or
    killing the build. Returns None on anything unexpected."""
    if not tok:
        return None
    try:
        q = urllib.parse.urlencode({"symbols": occ(t, expiry, strike), "greeks": "false"})
        req = urllib.request.Request(API + "/v1/markets/quotes?" + q,
            headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        qt = (d.get("quotes") or {}).get("quote")
        if isinstance(qt, list):
            qt = qt[0] if qt else None
        if not qt:
            return None
        b, a = qt.get("bid"), qt.get("ask")
        if not b or not a or float(b) <= 0 or float(a) <= 0:
            return None
        return (float(b) + float(a)) / 2.0
    except Exception:
        return None


def book_stats(closed, open_marks, as_of):
    """Forward-record statistics on the option leg, model-mark basis.

    Every ratio here needs a sample the book does not have yet. They are
    computed anyway and reported with their n, because the alternative -
    showing nothing until row 20 - hides the shape of what is accumulating.
    What is NOT done is dressing three trades as an annual rate: `meaningful`
    is False below the gate target and the page greys the ratios accordingly.
    """
    rows = [c for c in closed if c.get("opt", {}).get("pnl") is not None]
    pnl = [c["opt"]["pnl"] for c in rows]
    ret = [c["opt"]["ret"] for c in rows]
    n = len(rows)
    unreal = sum(m["pnl"] for m in open_marks)
    st = {"n": n, "realised": sum(pnl), "unrealised": unreal,
          "net": sum(pnl) + unreal, "meaningful": n >= GATE_TARGET,
          "open_cost": sum(m["cost"] for m in open_marks)}
    if not n:
        return st
    wins = [x for x in pnl if x > 0]
    loss = [x for x in pnl if x <= 0]
    st["win_pct"] = 100.0 * len(wins) / n
    st["pf"] = (sum(wins) / abs(sum(loss))) if loss and sum(loss) else None
    st["avg_ret"] = 100.0 * sum(ret) / n
    st["avg_pnl"] = sum(pnl) / n
    st["best"] = max(ret) * 100.0
    st["worst"] = min(ret) * 100.0
    # Downside deviation about a zero target, per trade, annualised at the
    # spec's stated 65-trade-a-year cadence. Undefined while no trade has lost.
    dd = (sum(min(r, 0.0) ** 2 for r in ret) / n) ** 0.5
    st["sortino"] = ((sum(ret) / n) * 65.0) / (dd * (65.0 ** 0.5)) if dd > 0 else None
    # Equity path over the sleeve, closed trades in exit order, open MTM last.
    eq = OL.SLEEVE
    peak, mdd = eq, 0.0
    for c in sorted(rows, key=lambda x: x["exit_date"]):
        eq += c["opt"]["pnl"]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    eq_now = eq + unreal
    peak = max(peak, eq_now)
    mdd = min(mdd, eq_now / peak - 1.0)
    st["max_dd"] = 100.0 * mdd
    st["ret_sleeve"] = 100.0 * (eq_now / OL.SLEEVE - 1.0)
    first = min(c["entry_date"] for c in rows)
    days = (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(first)).days
    st["days"] = days
    st["since"] = first
    if days >= 1 and eq_now > 0:
        st["cagr"] = 100.0 * ((eq_now / OL.SLEEVE) ** (365.0 / days) - 1.0)
    return st

def main():
    a = sys.argv[1:]
    bars_p, page_p, uni_p = opt(a,"--bars"), opt(a,"--page"), opt(a,"--universe")
    earn_p = opt(a,"--earnings"); led_p = opt(a,"--ledger","data/robert_shadow.json")
    if not (bars_p and page_p and uni_p): sys.exit("--bars, --page, --universe required")
    bars = json.load(open(bars_p))
    uni = [t.strip() for t in open(uni_p).read().replace("\n", ",").split(",") if t.strip()]
    if len(uni) < 60: sys.exit(f"fail-closed: universe has {len(uni)} names")
    earn = {}
    if earn_p and os.path.exists(earn_p):
        try:
            for k, v in json.load(open(earn_p)).items():
                earn[k] = [str(x)[:10] for x in (v if isinstance(v, list) else [v])]
        except Exception: earn = {}
    if not earn:
        seedp = os.path.join(os.path.dirname(os.path.abspath(page_p)), "data", "robert_earnings.json")
        if os.path.exists(seedp):
            try:
                for k, v in json.load(open(seedp)).items():
                    earn[k] = [str(x)[:10] for x in (v if isinstance(v, list) else [v])]
                print("earnings: repo seed fallback (" + str(len(earn)) + " names)", file=sys.stderr)
            except Exception:
                pass
    need = [s for s in uni + ["SPY"] if s not in bars]
    tok = token()
    if need and tok:
        start = (dt.date.today() - dt.timedelta(days=560)).isoformat()
        for s in need:
            try:
                sr = fetch(s, tok, start)
                if len(sr) >= 210: bars[s] = sr
            except Exception: pass
            time.sleep(0.4)
    if "SPY" not in bars: sys.exit("fail-closed: no SPY")
    spy_c = [r[4] for r in bars["SPY"]]
    as_of = bars["SPY"][-1][0]
    if len(spy_c) < 260: sys.exit("fail-closed: SPY short")
    spy_r = spy_c[-1]/spy_c[-253] - 1

    # Earnings-feed forward coverage - same guard as robert_scan.py, duplicated
    # because both scripts are deliberately standalone. len(earn) flatters: a
    # name whose only dates are past still counts while the 7-day gate has
    # silently stopped seeing it (the Z-Score seed failure mode, 08-11-2026).
    # stderr only: without --splice this script's stdout IS the page HTML.
    e_live = sum(1 for v in earn.values() if any(x >= as_of for x in v))
    if not earn:
        print("WARNING: no earnings feed at all - the no-earnings-within-7-days "
              "gate is INERT for this ledger pass", file=sys.stderr)
    else:
        e_pct = 100.0 * e_live / len(earn)
        e_msg = (f"earnings feed: {e_live}/{len(earn)} names forward-dated "
                 f"({e_pct:.0f}%) vs bar {as_of}")
        if e_live == 0:
            print("WARNING: earnings feed fully spent - the no-earnings-within-"
                  "7-days gate is INERT for this ledger pass. " + e_msg,
                  file=sys.stderr)
        elif e_pct < 50:
            print("WARNING: earnings feed draining - refresh it. " + e_msg,
                  file=sys.stderr)
        else:
            print(e_msg, file=sys.stderr)

    st = {"open": [], "queued": [], "closed": [], "skipped": [], "closed_total": 0}
    if os.path.exists(led_p):
        try: st.update(json.load(open(led_p)))
        except Exception: sys.exit("fail-closed: ledger unreadable, refusing to overwrite")
    if st.get("last_as_of") == as_of:
        print(f"robert_shadow: bar {as_of} already processed", file=sys.stderr)
    busy = {p["t"] for p in st["open"]} | {q["t"] for q in st["queued"]}
    # Names whose fill/exit could not be evaluated this run. See the stamp at
    # the bottom: a skip that is not recorded is a skip that becomes permanent.
    unchecked = []

    still_q = []
    for q in st["queued"]:
        t = q["t"]
        if t not in bars:
            # NOT a silent continue. shadow_book.py learned this the hard way:
            # a name absent from the fetch gets no fill check, and because
            # last_as_of is stamped unconditionally below, the bar is recorded
            # as processed and never revisited. The position then holds its
            # slot and its cash forever.
            print("WARNING: fill UNCHECKED %s - no bars this run; stays queued"
                  % t, file=sys.stderr)
            q["unchecked"] = as_of
            unchecked.append("queued/" + t)
            still_q.append(q); continue
        seq = bars[t]; idx = None
        for i, r in enumerate(seq):
            if r[0] > q["signal_date"]: idx = i; break
        if idx is None: still_q.append(q); continue
        o = seq[idx][1]
        prior_c = [r[4] for r in seq[:idx]]
        p5 = sma(prior_c, 5)
        if p5 is not None and o > p5:
            st["skipped"].append({"t": t, "signal_date": q["signal_date"],
                                  "why": "gap-recovered (open > prior SMA5)"})
            busy.discard(t); continue
        st["open"].append({"t": t, "signal_date": q["signal_date"],
                           "entry_date": seq[idx][0], "entry_px": o})
    st["queued"] = still_q

    # Freeze the option leg on anything now open - newly filled rows and any
    # row that predates this overlay (the backfill). Runs BEFORE the exit loop
    # so a position that opens and closes across the same pass still carries a
    # contract into its closed record.
    for p in st["open"]:
        freeze_entry(p, bars, tok)

    still_o = []
    for p in st["open"]:
        t = p["t"]
        if t not in bars:
            print("WARNING: exit UNCHECKED %s - no bars this run; position held"
                  % t, file=sys.stderr)
            p["exit_unchecked"] = as_of
            unchecked.append("open/" + t)
            still_o.append(p); continue
        seq = bars[t]
        di = {r[0]: i for i, r in enumerate(seq)}
        ei = di.get(p["entry_date"])
        if ei is None:
            print("WARNING: exit UNCHECKED %s - entry bar %s missing from its "
                  "series; position held" % (t, p["entry_date"]), file=sys.stderr)
            p["exit_unchecked"] = as_of
            unchecked.append("open/" + t)
            still_o.append(p); continue
        p.pop("exit_unchecked", None)
        closed = False
        for j in range(ei + 1, len(seq)):
            cl = [r[4] for r in seq[:j+1]]
            s5 = sma(cl, 5)
            bars_held = j - ei
            if (s5 is not None and cl[-1] > s5) or bars_held >= 10:
                x = seq[j][4]
                net = (x*(1-FR_SIDE))/(p["entry_px"]*(1+FR_SIDE)) - 1.0
                rec = {"t": t, "entry_date": p["entry_date"],
                    "exit_date": seq[j][0], "entry_px": round(p["entry_px"],4),
                    "exit_px": round(x,4), "bars": bars_held,
                    "reason": "SMA5" if (s5 is not None and cl[-1] > s5) else "TIME",
                    "net": round(net, 5)}
                if p.get("opt"):
                    rec["opt"] = p["opt"]
                    freeze_exit(rec["opt"], p["entry_px"], p["entry_date"],
                                x, seq[j][0])
                st["closed"].append(rec)
                st["closed_total"] = len(st["closed"])
                busy.discard(t); closed = True; break
        if not closed: still_o.append(p)
    st["open"] = still_o

    # Closed rows written before this overlay existed carry no contract. Price
    # them once, from the entry-bar information they were taken on, and freeze.
    for c in st["closed"]:
        if c.get("opt"):
            continue
        freeze_entry(c, bars, tok)
        if c.get("opt"):
            freeze_exit(c["opt"], c["entry_px"], c["entry_date"],
                        c["exit_px"], c["exit_date"])

    new_q = []
    for t in uni:
        if t in busy or t not in bars: continue
        seq = bars[t]; c = [r[4] for r in seq]
        if len(c) < 253: continue
        # PER-SYMBOL STALENESS. robert_scan.py refuses any name whose last bar
        # != the corpus as_of, with the reason written out: a frozen feed's
        # RS252 window measured against SPY's CURRENT 252-day return "can
        # manufacture a phantom TAKE on a name that has not traded in months".
        # That guard was never copied here, though the earnings guard next to
        # it was (with the comment "duplicated because both scripts are
        # deliberately standalone"). Consequence, reproduced end to end: the
        # scan splices "Dropped as stale: GM@2026-06-23" into ROBSIG while this
        # file splices "Queued for the next open: GM" into ROBSHADOW, one card
        # below, same file, same run. Worse, signal_date is stamped with SPY's
        # date, so no bar in the name's own series is ever > signal_date: the
        # fill loop can never advance it, it stays in `busy` so the name can
        # never re-signal, and the line reprints forever.
        if seq[-1][0] != as_of:
            print("robert_shadow: dropped as stale %s@%s (corpus %s)"
                  % (t, seq[-1][0], as_of), file=sys.stderr)
            continue
        r2 = wilder_rsi2(c[-120:]); s200 = sma(c, 200)
        if s200 is None or c[-1] <= s200 or r2 >= 10: continue
        rs = c[-1]/c[-253] - 1 - spy_r
        if rs <= 0.40: continue
        blocked = False
        for ed in earn.get(t, []):
            try:
                dd = (dt.date.fromisoformat(ed) - dt.date.fromisoformat(as_of)).days
                if 0 <= dd <= 7: blocked = True
            except Exception: pass
        if blocked: continue
        ivp = rv_blend(c)
        if ivp is None or ivp > 0.60: continue
        st["queued"].append({"t": t, "signal_date": as_of, "rsi2": round(r2, 2)})
        new_q.append(t); busy.add(t)

    # Advance the run stamp ONLY when everything held was actually evaluated.
    # Same reasoning as shadow_book.py: holding it back costs one repeated pass
    # (queueing dedupes on `busy`, fills only touch queued rows), while burying
    # an unchecked exit costs a slot forever.
    if unchecked:
        print("WARNING: %d position(s) unevaluated this run (%s). Holding "
              "last_as_of at %s so the next run retries."
              % (len(unchecked), ", ".join(sorted(unchecked)), st.get("last_as_of")),
              file=sys.stderr)
        st["unchecked_as_of"] = as_of
        st["unchecked"] = sorted(unchecked)
    else:
        st.pop("unchecked_as_of", None)
        st.pop("unchecked", None)
        st["last_as_of"] = as_of
    os.makedirs(os.path.dirname(led_p) or ".", exist_ok=True)
    json.dump(st, open(led_p, "w"), indent=1)

    # ---- mark the open book -------------------------------------------
    # Model marks drive every published statistic, so entry and exit sit on ONE
    # basis and a 4.5% pricing error cannot leak into a 7% return. The live
    # chain mid is fetched alongside and shown next to the model mark as a
    # running check on the model - never mixed into the arithmetic.
    open_marks = []
    for p in st["open"]:
        o = p.get("opt")
        if not o or p["t"] not in bars:
            continue
        spot = bars[p["t"]][-1][4]
        cm = chain_mid(p["t"], o["expiry"], o["strike"], tok)
        m = OL.mark_leg(o, spot, as_of)
        held = (dt.date.fromisoformat(as_of)
                - dt.date.fromisoformat(p["entry_date"])).days
        m.update({"t": p["t"], "opt": o, "spot": spot, "held": held,
                  "entry_date": p["entry_date"], "entry_px": p["entry_px"],
                  "contracts": o["contracts"], "cost": o["cost"],
                  "stock_ret": spot / p["entry_px"] - 1.0,
                  "chain_mid": cm,
                  "chain_gap": (cm / m["mark_mid"] - 1.0) if cm else None})
        open_marks.append(m)

    bk = book_stats(st["closed"], open_marks, as_of)

    # ---- stock-leg gate line (unchanged instrument) --------------------
    nets = [c["net"] for c in st["closed"]]
    wr = 100.0*sum(1 for n in nets if n > 0)/len(nets) if nets else None
    avg = 100.0*sum(nets)/len(nets) if nets else None
    gate_left = max(GATE_TARGET - len(nets), 0)

    def mny(v, dp=0):
        return ("+$" if v >= 0 else "&minus;$") + ("{:,.%df}" % dp).format(abs(v))

    def sgn(v):
        return "pos" if v > 0 else ("neg" if v < 0 else "")

    def pct(v, dp=2, sign=True):
        """The page renders negatives with a real minus sign, not a hyphen -
        the tiles at the top of it already do. Percentages went out as hyphens
        in the first cut and sat next to &minus;-formatted dollars."""
        f = ("{:+.%df}" % dp) if sign else ("{:.%df}" % dp)
        return f.format(v).replace("-", "&minus;") + "%"

    def contract(o):
        y, m, d = o["expiry"].split("-")
        mon = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"][int(m)-1]
        k = ("%g" % o["strike"])
        return f'{mon}{int(d)} {k}C'

    def tile(k, v, d, cls=""):
        return (f'<div class="tile"><div class="k">{k}</div>'
                f'<div class="v {cls}">{v}</div><div class="d">{d}</div></div>')

    # ---- headline tiles ------------------------------------------------
    n = bk["n"]
    dim = "" if bk["meaningful"] else "dim"
    ratio_note = ("" if bk["meaningful"]
                  else f'n={n} - not meaningful until {GATE_TARGET}')
    tiles = tile("Net P&amp;L", mny(bk["net"]),
                 f'{n} closed + {len(open_marks)} open, model marks',
                 sgn(bk["net"]))
    if n:
        tiles += tile("Return on sleeve", pct(bk["ret_sleeve"]),
                      f'$100,000 sleeve &middot; since {bk["since"]} '
                      f'({bk["days"]}d)', sgn(bk["ret_sleeve"]))
        tiles += tile("Trades", f'{n} / {GATE_TARGET}',
                      f'closed / go-live gate &middot; {len(open_marks)} open')
        tiles += tile("Win rate", pct(bk["win_pct"], 0, False),
                      f'{sum(1 for c in st["closed"] if c.get("opt",{}).get("pnl",0)>0)} of {n} closed')
        pf = ("no loss yet" if bk["pf"] is None else f'{bk["pf"]:.2f}')
        tiles += tile("Profit factor", pf,
                      ratio_note or "gross win / gross loss, $", dim)
        tiles += tile("Avg / trade", pct(bk["avg_ret"], 1),
                      f'{mny(bk["avg_pnl"])} per closed contract set',
                      sgn(bk["avg_ret"]))
        srt = ("&mdash;" if bk["sortino"] is None else f'{bk["sortino"]:.2f}')
        tiles += tile("Sortino", srt,
                      "needs a losing trade" if bk["sortino"] is None
                      else (ratio_note or "annualised at 65 trades/yr"), dim)
        cg = bk.get("cagr")
        tiles += tile("CAGR", "&mdash;" if cg is None else pct(cg, 0),
                      f'annualised from {bk["days"]} days - '
                      f'{ratio_note or "on the closed equity path"}', dim)
        tiles += tile("Max drawdown", pct(bk["max_dd"], 1, False),
                      "closed-trade equity, incl. open MTM", dim)
    stats_html = f'<div class="tiles compact">{tiles}</div>'

    # The stock leg and the option leg do NOT agree on what a win is, and the
    # gap between them is the wrapper bar made visible: a stock move too small
    # to clear 1.25% in and 2.5% out is a losing call on a winning trade. Two
    # win rates side by side with no explanation reads as a bug, so name the
    # rows that diverge rather than leaving the reader to find them.
    split = [c for c in st["closed"]
             if c.get("opt", {}).get("ret") is not None
             and (c["net"] > 0) != (c["opt"]["ret"] > 0)]
    if split:
        who = ", ".join(f'{c["t"]} ({pct(100*c["net"])} stock &rarr; '
                        f'{pct(100*c["opt"]["ret"],1)} call)' for c in split[:6])
        stats_html += (
            '<p class="small"><b>The two win rates differ on purpose.</b> The '
            f'stock leg calls {len(nets)-len([c for c in st["closed"] if c["net"]<=0])} '
            f'of {len(nets)} a win; the option leg calls '
            f'{sum(1 for c in st["closed"] if c.get("opt",{}).get("ret",0)>0)} of '
            f'{bk["n"]}. The rows that split: {who}. That is the +0.9%/trade '
            'wrapper bar doing its job - a move too small to cover 1.25% in and '
            '2.5% out is a losing call on a winning trade, and it is the single '
            'reason the stock ledger alone cannot tell you whether ROBERT '
            'makes money.</p>')

    # ---- open book -----------------------------------------------------
    rowsh = ""
    if open_marks:
        body = ""
        for m in open_marks:
            o = m["opt"]
            ch = ("&mdash;" if m["chain_mid"] is None else
                  f'{m["chain_mid"]:.2f} <span class="tag">'
                  + pct(100*m["chain_gap"], 1) + " vs model</span>")
            body += (f'<tr><td><b>{m["t"]}</b></td><td>{contract(o)}</td>'
                     f'<td>{m["entry_date"]}</td><td>{m["held"]}</td>'
                     f'<td class="{sgn(m["stock_ret"])}">{pct(100*m["stock_ret"])}</td>'
                     f'<td>{o["prem_paid"]:.2f}</td><td>{m["mark_mid"]:.2f}</td>'
                     f'<td>{ch}</td><td>{o["contracts"]}</td>'
                     f'<td class="{sgn(m["ret"])}">{pct(100*m["ret"],1)}</td>'
                     f'<td class="{sgn(m["pnl"])}">{mny(m["pnl"])}</td></tr>')
        rowsh += (f'<details class="gloss" open><summary>Open positions '
                  f'({len(open_marks)}) &middot; {mny(bk["unrealised"])} '
                  f'unrealised &middot; {mny(bk["open_cost"])[1:]} at risk'
                  f'</summary><div class="tablewrap"><table>'
                  '<tr><th>Ticker</th><th>Contract</th><th>Entered</th><th>Days</th>'
                  '<th>Stock</th><th>Prem paid</th><th>Model mark</th>'
                  '<th>Live chain</th><th>Ctr</th><th>Option</th>'
                  f'<th>P&amp;L</th></tr>{body}</table></div>'
                  '<p class="small">Model mark reprices the frozen contract at '
                  f'the {as_of} close and is what the tiles above count. Live '
                  'chain is the current quoted mid for the same contract, shown '
                  'with its gap to the model - a running check on the pricing, '
                  'kept out of the arithmetic so entry and exit stay on one '
                  'basis.</p></details>')

    # ---- closed book ---------------------------------------------------
    if st["closed"]:
        body = ""
        for c in sorted(st["closed"], key=lambda x: x["exit_date"],
                        reverse=True)[:25]:
            o = c.get("opt") or {}
            if o.get("pnl") is None:
                body += (f'<tr><td><b>{c["t"]}</b></td><td colspan="5" '
                         'class="small">no contract priced - entry bar history '
                         'unavailable</td>'
                         f'<td class="{sgn(c["net"])}">{pct(100*c["net"])}</td>'
                         '<td colspan="4">&mdash;</td></tr>')
                continue
            body += (f'<tr><td><b>{c["t"]}</b></td><td>{contract(o)}</td>'
                     f'<td>{c["entry_date"]}</td><td>{c["exit_date"]}</td>'
                     f'<td>{c["bars"]}</td><td>{c["reason"]}</td>'
                     f'<td class="{sgn(c["net"])}">{pct(100*c["net"])}</td>'
                     f'<td>{o["prem_paid"]:.2f}</td><td>{o["exit_recv"]:.2f}</td>'
                     f'<td>{o["contracts"]}</td>'
                     f'<td class="{sgn(o["ret"])}">{pct(100*o["ret"],1)}</td>'
                     f'<td class="{sgn(o["pnl"])}">{mny(o["pnl"])}</td></tr>')
        rowsh += (f'<details class="gloss"><summary>Closed trades ({len(nets)})'
                  f' &middot; {mny(bk["realised"])} realised'
                  + (f' &middot; {wr:.0f}% win' if nets else "") +
                  '</summary><div class="tablewrap"><table>'
                  '<tr><th>Ticker</th><th>Contract</th><th>In</th><th>Out</th>'
                  '<th>Bars</th><th>Why</th><th>Stock</th><th>Prem in</th>'
                  '<th>Prem out</th><th>Ctr</th><th>Option</th>'
                  f'<th>P&amp;L</th></tr>{body}</table></div></details>')

    # ---- queue and skips ------------------------------------------------
    if st["queued"] or st["skipped"]:
        q = (", ".join(f'{x["t"]} (RSI2 {x.get("rsi2","?")})'
                       for x in st["queued"]) or "nothing queued")
        sk = ", ".join(f'{x["t"]} {x["signal_date"]}'
                       for x in st["skipped"][-12:]) or "none"
        rowsh += ('<details class="gloss"><summary>Queue and gap-skips '
                  f'({len(st["queued"])} queued, {len(st["skipped"])} skipped)'
                  f'</summary><p class="small">Queued for the next open: {q}.</p>'
                  f'<p class="small">Gap-recovered skips (open already above the '
                  f'prior SMA5, exactly as production would skip them): {sk}.</p>'
                  '</details>')

    # ---- method ----------------------------------------------------------
    rowsh += (
        '<details class="gloss"><summary>How the option leg is priced - read '
        'this before quoting a dollar figure</summary>'
        '<p class="small"><b>These are not fills.</b> No order has ever rested '
        'in a book for any row on this page. The dollar column is what the '
        'specced contract would have returned at modelled marks, and the one '
        'variable it cannot contain is realised friction - which is the whole '
        'of D11 and the reason the Paper-Fill Log exists.</p>'
        '<p class="small"><b>Contract.</b> First standard monthly at least 30 '
        'days out; shallowest strike whose extrinsic is under 20% of premium. '
        'Delta lands 0.78-0.82 as an outcome of that rule. Frozen on the entry '
        'bar and never re-selected.</p>'
        '<p class="small"><b>Price.</b> Black-Scholes at the underlying\'s '
        'rv-blend IV proxy - the same number the scan card prints and gates at '
        '&le;60% - computed on closes strictly before the entry bar. Validated '
        'against live chains on 2026-08-26 for the six names then in the book: '
        'mean error &minus;1.4%, mean absolute error 4.5% versus the real mid, '
        'no systematic bias. The 1.25 RV&rarr;IV multiplier carried by '
        'rsi2_call_model is deliberately not applied - it over-prices this '
        'basket by 6-12%.</p>'
        '<p class="small"><b>What that validation does not cover.</b> It is a '
        'point-in-time check on pricing a fresh contract. Vol is then held FLAT '
        'at the entry reading for the life of the trade, so an open position '
        'whose IV has moved will drift from its live quote by more than 4.5% - '
        'PANW sat 13% under its chain mid on 2026-08-26 after selling off into '
        'a vol bid. Flat vol is the deliberate choice: it keeps entry and exit '
        'on one basis so a pricing error cannot masquerade as a return, and it '
        'is conservative for this strategy, whose exits complete into strength '
        'where IV normally falls. The live-chain column is where that drift is '
        'reported rather than buried.</p>'
        '<p class="small"><b>Friction.</b> 1.25% of premium in, 2.5% out - the '
        'locked backtest\'s published assumption and the same pair the '
        'Paper-Fill Log scores real fills against, derived from f=0.16 of the '
        'quoted half-spread.</p>'
        '<p class="small"><b>Sizing.</b> $100,000 sleeve, 6 slots &times; 15% = '
        '$15,000 a slot, floored at one contract so the most expensive - and '
        'most leveraged - names cannot quietly drop out of the record. Not '
        'compounded: each slot is sized off the fixed sleeve, so the dollar '
        'column reads as a per-trade impact rather than a growth curve.</p>'
        '<p class="small"><b>What the ratios need.</b> Profit factor, Sortino, '
        'CAGR and max drawdown are all shown greyed until the book reaches '
        f'{GATE_TARGET} closed trades. At n={n} they describe this sample, not '
        'the strategy; the CAGR tile in particular annualises '
        f'{bk.get("days", 0)} days and should be read as arithmetic, not as a '
        'forecast.</p></details>')

    stat = (f'{len(nets)} closed / {GATE_TARGET} gate ({gate_left} to go) &middot; '
            + (f'{wr:.0f}% win &middot; {avg:+.2f}%/trade vs the +0.9% wrapper bar &middot; '
               if nets else "") +
            f'{len(st["open"])} open &middot; {len(st["queued"])} queued &middot; '
            f'{len(st["skipped"])} gap-skipped')
    html = (f'<p class="small">Automatic paper ledger as of the {as_of} bar - '
            'entered at the next open, exited at the close over the SMA5 or at '
            '10 bars. Headline figures are the <b>option leg</b>: the DITM call '
            'the spec actually buys, on a $100,000 sleeve at 6 slots '
            '&times; 15%, at modelled marks after 1.25%/2.5% friction.</p>'
            f'{stats_html}'
            f'<p class="small"><b>Stock-leg gate</b> (the go-live instrument, '
            f'0.02%/side, unchanged): {stat}. The option wrapper clears its own '
            'cost only when the stock leg averages &ge;+0.9%/trade.</p>'
            f'{rowsh}')
    if not (st["open"] or st["queued"] or st["closed"]):
        html += '<p class="small">Ledger is armed and empty - it fills itself from the first qualifying signal.</p>'

    page = open(page_p).read()
    pat = re.escape(SM) + r".*?" + re.escape(EM)
    page2, n = re.subn(pat, lambda _m: SM + "\n" + html + "\n" + EM, page, count=1, flags=re.S)
    if n != 1: sys.exit("fail-closed: ROBSHADOW markers not found")
    if "--splice" in a:
        open(page_p, "w").write(page2)
        print(f"ROBSHADOW spliced: {len(st['open'])} open, {len(st['queued'])} queued, "
              f"{len(nets)} closed, +{len(new_q)} new as of {as_of}", file=sys.stderr)
    else:
        print(html)

if __name__ == "__main__":
    main()
