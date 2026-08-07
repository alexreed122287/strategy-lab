#!/usr/bin/env python3
"""Nightly ROBERT scan: evaluate the 90-name universe on the latest bars and
splice a static signals section into robert.html between the ROBSIG markers.

Mirrors scan_book_signals.py conventions: reads the build's bars.json
(--ohlcv format: {sym: [[date,o,h,l,c,v],...]}), earnings.json, fail-closed
(any error -> exit without writing). Names in robert_universe.txt missing
from bars.json are fetched straight from Tradier (TRADIER_TOKEN env or
~/.tradier_token), fail-quiet per name.

Signal bar = the LAST bar in the feed (the 15:30 CT build evaluates the
running bar near the close, same as BOOKSIG). Gates: RSI(2)<10, close>SMA200,
RS252 vs SPY > +40%, no earnings within 7 days, rv-blend IV proxy <= 60%.
The chain gate (OI>=250, spread<=5%) cannot be computed from daily bars and
is rendered as an order-time reminder.

Usage:
  robert_scan.py --bars bars.json --page robert.html --universe robert_universe.txt
      [--earnings earnings.json] [--splice]
"""
import json, os, re, sys, time, urllib.parse, urllib.request
import datetime as dt

API = "https://api.tradier.com"
START_MARK = "<!-- ROBSIG:START -->"
END_MARK = "<!-- ROBSIG:END -->"

def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default

def token():
    t = os.environ.get("TRADIER_TOKEN")
    if t: return t.strip()
    p = os.path.expanduser("~/.tradier_token")
    if os.path.exists(p): return open(p).read().strip()
    return None

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

def wilder_rsi2(closes):
    au = ad = None
    prev = closes[0]
    for c in closes[1:]:
        d = c - prev; prev = c
        up = max(d, 0.0); dn = max(-d, 0.0)
        au = up if au is None else au + 0.5*(up-au)
        ad = dn if ad is None else ad + 0.5*(dn-ad)
    if not ad: return 100.0
    return 100.0 - 100.0/(1.0 + au/ad)

def sma(v, n):
    return sum(v[-n:])/n if len(v) >= n else None

def rv_blend(closes):
    import math
    lr = [math.log(closes[i]/closes[i-1]) for i in range(1, len(closes))]
    def sd(x):
        m = sum(x)/len(x)
        return (sum((y-m)**2 for y in x)/(len(x)-1))**0.5 if len(x) > 1 else 0.0
    if len(lr) < 60: return None
    r5, r20, r60 = (sd(lr[-n:])*(252**0.5) for n in (5, 20, 60))
    return max(0.25*r5 + 0.40*r20 + 0.35*r60, 0.05)

def main():
    args = sys.argv[1:]
    bars_p, page_p = opt(args, "--bars"), opt(args, "--page")
    uni_p, earn_p = opt(args, "--universe"), opt(args, "--earnings")
    if not (bars_p and page_p and uni_p):
        sys.exit("--bars, --page, --universe required")
    bars = json.load(open(bars_p))
    uni = [t.strip() for t in open(uni_p).read().replace("\n", ",").split(",") if t.strip()]
    if len(uni) < 60: sys.exit(f"fail-closed: universe file has only {len(uni)} names")
    earn = {}
    if earn_p and os.path.exists(earn_p):
        try:
            for k, v in json.load(open(earn_p)).items():
                earn[k] = [str(x)[:10] for x in (v if isinstance(v, list) else [v])]
        except Exception:
            earn = {}
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
                series = fetch(s, tok, start)
                if len(series) >= 210: bars[s] = series
            except Exception:
                pass
            time.sleep(0.4)
    if "SPY" not in bars: sys.exit("fail-closed: no SPY series for RS252")
    missing = [s for s in uni if s not in bars]
    spy_c = [r[4] for r in bars["SPY"]]
    spy_dates = [r[0] for r in bars["SPY"]]
    as_of = spy_dates[-1]
    if len(spy_c) < 260: sys.exit("fail-closed: SPY series too short")
    spy_r252 = spy_c[-1]/spy_c[-253] - 1

    rows = []
    for t in uni:
        if t not in bars: continue
        seq = bars[t]
        c = [r[4] for r in seq]
        if len(c) < 210: continue
        r2 = wilder_rsi2(c[-120:])
        s200 = sma(c, 200); s5 = sma(c, 5)
        if s200 is None or c[-1] <= s200 or r2 >= 10: continue
        rs = (c[-1]/c[-253] - 1 - spy_r252) if len(c) >= 253 else None
        edate, eflag = None, "ok"
        for ed in earn.get(t, []):
            try:
                dd = (dt.date.fromisoformat(ed) - dt.date.fromisoformat(as_of)).days
                if 0 <= dd <= 7: eflag, edate = "blocked", ed
            except Exception:
                pass
        ivp = rv_blend(c)
        gates = {"rs": rs is not None and rs > 0.40,
                 "earn": eflag == "ok",
                 "iv": ivp is not None and ivp <= 0.60}
        rows.append(dict(t=t, r2=r2, close=c[-1], sma5=s5, rs=rs, ivp=ivp,
                         edate=edate, take=all(gates.values()), gates=gates))
    rows.sort(key=lambda x: x["r2"])

    def chip(txt, kind):
        color = {"take": "#009E73", "block": "#D55E00", "info": "#56B4E9", "gray": "#8d8c85"}[kind]
        return (f'<span style="font-size:11px;padding:2px 8px;border-radius:10px;'
                f'border:1px solid {color};color:{color};white-space:nowrap">{txt}</span>')

    if rows:
        body = ['<div class="tablewrap"><table>',
                '<tr><th>Ticker</th><th>RSI(2)</th><th>RS252 vs SPY</th><th>IV proxy</th><th>Earnings</th><th>Verdict</th></tr>']
        for r in rows:
            rs_txt = f'{r["rs"]*100:+.0f}%' if r["rs"] is not None else "n/a"
            iv_txt = f'{r["ivp"]*100:.0f}%' if r["ivp"] is not None else "n/a"
            if r["take"]:
                verdict = chip("TAKE - verify chain at 09:45 (OI&ge;250, spread&le;5%)", "take")
            else:
                why = []
                if not r["gates"]["rs"]: why.append("RS gate")
                if not r["gates"]["earn"]: why.append(f'earnings {r["edate"]}')
                if not r["gates"]["iv"]: why.append("IV proxy &gt; 60%")
                verdict = chip("signal, gated out: " + ", ".join(why), "gray")
            body.append(f'<tr><td><b>{r["t"]}</b></td><td>{r["r2"]:.2f}</td>'
                        f'<td>{rs_txt}</td><td>{iv_txt}</td>'
                        f'<td>{r["edate"] or "clear"}</td><td>{verdict}</td></tr>')
        body.append("</table></div>")
        takes = sum(1 for r in rows if r["take"])
        head = (f'<p class="small">Scan as of the {as_of} bar - {len(rows)} raw signal(s), '
                f'{takes} pass all gates. Entry is the NEXT open, ~09:45 ET limit at mid; '
                f'skip if the open is already above the prior SMA5.</p>')
        html = head + "\n".join(body)
    else:
        html = (f'<p class="small">Scan as of the {as_of} bar - no RSI(2) signals in the '
                f'90-name universe tonight. A zero-signal night is the normal state.</p>')
    if missing:
        html += f'<p class="small">No bars for: {", ".join(missing)}.</p>'

    page = open(page_p).read()
    pat = re.escape(START_MARK) + r".*?" + re.escape(END_MARK)
    new_block = START_MARK + "\n" + html + "\n" + END_MARK
    page2, n = re.subn(pat, lambda _m: new_block, page, count=1, flags=re.S)
    if n != 1: sys.exit("fail-closed: ROBSIG markers not found in page")
    if "--splice" in args:
        open(page_p, "w").write(page2)
        print(f"ROBSIG spliced: {len(rows)} signals ({sum(1 for r in rows if r['take'])} TAKE) as of {as_of}", file=sys.stderr)
    else:
        print(html)

if __name__ == "__main__":
    main()
