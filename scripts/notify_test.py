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
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_buys as nb  # noqa: E402

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")


def run_js_rankblock(cases):
    """Execute index.html's rankBlock() over the shared case table.

    Returns a list of booleans (blocked?) aligned with `cases`, or None if no
    browser is available - None means SKIPPED, and the caller must surface that
    as a failure rather than silence. The page is loaded for real rather than
    the function being regex-extracted, so what is tested is what ships.
    """
    import subprocess
    import tempfile
    page = os.path.abspath(PAGE)
    script = """
const path=require('path');
const {execSync}=require('child_process');
let chromium;
try{ chromium=require(execSync('npm root -g',{encoding:'utf8'}).trim()+'/playwright-core').chromium; }
catch(e){ try{ chromium=require('playwright-core').chromium; }catch(e2){ process.exit(3); } }
const CASES=%s;
(async()=>{
  let b;
  try{ b=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/opt/pw-browsers/chromium'}); }
  catch(e){ process.exit(3); }
  const p=await b.newPage();
  await p.goto('file://'+%s);
  await p.waitForTimeout(500);
  const out=await p.evaluate(cs=>cs.map(c=>{
    const [n,avg,strat,vetted]=c;
    const score=(avg==null||!n)?null:+(avg*(n/(n+10))).toFixed(3);
    return rankBlock({hn:n, havg:avg, strat, vetted, score})!=="";
  }), CASES);
  console.log(JSON.stringify(out));
  await b.close();
})().catch(()=>process.exit(3));
""" % (json.dumps([[c[0], c[1], c[2], c[3]] for c in cases]), json.dumps(page))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        tmp = fh.name
    try:
        r = subprocess.run(["node", tmp], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    finally:
        os.unlink(tmp)


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

    # --- the two implementations actually get compared ----------------------
    # index.html says of its rankBlock(): "Mirrors rank_block() in
    # scripts/notify_buys.py; if you change one, change both, and notify_test.py
    # will fail if they drift." That was FALSE when it was written on
    # 2026-08-18 - this file imported notify_buys and parsed JSON blobs, and
    # never looked at the page's JS at all, while daily_build.sh gated
    # production mail on the claim. A guard that asserts it checks something it
    # does not check is worse than no guard: it converts an absent check into a
    # believed one. So do the comparison for real.
    #
    # Both functions are pure and total over (n, avg, strat, vetted, score), so
    # a shared table of cases decides it. The JS is executed in a browser when
    # one is available; when it is not, the test SAYS SO rather than passing
    # quietly - a skipped comparison must not read as a green one.
    CASES = [
        # n,   avg,   strat,        vetted, expect_blocked
        (0,    None,  "RSI2",       True,   True),   # no record
        (5,    1.0,   "GAPW_RSI2",  True,   True),   # below BOOK_MIN_N
        (10,   1.0,   "GAPW_RSI2",  True,   True),   # below RANK_MIN_N
        (29,   1.0,   "RSI2",       True,   True),   # one short
        (30,   1.0,   "RSI2",       True,   False),  # exactly the floor
        (85,   1.4,   "MFI",        True,   False),  # comfortable
        (85,  -0.5,   "MFI",        True,   True),   # negative expectancy
        (500,  9.0,   "ZSCORE",     False,  True),   # z-score: never, any n
        (85,   1.4,   "RSI2",       False,  True),   # unvetted
    ]
    py = []
    for n, avg, strat, vetted, _ in CASES:
        row = {"n": n, "avg": avg, "strat": strat, "vetted": vetted,
               "score": nb.score(avg, n) if n else None}
        py.append(nb.rank_block(row) is not None)
    t("python rank_block matches the shared expectation table",
      py == [c[4] for c in CASES])

    js = run_js_rankblock(CASES)
    if js is None:
        t("SKIPPED (no browser): JS rankBlock not compared - install "
          "playwright-core and set CHROMIUM_PATH to enable", False)
    else:
        mismatches = ["%s n=%s avg=%s vetted=%s: py=%s js=%s"
                      % (c[2], c[0], c[1], c[3], p_, j_)
                      for c, p_, j_ in zip(CASES, py, js) if p_ != j_]
        t("index.html rankBlock agrees with notify_buys.rank_block (%d cases)"
          % len(CASES), not mismatches)
        for m in mismatches:
            print("    DRIFT: " + m)

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
