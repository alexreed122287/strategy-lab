#!/usr/bin/env python3
"""Inject the generator's fresh DATA blobs into the evolved dashboard page.

The local builder (build_dashboard.py --public) produces the original v1 page
with fresh data. The evolved page in this repo carries the newer UI plus
repo-owned blobs (BOOKS, VEHICLES, TRACK) and repo-maintained display text
(CALLS, TF, METHOD). This script copies ONLY the generator-owned data blobs
from the builder's output into the evolved page, so a daily build refreshes
data without regressing the interface.

Usage:
  python3 refresh_blobs.py --source out/index.html --target repo/index.html

Fail-closed: any missing or invalid blob aborts before the target is written.
"""
import json
import re
import sys

DATA_BLOBS = ["SCAN", "SIGNALS", "BASKETS", "DAILY", "REGIME"]


def main():
    args = sys.argv[1:]
    def opt(name):
        return args[args.index(name) + 1] if name in args else sys.exit(f"{name} required")
    source, target = opt("--source"), opt("--target")
    src, tgt = open(source).read(), open(target).read()

    new = {}
    for b in DATA_BLOBS:
        m = re.search(r"const %s = (.*?);\n" % b, src, re.S)
        if not m:
            sys.exit(f"fail-closed: {b} blob missing from source {source}")
        blob = m.group(1)
        json.loads(blob)
        if "</" in blob:
            sys.exit(f"fail-closed: script-breaking sequence in {b}")
        new[b] = blob

    for b in DATA_BLOBS:
        line = "const %s = %s;\n" % (b, new[b])
        tgt, n = re.subn(r"const %s = .*?;\n" % b, lambda _m: line, tgt, count=1, flags=re.S)
        if n != 1:
            sys.exit(f"fail-closed: {b} blob missing from target {target}")

    open(target, "w").write(tgt)
    gen = json.loads(new["SIGNALS"]).get("generated", "?")
    print(f"refreshed {', '.join(DATA_BLOBS)} (signals generated {gen}) into {target}")


if __name__ == "__main__":
    main()
