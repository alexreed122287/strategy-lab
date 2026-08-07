#!/usr/bin/env python3
"""Build the earnings.json the daily build feeds to the TRACK snapshot and the
book scanner: {"SYM": "YYYY-MM-DD"} = next confirmed report on/after today.

Source: a market-data-brain style earnings directory - one {SYM}.json per
symbol containing a sorted list of ISO dates (the x37 fetcher's format). ETFs
have empty lists (or no file) and simply get no entry, which disables the
earnings rules for them - exactly the books' spec.

Usage:
  python3 next_earnings.py --dir ~/Projects/market-data-brain/earnings \
      --out earnings.json [--today YYYY-MM-DD] [--seed-dir data/earnings_seed] \
      [--seed-file data/earnings_seed.json]

--seed-dir (a directory of {SYM}.json) and --seed-file (one
{"dates": {SYM: [...]}} blob) are secondary, repo-committed feeds used ONLY for
symbols the main dir does not cover. --seed-file exists because the GitHub
Actions build has NO brain directory at all: without a seed it reports
earnings:0 and Z-Score's pre-earnings exit rule runs inert there. (--seed-dir
came first, for the same need in a different place: x45's session-fetched MIO
names had no brain earnings files yet.) The main dir always wins where it has
data - a seed is a floor, not an override.

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
    sfile = os.path.expanduser(opt("--seed-file") or "")
    if ((not edir or not os.path.isdir(edir))
            and (not sdir or not os.path.isdir(sdir))
            and (not sfile or not os.path.isfile(sfile))):
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

    def scan_file(p):
        """Single-file seed: {"SYM": ["YYYY-MM-DD", ...]} -> next date on/after
        today. Same contract as scan(), one file instead of hundreds - which is
        what a repo-committed seed wants to be."""
        got, seen = {}, 0
        if not p or not os.path.isfile(p):
            return got, seen
        try:
            blob = json.load(open(p))
        except Exception:
            return got, seen
        for sym, dates in (blob.get("dates") or blob).items():
            if not isinstance(dates, list):
                continue
            seen += 1
            nxt = min((x for x in dates if isinstance(x, str) and x >= today),
                      default=None)
            if nxt:
                got[sym] = nxt
        return got, seen

    main_res, main_files = scan(edir)
    seed_res, seed_files = scan(sdir)
    # A file seed and a dir seed can both be supplied; the dir wins between them
    # for no deeper reason than that it was here first.
    f_res, f_files = scan_file(sfile)
    for s, v in f_res.items():
        seed_res.setdefault(s, v)
    seed_files += f_files
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
