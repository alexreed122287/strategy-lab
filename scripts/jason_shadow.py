#!/usr/bin/env python3
"""JASON shadow forward book - the automated paper-fill log for the JASON arm.

Started 2026-09-12 (owner's call: "yes" to the forward paper log its own page
names as the next step). Same law as robert_shadow.py, its own state file, its
own sleeve, its own signal. Each nightly build this script

  1. FILLS entries queued at the previous build at the NEXT session's open
     (the spec: signal on the close, enter next session's open; no gap-skip
     rule - JASON has none, and inventing one here would be a second spec),
  2. EVALUATES every open position on the newest bar and closes at that bar's
     close when the close reverts to VAP(50) or the frozen contract has reached
     its expiry (the spec: no DTE cap, no time stop, hold to expiration),
  3. QUEUES tonight's signals:
       close <= VAP(50) - 1.5 x ATR(14)      the dislocation
       close > SMA(200)                       leader
       RS252 vs SPY > +40%                    relative-strength leader
       50-day average volume >= 500,000       liquid enough to size
       rv-blend IV proxy <= 60%               contract IV gate (same proxy as
                                              the ROBERT card)
       no earnings inside the next 21 days    "no earnings inside the ~3-week
                                              expected hold"
       >= 5 bars since this name's last signal, one open or queued per name.

The option leg is frozen exactly as ROBERT's: a REAL quote captured at the
09:45 entry by the jason-entry-snap workflow (first monthly >= 30 DTE,
shallowest strike with extrinsic under 20% - the spec's contract, and the same
selection rule robert_chain_snap.py already implements), Black-Scholes at the
rv-blend proxy as the fallback. Sized on JASON's OWN sleeve: $250,000, five
slots at 5% ($12,500 a slot) - never ROBERT's 6 x 15%, which the source
research shows puts the bootstrap 5th percentile at ruin for this line.

This is a paper ledger. No capital, no order, no fill. Every dollar figure is
contingent on the assumed fill fraction f, reported as a band where both ends
were measured. Twenty closed rows here is a sample milestone, not a gate to
anything.

State: data/jason_shadow.json. Snapshots: data/jason_chain_snaps.json.
Output: static HTML spliced between JASSHADOW markers in jason.html.

Usage:
  jason_shadow.py --bars bars.json --page jason.html --universe jason_universe.txt
      [--earnings earnings.json] [--ledger data/jason_shadow.json]
      [--snaps data/jason_chain_snaps.json] [--splice]
"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robert_chain_snap as CS
import robert_option_leg as OL
import robert_shadow as RS

SM, EM = "<!-- JASSHADOW:START -->", "<!-- JASSHADOW:END -->"
FR_SIDE = 0.0002          # stock-leg friction per side, the vehicle-study assumption
GATE_TARGET = 20
SLEEVE = 250_000.0
SLOTS = 5
SLOT_DOLLARS = SLEEVE * 0.05
DISLOCATION_ATR = 1.5
MIN_AVG_VOL = 500_000
EARNINGS_WINDOW_DAYS = 21
MIN_BARS_BETWEEN = 5
STARTED = "2026-09-12"


def opt(a, n, d=None):
    return a[a.index(n) + 1] if n in a else d


# ----------------------------------------------------------- pure signal math
def atr14(seq, n=14):
    """Wilder ATR over the last n bars of [date, o, h, l, c, v] rows. None if short."""
    if len(seq) < n + 1:
        return None
    trs = []
    for i in range(len(seq) - n, len(seq)):
        h, l, pc = seq[i][2], seq[i][3], seq[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def vap(seq, n=50):
    """Volume-weighted average price of the last n closes. None if short or no volume."""
    if len(seq) < n:
        return None
    rows = seq[-n:]
    vol = sum(r[5] for r in rows)
    if vol <= 0:
        return None
    return sum(r[4] * r[5] for r in rows) / vol


def avg_volume(seq, n=50):
    if len(seq) < n:
        return None
    return sum(r[5] for r in seq[-n:]) / n


def signal(seq, spy_r, earn_dates, as_of, last_signal_date=None):
    """One name's JASON entry test on its newest bar. Returns (take, why, detail).

    Pure: every input is a list or a string, so the test file can drive it
    without a feed. `why` names the first rule that failed, for the log.
    """
    if len(seq) < 253:
        return False, "short_history", {}
    if seq[-1][0] != as_of:
        return False, "stale", {"last_bar": seq[-1][0]}
    c = [r[4] for r in seq]
    close = c[-1]
    v50 = vap(seq)
    a14 = atr14(seq)
    if v50 is None or a14 is None or a14 <= 0:
        return False, "no_vap_or_atr", {}
    thr = v50 - DISLOCATION_ATR * a14
    detail = {"close": round(close, 4), "vap50": round(v50, 4), "atr14": round(a14, 4),
              "threshold": round(thr, 4)}
    if close > thr:
        return False, "not_dislocated", detail
    s200 = RS.sma(c, 200)
    if s200 is None or close <= s200:
        return False, "below_sma200", detail
    rs = close / c[-253] - 1 - spy_r
    detail["rs252"] = round(rs, 4)
    if rs <= 0.40:
        return False, "rs_weak", detail
    av = avg_volume(seq)
    if av is None or av < MIN_AVG_VOL:
        return False, "thin_volume", detail
    ivp = RS.rv_blend(c)
    if ivp is None or ivp > 0.60:
        return False, "iv_high", detail
    detail["iv_proxy"] = round(ivp, 4)
    d0 = dt.date.fromisoformat(as_of)
    for ed in earn_dates or []:
        try:
            dd = (dt.date.fromisoformat(ed) - d0).days
        except ValueError:
            continue
        if 0 <= dd <= EARNINGS_WINDOW_DAYS:
            return False, "earnings_in_hold", detail
    if last_signal_date:
        bars_since = sum(1 for r in seq if r[0] > last_signal_date)
        if bars_since < MIN_BARS_BETWEEN:
            return False, "too_soon", detail
    return True, "take", detail


def exit_test(seq, entry_idx, expiry):
    """Walk bars after entry; return (index, reason) of the exit bar or None.
    VAP reversion first (close >= VAP(50) on that bar), else the expiry date."""
    for j in range(entry_idx + 1, len(seq)):
        v = vap(seq[:j + 1])
        if v is not None and seq[j][4] >= v:
            return j, "VAP"
        if expiry and seq[j][0] >= expiry:
            return j, "EXPIRY"
    return None


def resize_leg(leg):
    """Size a frozen leg on JASON's slot, not ROBERT's, and recompute the
    dollars that depend on it. Floor, never zero, same reasoning as
    OL.contracts_for: dropping the priciest names would bias the record."""
    if not leg or not leg.get("prem_paid"):
        return
    n = max(1, int(SLOT_DOLLARS // (max(leg["prem_paid"], 0.01) * 100.0)))
    leg["contracts"] = n
    leg["cost"] = round(leg["prem_paid"] * 100.0 * n, 2)
    leg["slot"] = SLOT_DOLLARS
    if leg.get("exit_recv") is not None:
        leg["pnl"] = round((leg["exit_recv"] - leg["prem_paid"]) * 100.0 * n, 2)
    for f, b in (leg.get("band") or {}).items():
        # band pnl was built at ROBERT's contract count; rebuild from its ret
        b["pnl"] = round(b["ret"] * leg["prem_paid"] * 100.0 * n, 2)


# ------------------------------------------------------------------ the build
def main():
    a = sys.argv[1:]
    bars_p, page_p, uni_p = opt(a, "--bars"), opt(a, "--page"), opt(a, "--universe")
    earn_p = opt(a, "--earnings")
    led_p = opt(a, "--ledger", "data/jason_shadow.json")
    snaps_p = opt(a, "--snaps", "data/jason_chain_snaps.json")
    if not (bars_p and page_p and uni_p):
        sys.exit("--bars, --page, --universe required")
    bars = json.load(open(bars_p))
    uni = [t.strip() for t in open(uni_p).read().replace("\n", ",").split(",") if t.strip()]
    if len(uni) < 300:
        sys.exit(f"fail-closed: universe has {len(uni)} names")
    earn = {}
    for src in ([earn_p] if earn_p else []) + [
            os.path.join(os.path.dirname(os.path.abspath(page_p)), "data", "robert_earnings.json")]:
        if src and os.path.exists(src) and not earn:
            try:
                for k, v in json.load(open(src)).items():
                    earn[k] = [str(x)[:10] for x in (v if isinstance(v, list) else [v])]
            except Exception:
                earn = {}
    tok = RS.token()
    need = [s for s in uni + ["SPY"] if s not in bars]
    if need and tok:
        start = (dt.date.today() - dt.timedelta(days=560)).isoformat()
        got = 0
        for s in need:
            try:
                sr = RS.fetch(s, tok, start)
                if len(sr) >= 210:
                    bars[s] = sr
                    got += 1
            except Exception:
                pass
            time.sleep(0.25)
        print(f"jason_shadow: fetched {got}/{len(need)} names not in the bars file", file=sys.stderr)
    if "SPY" not in bars:
        sys.exit("fail-closed: no SPY")
    spy_c = [r[4] for r in bars["SPY"]]
    as_of = bars["SPY"][-1][0]
    if len(spy_c) < 260:
        sys.exit("fail-closed: SPY short")
    spy_r = spy_c[-1] / spy_c[-253] - 1
    covered = sum(1 for t in uni if t in earn)
    print(f"jason_shadow: earnings dates for {covered}/{len(uni)} names - the "
          f"earnings-inside-hold gate is inert for the rest", file=sys.stderr)

    # Point the shared freeze machinery at JASON's own snapshot store and sleeve.
    RS.SNAPS_PATH = snaps_p
    try:
        RS.SNAPS = CS.load(snaps_p)
    except Exception as e:
        print(f"WARNING: snapshot store unreadable ({e}) - model marks this run", file=sys.stderr)
        RS.SNAPS = {"schema": 1, "snaps": {}}
    OL.SLEEVE = SLEEVE
    OL.SLOTS = SLOTS
    OL.SLOT_FRAC = 0.05

    st = {"arm": "JASON", "started": STARTED, "sleeve": SLEEVE, "slots": SLOTS,
          "slot_dollars": SLOT_DOLLARS, "open": [], "queued": [], "closed": [],
          "skipped": [], "closed_total": 0, "last_signal": {}}
    if os.path.exists(led_p):
        try:
            st.update(json.load(open(led_p)))
        except Exception:
            sys.exit("fail-closed: ledger unreadable, refusing to overwrite")
    if st.get("last_as_of") == as_of:
        print(f"jason_shadow: bar {as_of} already processed", file=sys.stderr)
    busy = {p["t"] for p in st["open"]} | {q["t"] for q in st["queued"]}
    unchecked = []

    # 1. fills at the next open
    still_q = []
    for q in st["queued"]:
        t = q["t"]
        if t not in bars:
            print(f"WARNING: fill UNCHECKED {t} - no bars this run; stays queued", file=sys.stderr)
            q["unchecked"] = as_of
            unchecked.append("queued/" + t)
            still_q.append(q)
            continue
        seq = bars[t]
        idx = next((i for i, r in enumerate(seq) if r[0] > q["signal_date"]), None)
        if idx is None:
            still_q.append(q)
            continue
        st["open"].append({"t": t, "signal_date": q["signal_date"],
                           "entry_date": seq[idx][0], "entry_px": seq[idx][1]})
    st["queued"] = still_q

    # freeze the option leg on anything open, on JASON's slot
    for p in st["open"]:
        RS.freeze_entry(p, bars, tok)
        resize_leg(p.get("opt"))

    # 2. exits: VAP reversion, else the contract's expiry
    still_o = []
    for p in st["open"]:
        t = p["t"]
        if t not in bars:
            print(f"WARNING: exit UNCHECKED {t} - no bars this run; position held", file=sys.stderr)
            p["exit_unchecked"] = as_of
            unchecked.append("open/" + t)
            still_o.append(p)
            continue
        seq = bars[t]
        di = {r[0]: i for i, r in enumerate(seq)}
        ei = di.get(p["entry_date"])
        if ei is None:
            print(f"WARNING: exit UNCHECKED {t} - entry bar {p['entry_date']} missing; held", file=sys.stderr)
            p["exit_unchecked"] = as_of
            unchecked.append("open/" + t)
            still_o.append(p)
            continue
        p.pop("exit_unchecked", None)
        expiry = (p.get("opt") or {}).get("expiry")
        if not expiry:
            # No contract could be priced: hold the spec's 38 calendar days.
            expiry = (dt.date.fromisoformat(p["entry_date"]) + dt.timedelta(days=38)).isoformat()
        hit = exit_test(seq, ei, expiry)
        if hit is None:
            still_o.append(p)
            continue
        j, why = hit
        x = seq[j][4]
        net = (x * (1 - FR_SIDE)) / (p["entry_px"] * (1 + FR_SIDE)) - 1.0
        rec = {"t": t, "entry_date": p["entry_date"], "exit_date": seq[j][0],
               "entry_px": round(p["entry_px"], 4), "exit_px": round(x, 4),
               "bars": j - ei, "reason": why, "net": round(net, 5)}
        if p.get("opt"):
            rec["opt"] = p["opt"]
            if not RS.freeze_exit_quoted(rec["opt"], t, seq[j][0], tok, as_of):
                RS.freeze_exit(rec["opt"], p["entry_px"], p["entry_date"], x, seq[j][0])
            resize_leg(rec["opt"])
        st["closed"].append(rec)
        st["closed_total"] = len(st["closed"])
        busy.discard(t)
    st["open"] = still_o

    # 3. tonight's signals
    new_q = []
    reasons = {}
    for t in uni:
        if t in busy or t not in bars:
            continue
        take, why, det = signal(bars[t], spy_r, earn.get(t), as_of, st["last_signal"].get(t))
        reasons[why] = reasons.get(why, 0) + 1
        if not take:
            continue
        st["queued"].append({"t": t, "signal_date": as_of, **det})
        st["last_signal"][t] = as_of
        new_q.append(t)
        busy.add(t)
    print("jason_shadow: rule tally " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())),
          file=sys.stderr)

    if unchecked:
        print(f"WARNING: {len(unchecked)} position(s) unevaluated this run; holding last_as_of",
              file=sys.stderr)
        st["unchecked_as_of"] = as_of
        st["unchecked"] = sorted(unchecked)
    else:
        st.pop("unchecked_as_of", None)
        st.pop("unchecked", None)
        st["last_as_of"] = as_of
    os.makedirs(os.path.dirname(led_p) or ".", exist_ok=True)
    json.dump(st, open(led_p, "w"), indent=1)
    if RS._snaps_dirty:
        CS.save(RS.SNAPS, snaps_p)

    # ---- marks and stats
    open_marks = []
    for p in st["open"]:
        o = p.get("opt")
        if not o or p["t"] not in bars:
            continue
        spot = bars[p["t"]][-1][4]
        cm = RS.chain_mid(p["t"], o["expiry"], o["strike"], tok)
        m = OL.mark_leg(o, spot, as_of)
        held = (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(p["entry_date"])).days
        m.update({"t": p["t"], "opt": o, "spot": spot, "held": held,
                  "entry_date": p["entry_date"], "entry_px": p["entry_px"],
                  "contracts": o["contracts"], "cost": o["cost"],
                  "stock_ret": spot / p["entry_px"] - 1.0, "chain_mid": cm})
        # mark_leg sized pnl at the leg's contracts, which resize_leg set
        open_marks.append(m)
    bk = RS.book_stats(st["closed"], open_marks, as_of)
    html = render(st, bk, open_marks, as_of, new_q, covered, len(uni))
    if "--splice" in a:
        page = open(page_p).read()
        if SM not in page or EM not in page:
            sys.exit("fail-closed: JASSHADOW markers missing from the page")
        head, rest = page.split(SM, 1)
        _, tail = rest.split(EM, 1)
        open(page_p, "w").write(head + SM + "\n" + html + "\n" + EM + tail)
        print(f"JASSHADOW spliced: {len(st['open'])} open, {len(st['queued'])} queued, "
              f"{len(st['closed'])} closed, as of {as_of}", file=sys.stderr)
    else:
        print(html)


# ------------------------------------------------------------------ rendering
def mny(v, dp=0):
    return ("+$" if v >= 0 else "&minus;$") + ("{:,.%df}" % dp).format(abs(v))


def pct(v, dp=2):
    return ("{:+.%df}" % dp).format(v).replace("-", "&minus;") + "%"


def sgn(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def contract(o):
    y, m, d = o["expiry"].split("-")
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1]
    return f'{mon} {int(d)} {("%g" % o["strike"])}C <span class="tag">{o.get("basis", "MODEL")}</span>'


def tile(k, v, d="", cls=""):
    return (f'<div class="tile"><div class="k">{k}</div><div class="v {cls}">{v}</div>'
            + (f'<div class="d">{d}</div>' if d else "") + "</div>")


def render(st, bk, marks, as_of, new_q, covered, n_uni):
    n = bk["n"]
    grey = "" if bk.get("meaningful") else "muted"
    tiles = tile("Started", STARTED, "no capital, no order, no fill")
    tiles += tile("Closed trades", f"{n} / {GATE_TARGET}", "ratios grey until 20")
    tiles += tile("Paper result", mny(bk["net"]), f"on a ${SLEEVE:,.0f} sleeve at f = 0.16")
    tiles += tile("Open", str(len(st["open"])), f"{len(st['queued'])} queued for the next open")
    if n:
        tiles += tile("Win rate", f"{bk['win_pct']:.0f}%", f"n = {n}", grey)
        tiles += tile("Profit factor", f"{bk['pf']:.2f}" if bk.get("pf") else "&mdash;", f"n = {n}", grey)
        tiles += tile("Avg / trade", pct(bk["avg_ret"]), "on premium, model or chain basis per row", grey)
    out = [f'<p class="small">Automatic paper ledger as of the {as_of} bar. Signals on the close, '
           f'fills at the next open, exits at the close on VAP(50) reversion or at expiry. '
           f'Contract quoted at 09:45 ET where the snapshot workflow caught it (CHAIN), '
           f'Black-Scholes otherwise (MODEL). Sized on JASON\'s own sleeve: five slots at '
           f'${SLOT_DOLLARS:,.0f}. Earnings dates known for {covered} of {n_uni} names.</p>',
           f'<div class="tiles compact">{tiles}</div>']
    if marks:
        body = ""
        for m in sorted(marks, key=lambda x: x["entry_date"]):
            body += (f'<tr><td><b>{m["t"]}</b></td><td>{contract(m["opt"])}</td>'
                     f'<td>{m["entry_date"]}</td><td>{m["held"]}</td>'
                     f'<td class="{sgn(m["stock_ret"])}">{pct(100 * m["stock_ret"])}</td>'
                     f'<td>{m["opt"]["prem_paid"]:.2f}</td><td>{m["mark_mid"]:.2f}</td>'
                     f'<td>{m["contracts"]}</td>'
                     f'<td class="{sgn(m["ret"])}">{pct(100 * m["ret"], 1)}</td>'
                     f'<td class="{sgn(m["pnl"])}">{mny(m["pnl"])}</td></tr>')
        out.append('<details class="gloss" open><summary>Open positions</summary><div class="tablewrap"><table>'
                   '<tr><th>Ticker</th><th>Contract</th><th>Entered</th><th>Days</th><th>Stock</th>'
                   '<th>Prem paid</th><th>Mark</th><th>Ctr</th><th>Option</th><th>P&amp;L</th></tr>'
                   f'{body}</table></div></details>')
    if st["closed"]:
        body = ""
        for c in sorted(st["closed"], key=lambda x: x["exit_date"], reverse=True):
            o = c.get("opt") or {}
            body += (f'<tr><td><b>{c["t"]}</b></td><td>{contract(o) if o else "&mdash;"}</td>'
                     f'<td>{c["entry_date"]}</td><td>{c["exit_date"]}</td><td>{c["bars"]}</td>'
                     f'<td>{c["reason"]}</td><td class="{sgn(c["net"])}">{pct(100 * c["net"])}</td>'
                     + (f'<td>{o["prem_paid"]:.2f}</td><td>{o.get("exit_recv", 0):.2f}</td><td>{o["contracts"]}</td>'
                        f'<td class="{sgn(o.get("ret", 0))}">{pct(100 * o.get("ret", 0), 1)}</td>'
                        f'<td class="{sgn(o.get("pnl", 0))}">{mny(o.get("pnl", 0))}</td>' if o.get("pnl") is not None
                        else '<td colspan="5" class="small">no contract priced</td>') + "</tr>")
        out.append(f'<details class="gloss"><summary>Closed trades ({len(st["closed"])})</summary>'
                   '<div class="tablewrap"><table><tr><th>Ticker</th><th>Contract</th><th>In</th><th>Out</th>'
                   '<th>Bars</th><th>Why</th><th>Stock</th><th>Prem in</th><th>Prem out</th><th>Ctr</th>'
                   f'<th>Option</th><th>P&amp;L</th></tr>{body}</table></div></details>')
    if st["queued"]:
        q = ", ".join(f'{x["t"]} (close {x.get("close", 0):.2f} vs {x.get("threshold", 0):.2f})' for x in st["queued"])
        out.append(f'<p class="small"><b>Queued for the next open:</b> {q}. The 09:45 ET snapshot '
                   f'workflow quotes each contract; the next build fills at the open.</p>')
    else:
        out.append('<p class="small"><b>Nothing queued</b> - no name met every rule on this bar.</p>')
    out.append('<p class="small"><b>These are not fills.</b> No order has ever rested in a book for '
               'any row here. Every dollar figure is contingent on the assumed fill fraction f; '
               'rows measured at both ends carry the f = 0.16 / 0.50 / 1.00 band in the ledger file.</p>')
    return "\n".join(out)


if __name__ == "__main__":
    main()
