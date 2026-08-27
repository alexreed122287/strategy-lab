#!/usr/bin/env python3
"""Append a fill to the durable Paper-Fill Log at data/paper_fills.json.

WHY THIS FILE EXISTS. The log lived in one browser's localStorage. It was the
instrument for D11 - twenty measured fills is the thing standing between ROBERT
and real capital - and it could be destroyed by clearing site data, switching
browsers, or a private window, with no copy anywhere and no way to know it had
happened. A go-live gate that a cache eviction can reset is not a gate.

The store is now a JSON file in the repo. That buys four things localStorage
cannot: it survives the browser, it is versioned (every fill has a commit and
an author), it is diffable in review, and the Python side can read it directly
rather than waiting for someone to remember to export a CSV.

It is also PUBLIC, because the repo and the Pages site are. That is not a
change of posture - the log has always rendered on a public page - but it is
worth saying plainly before anyone puts an account number in the notes field.

Two write paths, one validator (this file):
  Mac        python3 scripts/log_fill.py --date 2026-09-01 --ticker DVN ...
  Anywhere   the log-fill workflow, run from the GitHub UI, which works on a
             phone and feeds --json straight through to this same code.

Usage:
  log_fill.py --date D --ticker T --side entry|exit --contract C
              --bid B --ask A --fill F [--qty N] [--gated Y|N] [--notes S]
              [--via cli|action] [--store PATH] [--dry-run]
  log_fill.py --json '<object or array of objects>' [--via ...] [--store ...]
  log_fill.py --verify            re-validate the whole store, change nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(os.path.dirname(HERE), "data", "paper_fills.json")

# The row shape the page reads. Kept deliberately short because it is also the
# localStorage shape - one schema, so a draft captured in the browser is the
# same object this script commits, with no translation step to get wrong.
FIELDS = ("d", "t", "s", "c", "b", "a", "f", "q", "g", "n")
TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class Bad(Exception):
    pass


def fingerprint(r):
    """Identity of a fill. Notes and qty are excluded on purpose: correcting a
    typo in the notes must not create a second row, and the same contract
    genuinely re-filled at a different size is the same measurement of
    friction."""
    def n(v):
        # Fixed 4dp on BOTH sides. The page computes this same fingerprint to
        # decide whether a browser draft has landed in the store yet, and naive
        # stringification does not agree across the two languages: a bid of
        # 30.00 is str(30.0) -> "30.0" in Python and String(30) -> "30" in JS,
        # so the draft would never be recognised as committed and would sit in
        # the "not yet saved" panel forever.
        try:
            return "%.4f" % float(v)
        except (TypeError, ValueError):
            return ""
    return "|".join([str(r.get("d", "")), str(r.get("t", "")), str(r.get("s", "")),
                     str(r.get("c", "")), n(r.get("b")), n(r.get("a")), n(r.get("f"))])


def clean(raw, today=None):
    """Validate one fill. Raises Bad with a reason - never guesses. A fill that
    cannot be validated is a fill that would corrupt the D11 sample, and the
    whole point of this store is that the sample can be trusted."""
    today = today or dt.date.today()
    r = {}
    d = str(raw.get("d") or raw.get("date") or "").strip()
    try:
        day = dt.date.fromisoformat(d)
    except ValueError:
        raise Bad(f"date {d!r} is not ISO YYYY-MM-DD")
    # One day of slack, deliberately. The validator runs on a GitHub runner in
    # UTC while the fill is dated in the trader's local zone, so a legitimate
    # afternoon fill in a zone ahead of UTC is "tomorrow" to this process.
    # Anything beyond that is a typo, not a timezone.
    if day > today + dt.timedelta(days=1):
        raise Bad(f"date {d} is in the future")
    r["d"] = d

    t = str(raw.get("t") or raw.get("ticker") or "").strip().upper()
    if not TICKER.match(t):
        raise Bad(f"ticker {t!r} does not look like a symbol")
    r["t"] = t

    s = str(raw.get("s") or raw.get("side") or "").strip().lower()
    s = "E" if s in ("e", "entry", "buy") else ("X" if s in ("x", "exit", "sell") else "")
    if not s:
        raise Bad("side must be entry/buy or exit/sell")
    r["s"] = s

    r["c"] = str(raw.get("c") or raw.get("contract") or "").strip()

    def num(key, alt):
        v = raw.get(key, raw.get(alt))
        try:
            return float(v)
        except (TypeError, ValueError):
            raise Bad(f"{alt} {v!r} is not a number")

    r["b"], r["a"], r["f"] = num("b", "bid"), num("a", "ask"), num("f", "fill")
    if r["b"] <= 0 or r["a"] <= 0 or r["f"] <= 0:
        raise Bad("bid, ask and fill must all be positive")
    if r["b"] > r["a"]:
        raise Bad(f"crossed quote: bid {r['b']} above ask {r['a']}")

    try:
        r["q"] = int(raw.get("q", raw.get("qty", 1)) or 1)
    except (TypeError, ValueError):
        raise Bad("qty is not an integer")
    if r["q"] < 1:
        raise Bad("qty must be at least 1")

    g = str(raw.get("g", raw.get("gated", "Y"))).strip().upper()
    r["g"] = "Y" if g in ("Y", "YES", "TRUE", "1") else "N"
    r["n"] = str(raw.get("n") or raw.get("notes") or "").strip()

    # A fill outside the quote you captured is legal - the book moves between
    # the snapshot and the print - but it is also what a transposed bid/ask
    # looks like, so it is surfaced rather than silently accepted.
    warn = None
    if not (min(r["b"], r["a"]) <= r["f"] <= max(r["b"], r["a"])):
        warn = (f"fill {r['f']} sits outside the captured quote "
                f"{r['b']}/{r['a']} - check the entry")
    return r, warn


def read(path=STORE):
    if not os.path.exists(path):
        return {"schema": 1, "fills": []}
    with open(path) as fh:
        d = json.load(fh)
    d.setdefault("fills", [])
    return d


def write(d, path=STORE):
    d["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    d["count"] = len(d["fills"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(d, fh, indent=1, sort_keys=False)
        fh.write("\n")


def add(rows, store=STORE, via="cli", dry=False):
    d = read(store)
    seen = {fingerprint(r) for r in d["fills"]}
    added, skipped = [], []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for raw in rows:
        r, warn = clean(raw)
        if warn:
            print("warning: " + warn, file=sys.stderr)
        fp = fingerprint(r)
        if fp in seen:
            skipped.append(r)
            print(f"duplicate, not added: {r['t']} {r['d']} {r['s']} @ {r['f']}",
                  file=sys.stderr)
            continue
        seen.add(fp)
        r["logged"] = stamp
        r["via"] = via
        d["fills"].append(r)
        added.append(r)
    # Newest first, matching how the page has always rendered.
    d["fills"].sort(key=lambda r: (r["d"], r.get("logged", "")), reverse=True)
    if not dry:
        write(d, store)
    for r in added:
        print(f"logged {r['t']} {r['d']} "
              f"{'entry' if r['s'] == 'E' else 'exit'} {r['c']} "
              f"bid {r['b']} ask {r['a']} fill {r['f']} x{r['q']}")
    print(f"store now holds {len(d['fills'])} fill(s)"
          + (" (dry run, nothing written)" if dry else f" -> {store}"))
    return len(added), len(skipped)


def verify(store=STORE):
    d = read(store)
    bad, seen = 0, set()
    for i, r in enumerate(d["fills"]):
        try:
            c, w = clean(r)
        except Bad as e:
            print(f"row {i}: INVALID - {e}", file=sys.stderr)
            bad += 1
            continue
        if w:
            print(f"row {i}: {w}", file=sys.stderr)
        fp = fingerprint(c)
        if fp in seen:
            print(f"row {i}: DUPLICATE - {fp}", file=sys.stderr)
            bad += 1
        seen.add(fp)
    ent = sum(1 for r in d["fills"] if r.get("s") == "E")
    print(f"{len(d['fills'])} fill(s): {ent} entry, {len(d['fills'])-ent} exit, "
          f"{bad} problem(s)")
    return 1 if bad else 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date"); p.add_argument("--ticker"); p.add_argument("--side")
    p.add_argument("--contract", default=""); p.add_argument("--bid")
    p.add_argument("--ask"); p.add_argument("--fill"); p.add_argument("--qty", default=1)
    p.add_argument("--gated", default="Y"); p.add_argument("--notes", default="")
    p.add_argument("--json", dest="blob",
                   help="one fill object, or an array of them")
    p.add_argument("--via", default="cli", choices=("cli", "action"))
    p.add_argument("--store", default=STORE)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify(a.store))

    if a.blob:
        try:
            payload = json.loads(a.blob)
        except json.JSONDecodeError as e:
            sys.exit(f"--json is not valid JSON: {e}")
        rows = payload if isinstance(payload, list) else [payload]
        if not rows:
            sys.exit("--json carried no fills")
    else:
        if not (a.date and a.ticker and a.side and a.bid and a.ask and a.fill):
            sys.exit("need --date --ticker --side --bid --ask --fill, or --json")
        rows = [{"date": a.date, "ticker": a.ticker, "side": a.side,
                 "contract": a.contract, "bid": a.bid, "ask": a.ask,
                 "fill": a.fill, "qty": a.qty, "gated": a.gated, "notes": a.notes}]
    try:
        add(rows, a.store, a.via, a.dry_run)
    except Bad as e:
        sys.exit(f"rejected: {e}")


if __name__ == "__main__":
    main()
