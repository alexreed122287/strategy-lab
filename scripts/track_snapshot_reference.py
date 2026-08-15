#!/usr/bin/env python3
"""Reference implementation for the dashboard's TRACK indicator snapshot.

The Positions tab flags sells by evaluating each book's exit rule against a
`const TRACK = {...};` line embedded in index.html. This script shows the exact
contract and indicator math (matching the strategy specs / BOOKS blob) so the
local daily build can emit it. Dependency-free.

Input : closes JSON  {"SYM": [["YYYY-MM-DD", close], ...], ...}  (ascending,
        >= 30 bars per symbol recommended)
        optional earnings JSON {"SYM": "YYYY-MM-DD", ...} (next confirmed report)
Output: the TRACK JSON, printed or spliced over the `const TRACK = ...;` line.

Usage:
  python3 track_snapshot_reference.py closes.json [--earnings earnings.json]
      [--splice path/to/index.html] [--source "your data source label"]

Indicator definitions (identical to the BOOKS blob):
  ema(n):  alpha = 2/(n+1), adjust=False, seeded at the first close
  rsi(n):  Wilder - gains/losses smoothed with ewm alpha = 1/n, adjust=False
  sma(n):  simple mean of the last n closes
"""
import json, re, sys


def ema(closes, n):
    a = 2.0 / (n + 1)
    e = closes[0]
    for c in closes[1:]:
        e = a * c + (1 - a) * e
    return e


def sma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


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
    if l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + g / l)


def snapshot(closes_by_sym, earnings=None, source="local build"):
    # Corpus max first: a frozen feed (EA sat at its 08-04 take-private close,
    # volume 0, for ten days) must not ship a stale close that sell-flag logic
    # and P&L cells then treat as live. Symbols trailing the market's last bar
    # by more than a week are dropped - the page renders them "not in
    # snapshot", which is the honest state. Symbols 1-7 days behind keep their
    # row but carry last_bar so consumers can see the lag.
    corpus_max = max((s[-1][0] for s in closes_by_sym.values() if s), default=None)
    as_of, tickers = None, {}
    for sym, series in closes_by_sym.items():
        if len(series) < 15:
            continue
        dates = [r[0] for r in series]
        closes = [float(r[4] if len(r) >= 6 else r[1]) for r in series]
        if corpus_max and dates[-1] < corpus_max:
            import datetime as _dt
            lag = (_dt.date.fromisoformat(corpus_max)
                   - _dt.date.fromisoformat(dates[-1])).days
            if lag > 7:
                continue
        as_of = max(as_of or dates[-1], dates[-1])
        row = {
            "close": round(closes[-1], 4),
            "rsi2": round(rsi(closes, 2), 2),
            "rsi3": round(rsi(closes, 3), 2),
            "rsi14": round(rsi(closes, 14), 2) if rsi(closes, 14) is not None else None,
            "sma5": round(sma(closes, 5), 4),
            "ema5": round(ema(closes, 5), 4),
            "ema7": round(ema(closes, 7), 4),
            "next_earnings": (earnings or {}).get(sym),
        }
        if corpus_max and dates[-1] < corpus_max:
            row["last_bar"] = dates[-1]
        tickers[sym] = row
    return {"as_of": as_of, "source": source, "tickers": tickers}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    closes = json.load(open(args[0]))
    earn = None
    source = "local build"
    splice = None
    if "--earnings" in args:
        earn = json.load(open(args[args.index("--earnings") + 1]))
    if "--source" in args:
        source = args[args.index("--source") + 1]
    if "--splice" in args:
        splice = args[args.index("--splice") + 1]
    track = snapshot(closes, earn, source)
    line = "const TRACK = " + json.dumps(track, separators=(",", ": ")) + ";"
    assert "</" not in line, "script-breaking sequence in TRACK payload"
    if splice:
        html = open(splice).read()
        html2, n = re.subn(r"const TRACK = .*?;\n", line + "\n", html, count=1, flags=re.S)
        if n != 1:
            sys.exit("no `const TRACK = ...;` line found in " + splice)
        open(splice, "w").write(html2)
        print("spliced TRACK (%d tickers, as of %s) into %s" %
              (len(track["tickers"]), track["as_of"], splice))
    else:
        print(line)


if __name__ == "__main__":
    main()
