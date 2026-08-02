#!/usr/bin/env python3
"""Build the earnings.json the daily build feeds to the TRACK snapshot and the
book scanner: {"SYM": "YYYY-MM-DD"} = next confirmed report on/after today.

Source: a market-data-brain style earnings directory - one {SYM}.json per
symbol containing a sorted list of ISO dates (the x37 fetcher's format). ETFs
have empty lists (or no file) and simply get no entry, which disables the
earnings rules for them - exactly the books' spec.

Usage:
  python3 next_earnings.py --dir ~/Projects/market-data-brain/earnings \
      --out earnings.json [--today YYYY-MM-DD]

Dates only ever come from the local feed; if the feed is stale (no future date
listed for a symbol) that symbol gets no entry and its earnings flags stay off
- fail-quiet by design, the build must not break on a stale earnings cache.
"""
import datetime
import json
import os
import sys


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    edir = os.path.expanduser(opt("--dir") or "")
    out = opt("--out", "earnings.json")
    today = opt("--today") or datetime.date.today().isoformat()
    if not edir or not os.path.isdir(edir):
        json.dump({}, open(out, "w"))
        print("next_earnings: no earnings dir at %r - wrote empty %s "
              "(earnings flags disabled)" % (edir, out), file=sys.stderr)
        return
    result, files = {}, 0
    for fn in os.listdir(edir):
        if not fn.endswith(".json"):
            continue
        files += 1
        sym = fn[:-5]
        try:
            dates = json.load(open(os.path.join(edir, fn)))
        except Exception:
            continue
        nxt = min((d for d in dates if isinstance(d, str) and d >= today),
                  default=None)
        if nxt:
            result[sym] = nxt
    json.dump(result, open(out, "w"))
    print("next_earnings: %d/%d symbols have a confirmed date on/after %s -> %s"
          % (len(result), files, today, out), file=sys.stderr)


if __name__ == "__main__":
    main()
