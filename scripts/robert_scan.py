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
The chain gate (OI>=10, spread<=25%, amended 08/17/2026) cannot be computed from
daily bars and is rendered as an order-time reminder.

Usage:
  robert_scan.py --bars bars.json --page robert.html --universe robert_universe.txt
      [--earnings earnings.json] [--splice]
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import datetime as dt

API = "https://api.tradier.com"
START_MARK = "<!-- ROBSIG:START -->"
END_MARK = "<!-- ROBSIG:END -->"

def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default

def token_candidates():
    """Every plausible token, in priority order. ~/.tradier_token is NOT
    trusted on sight: on the Mac it has held a dead key that 401s against
    prod while a live one sat in ~/options-platform/.env. Taking the first
    file that exists is how every un-cached name silently lands in the
    'No bars for:' list with no stated cause."""
    out = []
    for v in (os.environ.get("TRADIER_TOKEN"),
              os.environ.get("TRADIER_ACCESS_TOKEN")):
        if v and v.strip(): out.append(v.strip())
    p = os.path.expanduser("~/.tradier_token")
    if os.path.exists(p):
        v = open(p).read().strip()
        if v: out.append(v)
    p = os.path.expanduser("~/options-platform/.env")
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("TRADIER_ACCESS_TOKEN="):
                v = line.split("=", 1)[1].strip()
                if v: out.append(v)
    seen, uniq = set(), []
    for t in out:
        if t not in seen: seen.add(t); uniq.append(t)
    return uniq

def token():
    """First candidate that actually authenticates against the history
    endpoint - the one this script depends on."""
    cands = token_candidates()
    if not cands:
        print("WARNING: no Tradier token found - names absent from bars.json "
              "cannot be fetched", file=sys.stderr)
        return None
    for t in cands:
        try:
            q = urllib.parse.urlencode({"symbol": "SPY", "interval": "daily",
                "start": (dt.date.today()-dt.timedelta(days=10)).isoformat()})
            req = urllib.request.Request(API + "/v1/markets/history?" + q,
                headers={"Authorization": "Bearer " + t,
                         "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20):
                return t
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 401, 403):
                print(f"WARNING: Tradier token ...{t[-4:]} rejected "
                      f"({ex.code}) - trying next candidate", file=sys.stderr)
                continue
            raise
        except Exception as ex:
            print(f"WARNING: Tradier token ...{t[-4:]} probe failed "
                  f"({type(ex).__name__}) - trying next", file=sys.stderr)
            continue
    print(f"WARNING: all {len(cands)} Tradier token candidate(s) rejected",
          file=sys.stderr)
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
    tok = token() if need else None
    if need and not tok:
        print(f"WARNING: {len(need)} name(s) absent from bars.json and no "
              f"working token - dropped from this scan: {', '.join(need)}",
              file=sys.stderr)
    if need and tok:
        start = (dt.date.today() - dt.timedelta(days=560)).isoformat()
        failed = []
        for s in need:
            try:
                series = fetch(s, tok, start)
                if len(series) >= 210: bars[s] = series
            except Exception as ex:
                failed.append(f"{s}:{type(ex).__name__}")
            time.sleep(0.4)
        if failed:
            print(f"WARNING: Tradier fetch failed for {len(failed)}/{len(need)}"
                  f" name(s): {', '.join(failed)}", file=sys.stderr)
    if "SPY" not in bars: sys.exit("fail-closed: no SPY series for RS252")
    missing = [s for s in uni if s not in bars]
    spy_c = [r[4] for r in bars["SPY"]]
    spy_dates = [r[0] for r in bars["SPY"]]
    as_of = spy_dates[-1]
    if len(spy_c) < 260: sys.exit("fail-closed: SPY series too short")
    spy_r252 = spy_c[-1]/spy_c[-253] - 1

    # Earnings-feed forward coverage. len(earn) flatters: a name whose only
    # dates are in the past still counts, while the 7-day gate has silently
    # stopped seeing it. Count names with a date on/after the bar being
    # evaluated and say so when the feed drains - the failure mode the
    # Z-Score seed hit on 08-11-2026 (403 listed, 147 live, no warning).
    # stderr only: without --splice this script's stdout IS the page HTML.
    e_live = sum(1 for v in earn.values() if any(x >= as_of for x in v))
    if not earn:
        print("WARNING: no earnings feed at all - the no-earnings-within-7-days "
              "gate is INERT for this scan", file=sys.stderr)
    else:
        e_pct = 100.0 * e_live / len(earn)
        e_msg = (f"earnings feed: {e_live}/{len(earn)} names forward-dated "
                 f"({e_pct:.0f}%) vs bar {as_of}")
        if e_live == 0:
            print("WARNING: earnings feed fully spent - the no-earnings-within-"
                  "7-days gate is INERT for this scan. " + e_msg, file=sys.stderr)
        elif e_pct < 50:
            print("WARNING: earnings feed draining - refresh it. " + e_msg,
                  file=sys.stderr)
        else:
            print(e_msg, file=sys.stderr)

    rows = []
    stale = []
    for t in uni:
        if t not in bars: continue
        seq = bars[t]
        # Staleness guard - the rule scan_book_signals.py applies to BOOKSIG.
        # Without it a name whose feed stopped is still evaluated on its old
        # last bar, and its RS252 window is compared against SPY's CURRENT
        # 252-day return: a misaligned comparison that can manufacture a
        # phantom TAKE on a name that has not traded in months.
        if not seq or seq[-1][0] != as_of:
            stale.append(f"{t}@{seq[-1][0] if seq else 'empty'}")
            continue
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
    if stale:
        print(f"WARNING: {len(stale)} name(s) dropped as stale (last bar != "
              f"{as_of}): {', '.join(stale)}", file=sys.stderr)

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
                verdict = chip("TAKE - verify chain at 09:45 (OI&ge;10, spread&le;25%)", "take")
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
    if stale:
        html += (f'<p class="small">Dropped as stale (last bar != {as_of}): '
                 f'{", ".join(stale)}.</p>')

    page = open(page_p).read()
    pat = re.escape(START_MARK) + r".*?" + re.escape(END_MARK)
    # WALL-CLOCK FRESHNESS. robert.html is 100% static - `grep -c "<script"`
    # returns 0 - so no client-side guard is possible and the producer has to
    # supply one. Every cross-check on that page is blob-vs-blob (ROBSIG,
    # ROBSHADOW and the ledger all carry the same as_of), so on a frozen page
    # they agree and none of them fires, while the page keeps showing green
    # TAKE chips and "Entry is the NEXT open, ~09:45 ET limit at mid" on a
    # mean-reversion trigger with a 2.6-bar median hold. index.html's Today
    # card got this guard in round 1 (F3); this page emits the same imperative
    # and had nothing. The failure has precedent here: a Tradier 401 cost
    # 8/12-8/14 and issue #81 killed the 08-17 cloud run, and daily_build.sh
    # correctly holds the push - which leaves the PREVIOUS robert.html serving.
    #
    # >4 calendar days matches the Positions tab's existing threshold so
    # weekends and holidays do not false-positive: an alarm that fires
    # routinely is one nobody reads (that was F8).
    _age = (dt.date.today() - dt.date.fromisoformat(as_of)).days
    if _age > 4:
        html = ('<div class="warnbox"><h3>This scan is ' + str(_age) +
                ' days old - do not trade it</h3><p>The newest bar behind these '
                'signals is <b>' + as_of + '</b>. No build has published since, '
                'so these are <b>NOT today\'s triggers</b> and the entry rules '
                'behind them may have stopped being true days ago. RSI(2) '
                'mean-reversion decays in days - the median hold in this book is '
                '2.6 bars. Re-run the daily build before acting on anything '
                'below.</p></div>\n') + html
        print("WARNING: robert scan bar %s is %d days old - staleness banner "
              "spliced" % (as_of, _age), file=sys.stderr)
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
