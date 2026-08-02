#!/usr/bin/env python3
"""Shadow forward book - the automated paper ledger.

The program's law: the forward record is the one dataset no backtest can
substitute, and every book owes 20 closed paper trades ("Forward n>=20" on the
Evidence Parity matrix). This script keeps that record WITHOUT relying on
manual logging: each nightly build it

  1. FILLS market-on-open entries queued at the previous build (Gap Widen and
     Z-Score paper signals fill at the NEXT session's open - their validated
     basis) using the fresh bars,
  2. EVALUATES every open position against its book's exact exit rule on the
     newest bar (rsi2>80 / rsi14>60 for GW, close>EMA5 + earnings force-exit
     for Z, close>SMA5 for RSI2, close>EMA7 for MFI, 10-bar time stop for all)
     and closes at that bar's close (the MOC print),
  3. QUEUES/OPENS today's qualifying signals: every Gap Widen and Z-Score TAKE
     from BOOKSIG (queued for tomorrow's open), and every fresh vetted 30+
     RSI2/MFI TAKE from SIGNALS (opened at the signal close - their validated
     basis). One position per (book, symbol).

Friction: GW nets 0.05%/side (the validated auction assumption), Z nets
0.02pp round trip; RSI2/MFI close prints are recorded gross and labeled.
The manual Positions book remains for REAL fills; this ledger is the
skip-free evidence machine.

State: data/shadow_book.json (committed by the daily build, so the record
survives machines). Output: `const SHADOW = ...;` spliced into the page.

Usage:
  python3 shadow_book.py --bars bars.json --page index.html
      [--earnings earnings.json] [--ledger data/shadow_book.json] [--splice]
"""
import datetime
import json
import os
import re
import sys

FRICTION_RT = {"GAPW_RSI2": 0.001, "GAPW_RSI14": 0.001, "ZSCORE": 0.0002,
               "RSI2": 0.0, "MFI": 0.0}
BASIS = {"GAPW_RSI2": "moo", "GAPW_RSI14": "moo", "ZSCORE": "moo",
         "RSI2": "close", "MFI": "close"}


def ema(closes, n):
    a = 2.0 / (n + 1)
    e = closes[0]
    for c in closes[1:]:
        e = a * c + (1 - a) * e
    return e


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def rsi(closes, n):
    if len(closes) < n + 1:
        return None
    a = 1.0 / n
    g = l = None
    for prev, cur in zip(closes, closes[1:]):
        ch = cur - prev
        gain, loss = max(ch, 0.0), max(-ch, 0.0)
        if g is None:
            g, l = gain, loss
        else:
            g = a * gain + (1 - a) * g
            l = a * loss + (1 - a) * l
    return 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)


def exit_hit(book, closes):
    """Book exit rule evaluated on the newest bar (close basis)."""
    c = closes[-1]
    if book == "GAPW_RSI2":
        r = rsi(closes, 2); return r is not None and r > 80 and "rsi2>80"
    if book == "GAPW_RSI14":
        r = rsi(closes, 14); return r is not None and r > 60 and "rsi14>60"
    if book == "ZSCORE":
        e = ema(closes, 5); return c > e and "close>ema5"
    if book == "RSI2":
        s = sma(closes, 5); return s is not None and c > s and "close>sma5"
    if book == "MFI":
        e = ema(closes, 7); return c > e and "close>ema7"
    return False


def blob(html, name):
    m = re.search(r"const %s = (.*?);\n" % name, html, re.S)
    return json.loads(m.group(1)) if m else None


def next_session_earnings(nxt, as_of):
    if not nxt:
        return False
    d0 = datetime.date.fromisoformat(as_of)
    nx = d0 + datetime.timedelta(days=1)
    while nx.weekday() >= 5:
        nx += datetime.timedelta(days=1)
    return as_of <= nxt <= nx.isoformat()


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    bars_path, page_path = opt("--bars"), opt("--page")
    if not bars_path or not page_path:
        sys.exit("--bars bars.json --page index.html required")
    ledger_path = opt("--ledger", os.path.join(
        os.path.dirname(os.path.abspath(page_path)), "data", "shadow_book.json"))
    bars = json.load(open(bars_path))
    earnings = json.load(open(opt("--earnings"))) if opt("--earnings") else {}
    page = open(page_path).read()
    booksig = blob(page, "BOOKSIG") or {"rows": []}
    signals = blob(page, "SIGNALS") or {"signals": []}
    scan = blob(page, "SCAN") or {"tickers": {}}
    led = (json.load(open(ledger_path)) if os.path.exists(ledger_path)
           else {"positions": [], "closed": [], "as_of": None})

    as_of = max((v[-1][0] for v in bars.values() if v), default=None)
    if not as_of:
        sys.exit("no bars")
    if led.get("as_of") == as_of:
        print("shadow: already processed %s - idempotent no-op" % as_of, file=sys.stderr)
    dates = {s: [r[0] for r in v] for s, v in bars.items()}
    closes = {s: [float(r[4] if len(r) >= 6 else r[1]) for r in v] for s, v in bars.items()}
    opens = {s: [float(r[1]) if len(r) >= 6 else None for r in v] for s, v in bars.items()}

    def series_upto(sym, date):
        ds = dates.get(sym) or []
        if date in ds:
            return closes[sym][:ds.index(date) + 1]
        return None

    if led.get("as_of") != as_of:
        # 1) fill queued MOO entries at the first bar AFTER the signal date
        for p in led["positions"]:
            if p["state"] != "pending_open":
                continue
            ds = dates.get(p["sym"]) or []
            nxt = next((i for i, d in enumerate(ds) if d > p["signal_date"]), None)
            if nxt is not None and opens[p["sym"]][nxt] is not None:
                p["state"] = "open"
                p["entry_date"] = ds[nxt]
                p["entry_px"] = round(opens[p["sym"]][nxt], 4)
            elif (datetime.date.fromisoformat(as_of)
                  - datetime.date.fromisoformat(p["signal_date"])).days > 7:
                p["state"] = "closed"; p["exit_reason"] = "never_filled"; p["net"] = None

        # 2) exits on the newest bar
        for p in led["positions"]:
            if p["state"] != "open":
                continue
            ds = dates.get(p["sym"]) or []
            if as_of not in ds or p["entry_date"] not in ds:
                continue
            held = ds.index(as_of) - ds.index(p["entry_date"])
            p["bars_held"] = held
            cs = series_upto(p["sym"], as_of)
            reason = None
            hit = exit_hit(p["book"], cs)
            if hit:
                reason = hit
            elif p["book"] == "ZSCORE" and next_session_earnings(earnings.get(p["sym"]), as_of):
                reason = "pre-earnings"
            elif held >= 10:
                reason = "time-stop"
            if reason:
                px = cs[-1]
                p.update(state="closed", exit_date=as_of, exit_px=round(px, 4),
                         exit_reason=reason,
                         net=round(px / p["entry_px"] - 1.0 - FRICTION_RT[p["book"]], 5))

        led["closed"] += [p for p in led["positions"] if p["state"] == "closed"]
        led["positions"] = [p for p in led["positions"] if p["state"] != "closed"]

        # 3) today's signals
        have = {(p["book"], p["sym"]) for p in led["positions"]}
        def queue(book, sym, sig_close):
            if (book, sym) in have:
                return
            have.add((book, sym))
            basis = BASIS[book]
            p = {"book": book, "sym": sym, "signal_date": as_of,
                 "basis": basis, "bars_held": 0, "signal_close": sig_close,
                 "entry_date": None, "entry_px": None,
                 "exit_date": None, "exit_px": None, "exit_reason": None, "net": None,
                 "state": "pending_open"}
            if basis == "close":
                p.update(state="open", entry_date=as_of, entry_px=sig_close)
            led["positions"].append(p)

        if (booksig.get("as_of") == as_of):
            for r in booksig.get("rows", []):
                if r.get("state") == "TAKE" and r.get("strat") in BASIS:
                    queue(r["strat"], r["sym"], r.get("close"))
        for x in signals.get("signals", []):
            if (x.get("state") == "TAKE" and x.get("new_today")
                    and x.get("as_of") == as_of and x.get("strat") in ("RSI2", "MFI")):
                st = (scan["tickers"].get(x["sym"], {}).get("strats", {})
                      .get(x["strat"]))
                if st and st.get("vetted") and (st.get("n") or 0) >= 30:
                    queue(x["strat"], x["sym"], x.get("close"))
        led["as_of"] = as_of

    # stats + blob
    books = ["RSI2", "MFI", "GAPW_RSI2", "GAPW_RSI14", "ZSCORE"]
    stats = {}
    for b in books:
        tr = [p for p in led["closed"] if p["book"] == b and p.get("net") is not None]
        stats[b] = {"n": len(tr),
                    "win": round(100.0 * sum(1 for t in tr if t["net"] > 0) / len(tr), 1) if tr else None,
                    "avg": round(100.0 * sum(t["net"] for t in tr) / len(tr), 2) if tr else None,
                    "open": sum(1 for p in led["positions"] if p["book"] == b and p["state"] == "open"),
                    "pending": sum(1 for p in led["positions"] if p["book"] == b and p["state"] == "pending_open")}
    exits_today = [{"sym": p["sym"], "book": p["book"], "why": p["exit_reason"],
                    "net": p.get("net")}
                   for p in led["closed"] if p.get("exit_date") == as_of]
    shadow = {"as_of": led.get("as_of"), "started": led.get("started") or as_of,
              "stats": stats,
              "open": [{k: p.get(k) for k in ["book", "sym", "state", "signal_date",
                        "entry_date", "entry_px", "bars_held"]} for p in led["positions"]],
              "exits_today": exits_today,
              "closed_total": len([p for p in led["closed"] if p.get("net") is not None])}
    led.setdefault("started", shadow["started"])

    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    json.dump(led, open(ledger_path, "w"), indent=1)
    line = "const SHADOW = " + json.dumps(shadow, separators=(",", ":")) + ";"
    assert "</" not in line
    if "--splice" in args:
        page2, n = re.subn(r"const SHADOW = .*?;\n", lambda _m: line + "\n", page, count=1, flags=re.S)
        if n != 1:
            sys.exit("no `const SHADOW = ...;` line in page")
        open(page_path, "w").write(page2)
        print("shadow: %s | open %d | pending %d | closed %d | exits today %d"
              % (as_of, sum(1 for p in led["positions"] if p["state"] == "open"),
                 sum(1 for p in led["positions"] if p["state"] == "pending_open"),
                 shadow["closed_total"], len(exits_today)), file=sys.stderr)
    else:
        print(line)


if __name__ == "__main__":
    main()
