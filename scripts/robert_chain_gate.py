#!/usr/bin/env python3
"""ROBERT chain gate - unattended option-book check for pending universe adds.

Runs Mondays ~09:40 ET via GitHub Actions (robert-chain-gate.yml). Reads
data/chain_gate_pending.json, pulls each name's first-monthly ~0.80-delta call
from Tradier, measures open interest and quoted spread, writes
data/chain_gate_results.json, and splices a verdict table into robert.html
between ROBGATE markers. Read-only market data; no orders are placed.
Fail-closed per name: errors are reported as errors, never guessed.
PASS = OI >= 250 and spread <= 5% of mid. MARGINAL = OI >= 100 and spread <= 8%.
"""
import json, os, sys, re, datetime as dt
from zoneinfo import ZoneInfo
import requests

TOK = os.environ.get("TRADIER_TOKEN", "").strip()
FORCE = os.environ.get("FORCE", "").lower() == "true"
BASE = "https://api.tradier.com/v1"
H = {"Authorization": "Bearer " + TOK, "Accept": "application/json"}

def third_friday(y, m):
    d = dt.date(y, m, 1)
    off = (4 - d.weekday()) % 7
    return d + dt.timedelta(days=off + 14)

def is_monthly(ds):
    d = dt.date.fromisoformat(ds)
    return d == third_friday(d.year, d.month)

def get(path, **params):
    r = requests.get(BASE + path, headers=H, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def check(sym, today):
    out = {"ticker": sym}
    try:
        q = get("/markets/quotes", symbols=sym)["quotes"]["quote"]
        if isinstance(q, list): q = q[0]
        spot = float(q.get("last") or q.get("prevclose") or 0)
        out["spot"] = round(spot, 2)
        ex = get("/markets/options/expirations", symbol=sym, includeAllRoots="true")
        exps = ((ex.get("expirations") or {}).get("date")) or []
        if isinstance(exps, str): exps = [exps]
        monthly = [e for e in exps if is_monthly(e) and (dt.date.fromisoformat(e) - today).days >= 30]
        if not monthly:
            out["status"] = "no_monthly_expiry"; return out
        exp = monthly[0]
        out["expiry"] = exp
        out["dte"] = (dt.date.fromisoformat(exp) - today).days
        ch = get("/markets/options/chains", symbol=sym, expiration=exp, greeks="true")
        opts = ((ch.get("options") or {}).get("option")) or []
        if isinstance(opts, dict): opts = [opts]
        calls = [o for o in opts if o.get("option_type") == "call"]
        pick, score = None, 9e9
        for o in calls:
            g = o.get("greeks") or {}
            dl = g.get("delta")
            if dl is None: continue
            dl = float(dl)
            if 0.70 <= dl <= 0.90 and abs(dl - 0.80) < score:
                pick, score = o, abs(dl - 0.80)
        if pick is None and spot > 0 and calls:
            for o in calls:
                k = float(o.get("strike") or 0)
                s2 = abs(k / spot - 0.90)
                if s2 < score: pick, score = o, s2
            out["note"] = "no greeks - moneyness fallback"
        if pick is None:
            out["status"] = "no_contract"; return out
        bid = float(pick.get("bid") or 0); ask = float(pick.get("ask") or 0)
        mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0
        oi = int(pick.get("open_interest") or 0)
        g = pick.get("greeks") or {}
        out["strike"] = float(pick.get("strike") or 0)
        out["delta"] = round(float(g.get("delta") or 0), 2)
        out["oi"] = oi
        out["bid"] = bid
        out["ask"] = ask
        out["volume"] = int(pick.get("volume") or 0)
        out["spread_pct"] = round(100.0 * (ask - bid) / mid, 1) if mid > 0 else None
        if mid <= 0:
            out["status"] = "no_live_quote"
        elif oi >= 250 and out["spread_pct"] <= 5:
            out["status"] = "PASS"
        elif oi >= 100 and out["spread_pct"] <= 8:
            out["status"] = "MARGINAL"
        else:
            out["status"] = "FAIL"
        return out
    except Exception as e:
        out["status"] = "error:" + type(e).__name__
        return out

def main():
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    in_window = (now.weekday() == 0 and now.hour == 9)
    if not FORCE and not in_window:
        print("outside the Monday-morning window; exiting cleanly")
        return
    if not TOK:
        print("no TRADIER_TOKEN; failing"); sys.exit(1)
    try:
        pend = json.load(open("data/chain_gate_pending.json"))
    except Exception:
        print("no pending file; exiting cleanly"); return
    ticks = pend.get("tickers") or []
    if not ticks:
        print("pending list empty; exiting cleanly"); return
    today = now.date()
    res = [check(t, today) for t in ticks]
    label = "live sweep" if in_window else "OFF-HOURS TEST - quotes may be stale or empty"
    doc = {"as_of": now.strftime("%Y-%m-%d %H:%M ET"), "mode": label, "results": res}
    os.makedirs("data", exist_ok=True)
    json.dump(doc, open("data/chain_gate_results.json", "w"), indent=1)
    rows = []
    for r in res:
        st = r.get("status", "?")
        cls = "ok" if st == "PASS" else ("warn" if st == "MARGINAL" else "bad")
        ba = "-"
        if r.get("bid") is not None and r.get("ask") is not None and (r["bid"] or r["ask"]):
            ba = "%.2f / %.2f" % (r["bid"], r["ask"])
        sp = "-" if r.get("spread_pct") is None else (str(r["spread_pct"]) + "%")
        rows.append("<tr><td>" + r["ticker"] + "</td><td>" + str(r.get("expiry", "-")) +
                    "</td><td>" + str(r.get("strike", "-")) + "</td><td>" + str(r.get("delta", "-")) +
                    "</td><td>" + str(r.get("oi", "-")) + "</td><td>" + ba + "</td><td>" + sp +
                    "</td><td>" + st + "</td></tr>")
    npass = sum(1 for r in res if r.get("status") == "PASS")
    block = ("<!-- ROBGATE:START -->\n<h3>Chain gate - pending adds</h3>\n" +
             "<p class=\"small\">" + doc["as_of"] + " (" + label + ") - first monthly &ge;30 DTE, ~0.80&Delta; call. " +
             "PASS = OI &ge; 250 and quoted spread &le; 5% of mid. " + str(npass) + "/" + str(len(res)) + " pass. " +
             "A FAIL here means the name generates signals it cannot fill at viable cost - cull before first trade.</p>\n" +
             "<table class=\"small\"><tr><th>Ticker</th><th>Expiry</th><th>Strike</th><th>Delta</th><th>OI</th><th>Bid / Ask</th><th>Spread</th><th>Verdict</th></tr>\n" +
             "\n".join(rows) + "\n</table>\n<!-- ROBGATE:END -->")
    try:
        html = open("robert.html").read()
        if "<!-- ROBGATE:START -->" in html:
            html = re.sub(r"<!-- ROBGATE:START -->.*?<!-- ROBGATE:END -->", lambda m: block, html, flags=re.S)
        elif "<!-- ROBSHADOW:END -->" in html:
            html = html.replace("<!-- ROBSHADOW:END -->", "<!-- ROBSHADOW:END -->\n" + block, 1)
        else:
            html = html.replace("</body>", block + "\n</body>", 1)
        open("robert.html", "w").write(html)
        print("page spliced")
    except Exception as e:
        print("page splice skipped:", type(e).__name__)
    print(json.dumps(doc, indent=1))

if __name__ == "__main__":
    main()
