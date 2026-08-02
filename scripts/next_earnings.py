#!/usr/bin/env python3
"""Build the earnings.json the daily build feeds to the TRACK snapshot and the
book scanner: {"SYM": "YYYY-MM-DD"} = next confirmed report on/after today.

Source: a market-data-brain style earnings directory - one {SYM}.json per
symbol containing a sorted list of ISO dates (the x37 fetcher's format). ETFs
have empty lists (or no file) and simply get no entry, which disables the
earnings rules for them - exactly the books' spec.

Usage:
  python3 next_earnings.py --dir ~/Projects/market-data-brain/earnings \
      --out earnings.json [--today YYYY-MM-DD] [--seed-dir data/earnings_seed]

--seed-dir is a secondary, repo-committed feed used ONLY for symbols the main
dir does not cover (x45: the session-fetched MIO names have no brain earnings
files yet, so the z-score no-entry rule would silently be inert for them). The
main dir always wins where it has data - the seed is a floor, not an override.

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
    sdir = os.path.expanduser(opt("--seed-dir") or "")
    out = opt("--out", "earnings.json")
    today = opt("--today") or datetime.date.today().isoformat()
    if (not edir or not os.path.isdir(edir)) and (not sdir or not os.path.isdir(sdir)):
        json.dump({}, open(out, "w"))
        print("next_earnings: no earnings dir at %r - wrote empty %s "
              "(earnings flags disabled)" % (edir, out), file=sys.stderr)
        return

    def scan(d):
        """dir -> {SYM: next date on/after today}. Missing dir = no entries."""
        got, seen = {}, 0
        if not d or not os.path.isdir(d):
            return got, seen
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            seen += 1
            try:
                dates = json.load(open(os.path.join(d, fn)))
            except Exception:
                continue
            nxt = min((x for x in dates if isinstance(x, str) and x >= today),
                      default=None)
            if nxt:
                got[fn[:-5]] = nxt
        return got, seen

    main_res, main_files = scan(edir)
    seed_res, seed_files = scan(sdir)
    # main feed wins; the seed only fills symbols the main feed has no date for
    added = [s for s in seed_res if s not in main_res]
    result = dict(main_res)
    for s in added:
        result[s] = seed_res[s]
    json.dump(result, open(out, "w"))
    print("next_earnings: %d/%d symbols have a confirmed date on/after %s "
          "(+%d from seed of %d) -> %s"
          % (len(main_res), main_files, today, len(added), seed_files, out),
          file=sys.stderr)


if __name__ == "__main__":
    main()
