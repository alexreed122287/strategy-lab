#!/usr/bin/env python3
"""Consistency tests for the buy mailer. Run: python3 scripts/notify_test.py

Every assertion here exists because the three surfaces that print a rank - the
Signals tab, the full alert email, and the --simple subscriber digest - gave
three different answers about the same row.

2026-08-18, CELH GAPW_RSI14: 16 trades, avg 3.19%, Strength 1.963. That was the
largest Strength on the whole board, larger than the actual #1 (SHOP, 1.253).
The dashboard showed it with Rank "-". The alert email printed it clean in the
Gap Widen section with no marker and left it out of RANKED. The digest ranked it
**#1** and sent that to the subscriber list under a heading claiming the order
was "exactly as the dashboard's Signals tab". Nothing was wrong with the floor;
what was wrong was that three code paths each decided separately what a rank
means, and a reader of any one of them could not tell.

These tests assert the shape, not today's tickers, so they survive data
movement - they must fail only if the surfaces start disagreeing again.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_buys as nb  # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")

_fails = []


def t(name, cond):
    print(("PASS - " if cond else "FAIL - ") + name)
    if not cond:
        _fails.append(name)


def main():
    as_of, ranked, gw_book, paper, exits = nb.collect(PAGE)

    # --- rank_block is the single answer ------------------------------------
    t("ranked pool is exactly the rows nothing blocks",
      all(nb.rank_block(b) is None for b in ranked))
    t("ranked pool holds one arm per ticker",
      len({b["sym"] for b in ranked}) == len(ranked))
    t("ranked pool is in descending Strength order",
      all(ranked[i]["score"] >= ranked[i + 1]["score"] for i in range(len(ranked) - 1)))

    # --- the floors are two different questions -----------------------------
    # A row may be SHOWN on weaker evidence than it may be RANKED on. That gap
    # is legitimate and deliberate; what is not legitimate is passing through it
    # silently. Every row on the weak side of it must carry a reason.
    shown_not_ranked = [b for b in gw_book + paper if nb.rank_block(b)]
    t("every shown-but-unrankable row carries a reason",
      all(nb.rank_block(b) for b in shown_not_ranked))
    t("no row is both ranked and blocked",
      not [b for b in ranked if nb.rank_block(b)])

    # --- the full alert marks what it does not rank -------------------------
    subject, body = nb.compose(as_of, ranked, gw_book, paper, exits, "http://x")
    for b in gw_book:
        why = nb.rank_block(b)
        if not why:
            continue
        line = [ln for ln in body.splitlines()
                if (" " + b["sym"] + " ") in ln and b["strat"] in ln]
        t("alert marks %s %s as NOT RANKED" % (b["sym"], b["strat"]),
          bool(line) and "[NOT RANKED" in line[0])
    t("alert's RANKED heading is not contradicted by an unmarked book row",
      body.count("[NOT RANKED") == len([b for b in gw_book if nb.rank_block(b)]))

    # --- the digest numbers only what the dashboard would number ------------
    _, text, dhtml = nb.compose_simple(as_of, ranked, gw_book, paper, "http://x")
    numbered = [r for r in ranked + gw_book + paper if r.get("_rank") is not None]
    blocked = [r for r in ranked + gw_book + paper
               if r.get("_rank") is None and r.get("rankable")]
    t("digest numbers exactly the ranked rows, in the same order",
      [(r["sym"], r["strat"]) for r in sorted(numbered, key=lambda x: x["_rank"])]
      == [(r["sym"], r["strat"]) for r in ranked])
    t("digest ranks are 1..N with no gaps",
      sorted(r["_rank"] for r in numbered) == list(range(1, len(numbered) + 1)))
    t("digest leaves every blocked row unnumbered",
      all(r.get("rank_block") for r in blocked))
    t("digest states a reason for every row it declined to number",
      all(r["rank_block"] in text for r in blocked))
    t("digest no longer claims its numbering mirrors the dashboard's",
      "ranked by Strength, exactly as" not in dhtml
      and "Ranked by Strength, exactly as" not in text)

    # --- the trap itself ----------------------------------------------------
    # Strength's n/(n+10) shrink is weak: at n=16 it keeps 62% of the raw
    # average. So the top of the Strength sort is routinely a thin record. If
    # the strongest row of the day is not rankable, the digest must say so.
    everything = [r for r in ranked + gw_book + paper
                  if r.get("rankable") and r.get("score") is not None]
    if everything:
        top = max(everything, key=lambda r: r["score"])
        t("top-Strength row is ranked or explained (%s %s, %.3f on n=%s)"
          % (top["sym"], top["strat"], top["score"], top["n"]),
          top.get("_rank") is not None or top["rank_block"] in text)

    # --- z-score is never ranked, at any sample size ------------------------
    t("z-score rows are blocked regardless of n",
      nb.rank_block({"strat": "ZSCORE", "n": 500, "avg": 9.0, "score": 8.8})
      is not None)
    # and the floors themselves still bite
    t("a 29-trade row is blocked, a 30-trade row is not",
      nb.rank_block({"strat": "RSI2", "n": 29, "avg": 1.0, "score": 0.74}) is not None
      and nb.rank_block({"strat": "RSI2", "n": 30, "avg": 1.0, "score": 0.75}) is None)

    print()
    if _fails:
        print("%d FAILED: %s" % (len(_fails), "; ".join(_fails)))
        return 1
    print("all notify consistency tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
