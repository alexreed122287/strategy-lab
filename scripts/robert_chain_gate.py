#!/usr/bin/env python3
"""ROBERT chain gate - unattended option-book check for pending universe adds.

Runs Mondays ~09:40 ET via GitHub Actions (robert-chain-gate.yml). Reads
data/chain_gate_pending.json, pulls each name's first-monthly ~0.80-delta call
from Tradier, measures open interest and quoted spread, writes
data/chain_gate_results.json, and splices a verdict table into robert.html
between ROBGATE markers. Read-only market data; no orders are placed.
Fail-closed per name: errors are reported as errors, never guessed.
PASS = OI >= 10 and spread <= 25% of mid; MARGINAL = OI >= 10 and spread <= 40%.
Thresholds set 08/16/2026 from measured OPRA data: neither OI nor quoted spread
predicted trade quality (corr +0.11 / +0.17). The OI floor exists for size
feasibility (OI 7 cannot fill 11 contracts) and to kill dead books; scale it to
about 10x the intended contract count. Contract volume is reported as the real
fillability signal - resting OI is a stock of old positions, prints are flow.
"""
import json
import sys, os, sys, re, datetime as dt
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

# THE GATE, IN ONE PLACE, RECORDED WITH ITS OWN OUTPUT.
#
# These were inline literals and the JSON stored only the resulting STATUS
# STRING, never the thresholds it was computed under. So when the gate was
# amended on 08/17/2026 (250/5% -> 10/25%, because the old floor "excluded
# roughly 90% of the basket for no measured reason"), every already-published
# verdict silently became a claim under a retired rule - and nothing could
# detect that, because the gate it used was not written down. robert.html has
# been serving "0/13 pass - cull before first trade" ever since, while 8 of
# those 13 pass the live rule on the SAME stored measurements.
#
# The sibling robert_chain_check.py was defended against exactly this with a
# `gate` field. This one was not. Now it is, and status is re-derivable from
# the raw measurements at any time - see --rerender.
OI_MIN = 10
SPREAD_MAX_PCT = 25
MARGINAL_SPREAD_MAX_PCT = 40
GATE = {"oi_min": OI_MIN, "spread_max_pct": SPREAD_MAX_PCT,
        "marginal_spread_max_pct": MARGINAL_SPREAD_MAX_PCT,
        "amended": "2026-08-17"}


def verdict(oi, spread_pct, mid_ok=True):
    """The single status rule. Takes measurements, returns a verdict - so a
    stored result can always be re-scored under the current gate instead of
    carrying a frozen string."""
    if not mid_ok:
        return "no_live_quote"
    if oi is None or spread_pct is None:
        return "no_live_quote"
    if oi >= OI_MIN and spread_pct <= SPREAD_MAX_PCT:
        return "PASS"
    if oi >= OI_MIN and spread_pct <= MARGINAL_SPREAD_MAX_PCT:
        return "MARGINAL"
    return "FAIL"


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
        out["status"] = verdict(oi, out["spread_pct"], mid_ok=(mid > 0))
        return out
    except Exception as e:
        out["status"] = "error:" + type(e).__name__
        return out

def main():
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    # A window, not an exact hour. The dual cron fires 13:40 and 14:40 UTC so
    # that one lands at 09:40 ET in either DST regime - but GitHub's scheduler
    # drifts by tens of minutes, and on 2026-08-17 BOTH firings arrived at 10:03
    # and 10:56 ET. An `hour == 9` guard rejected both, so the sweep silently
    # did not run and the workflow still reported success. Widened to
    # 09:30-11:00 ET to absorb that drift; the duplicate this admits under EDT
    # is killed by the already-swept check below, not by the clock.
    in_window = (now.weekday() == 0
                 and dt.time(9, 30) <= now.time() <= dt.time(11, 0))
    if not FORCE and not in_window:
        print("outside the Monday-morning window; exiting cleanly")
        return
    # Idempotency. Under EDT both firings (09:40 and 10:40 ET) now fall inside
    # the window. Whichever arrives first sweeps; the second finds today's live
    # result on disk and exits. Keyed on the result file rather than the clock,
    # so that if the first firing died before writing, the second correctly
    # takes over instead of skipping the week.
    if not FORCE:
        try:
            prev = json.load(open("data/chain_gate_results.json"))
            if (prev.get("mode") == "live sweep" and str(prev.get("as_of", ""))
                    .startswith(now.strftime("%Y-%m-%d"))):
                print("today's live sweep already recorded (%s); exiting cleanly"
                      % prev.get("as_of"))
                return
        except Exception:
            pass
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
    doc = {"as_of": now.strftime("%Y-%m-%d %H:%M ET"), "mode": label,
           "gate": dict(GATE), "results": res}
    os.makedirs("data", exist_ok=True)
    json.dump(doc, open("data/chain_gate_results.json", "w"), indent=1)
    render_and_splice(doc)
    print(json.dumps(doc, indent=1))


def render_and_splice(doc):
    """Build the ROBGATE block from RAW MEASUREMENTS under the CURRENT gate.

    Re-scoring here (rather than printing the stored status string) is what
    stops a published verdict outliving the rule it was computed under. The
    stored `status` is left untouched in the JSON as the historical record;
    what the page shows is always today's rule applied to the same numbers.
    """
    res = doc.get("results") or []
    label = doc.get("mode", "")
    stored_gate = doc.get("gate")
    restated = 0
    for r in res:
        live = verdict(r.get("oi"), r.get("spread_pct"),
                       mid_ok=(r.get("spread_pct") is not None))
        if live != r.get("status"):
            restated += 1
        r["_live_status"] = live
    rows = []
    for r in res:
        st = r.get("_live_status", r.get("status", "?"))
        cls = "ok" if st == "PASS" else ("warn" if st == "MARGINAL" else "bad")
        ba = "-"
        if r.get("bid") is not None and r.get("ask") is not None and (r["bid"] or r["ask"]):
            ba = "%.2f / %.2f" % (r["bid"], r["ask"])
        sp = "-" if r.get("spread_pct") is None else (str(r["spread_pct"]) + "%")
        rows.append("<tr><td>" + r["ticker"] + "</td><td>" + str(r.get("expiry", "-")) +
                    "</td><td>" + str(r.get("strike", "-")) + "</td><td>" + str(r.get("delta", "-")) +
                    "</td><td>" + str(r.get("oi", "-")) + "</td><td>" + ba + "</td><td>" + sp +
                    "</td><td>" + st + "</td></tr>")
    npass = sum(1 for r in res if r.get("_live_status") == "PASS")
    block = ("<!-- ROBGATE:START -->\n<h3>Chain gate - pending adds</h3>\n" +
             "<p class=\"small\">" + doc["as_of"] + " (" + label + ") - first monthly &ge;30 DTE, ~0.80&Delta; call. " +
             "PASS = OI &ge; " + str(OI_MIN) + " and quoted spread &le; " + str(SPREAD_MAX_PCT) +
             "% of mid (gate amended " + GATE["amended"] + "); volume column is the fillability read. " +
             str(npass) + "/" + str(len(res)) + " pass. " +
             "A FAIL here means the name generates signals it cannot fill at viable cost - cull before first trade." +
             (" <b>Verdicts re-scored:</b> " + str(restated) + " of " + str(len(res)) +
              " stored verdicts were computed under an earlier gate" +
              (" (" + str(stored_gate.get("oi_min")) + "/" + str(stored_gate.get("spread_max_pct")) + "%)" if stored_gate else "") +
              " and are restated above under the current one - the measurements are unchanged."
              if restated else "") + "</p>\n" +
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


def rerender():
    """Re-splice robert.html from data/chain_gate_results.json, no network.

    The live sweep is Monday-only, so without this a gate amendment cannot
    reach the page for up to a week - which is exactly how the 08/17 amendment
    left "0/13 pass - cull before first trade" published against measurements
    that pass 8/13 under the rule the same page declares current.
    """
    doc = json.load(open("data/chain_gate_results.json"))
    render_and_splice(doc)
    live = [r.get("_live_status") for r in doc.get("results") or []]
    print("rerendered from stored measurements: %d PASS / %d MARGINAL / %d FAIL of %d"
          % (live.count("PASS"), live.count("MARGINAL"), live.count("FAIL"), len(live)))


if __name__ == "__main__":
    if "--rerender" in sys.argv:
        rerender()
    else:
        main()
