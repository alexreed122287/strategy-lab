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

    still_q = []
    for q in st["queued"]:
        t = q["t"]
        if t not in bars: still_q.append(q); continue
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

    still_o = []
    for p in st["open"]:
        t = p["t"]
        if t not in bars: still_o.append(p); continue
        seq = bars[t]
        di = {r[0]: i for i, r in enumerate(seq)}
        ei = di.get(p["entry_date"])
        if ei is None: still_o.append(p); continue
        closed = False
        for j in range(ei + 1, len(seq)):
            cl = [r[4] for r in seq[:j+1]]
            s5 = sma(cl, 5)
            bars_held = j - ei
            if (s5 is not None and cl[-1] > s5) or bars_held >= 10:
                x = seq[j][4]
                net = (x*(1-FR_SIDE))/(p["entry_px"]*(1+FR_SIDE)) - 1.0
                st["closed"].append({"t": t, "entry_date": p["entry_date"],
                    "exit_date": seq[j][0], "entry_px": round(p["entry_px"],4),
                    "exit_px": round(x,4), "bars": bars_held,
                    "reason": "SMA5" if (s5 is not None and cl[-1] > s5) else "TIME",
                    "net": round(net, 5)})
                st["closed_total"] = len(st["closed"])
                busy.discard(t); closed = True; break
        if not closed: still_o.append(p)
    st["open"] = still_o

    new_q = []
    for t in uni:
        if t in busy or t not in bars: continue
        seq = bars[t]; c = [r[4] for r in seq]
        if len(c) < 253: continue
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

    st["last_as_of"] = as_of
    os.makedirs(os.path.dirname(led_p) or ".", exist_ok=True)
    json.dump(st, open(led_p, "w"), indent=1)

    nets = [c["net"] for c in st["closed"]]
    wr = 100.0*sum(1 for n in nets if n > 0)/len(nets) if nets else None
    avg = 100.0*sum(nets)/len(nets) if nets else None
    gate_left = max(GATE_TARGET - len(nets), 0)
    rowsh = ""
    if st["open"]:
        rowsh += '<div class="tablewrap"><table><tr><th>Open</th><th>Entered</th><th>Entry</th></tr>'
        for p in st["open"]:
            rowsh += f'<tr><td><b>{p["t"]}</b></td><td>{p["entry_date"]}</td><td>{p["entry_px"]:.2f}</td></tr>'
        rowsh += "</table></div>"
    if st["queued"]:
        rowsh += '<p class="small">Queued for the next open: ' + ", ".join(
            f'{q["t"]} (RSI2 {q.get("rsi2","?")})' for q in st["queued"]) + "</p>"
    if st["closed"]:
        rowsh += '<div class="tablewrap"><table><tr><th>Closed</th><th>Entry</th><th>Exit</th><th>Bars</th><th>Why</th><th>Net</th></tr>'
        for c in st["closed"][-10:]:
            rowsh += (f'<tr><td><b>{c["t"]}</b></td><td>{c["entry_date"]}</td><td>{c["exit_date"]}</td>'
                      f'<td>{c["bars"]}</td><td>{c["reason"]}</td><td>{100*c["net"]:+.2f}%</td></tr>')
        rowsh += "</table></div>"
    stat = (f'{len(nets)} closed / {GATE_TARGET} gate ({gate_left} to go) &middot; '
            + (f'{wr:.0f}% win &middot; {avg:+.2f}%/trade vs the +0.9% wrapper bar &middot; '
               if nets else "") +
            f'{len(st["open"])} open &middot; {len(st["queued"])} queued &middot; '
            f'{len(st["skipped"])} gap-skipped')
    html = (f'<p class="small">Stock-leg ledger as of the {as_of} bar - auto-entered at the next open, '
            f'auto-exited at the close over the SMA5 or 10 bars, 0.02%/side. {stat}.</p>{rowsh}')
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
