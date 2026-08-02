# x46 (SESSION) — SPEC A: Gap Widen deep out-of-sample + era decomposition
Pre-registered 2026-08-02 BEFORE computing. This executes the one spec in
docs/lab_runs_evidence_parity.md that has never had data. The gates below are
copied from SPEC A as already written there — they are not being invented now.

## Why this book, why now
Gap Widen (both variants) is VALIDATED and live in the nightly scan: 9 of the
37 open shadow-book positions are GAPW. It is also the only book whose
"Deep OOS / eras" evidence-parity cell is empty. The edge has never been tested
outside the era it was validated in, and no one has checked whether one year
carries it. That combination — most evidence-thin, actively traded — makes it
the highest-value open question on the program.

## Engine situation (stated plainly)
The GW lab engine (`gap_widen_lab/engine`) is NOT in this session's
market-data-brain clone, and `fillmode_sim.py` has no GAPW entry — it only
implements ZSCORE / ZSCORE_AV50P / BB_RUBBER. So this run uses a SESSION
harness implementing the book's published entry/exit spec verbatim:

  ignition: ema(4) crossed ema(21) on bar r; ema(10) crossed ema(21) on bar s;
    0 <= s-r <= 3; t-2 <= s <= t
  stack ema(4) > ema(10) > ema(21); widening (e4-e10) > prior (e4-e10)
  pullback context min(low,20) <= 0.93 * max(high,40)
  liquidity avol50 > 1M shares AND close >= 3
  variant filter rsi(2) < 80  |  rsi(14) < 60
  exit rsi(2) > 80  |  rsi(14) > 60, or the 10-bar time stop
  ranking rs252 DESC, fill open slots top-down
  mechanics $100k, 3 slots, close fills, 0.01%/side (the program's convention)
  earnings: live-only filter, NOT in the backtest (per the book's own spec)

## MANDATORY ANCHOR — run first, publish nothing if it fails
Before any deep result is computed, the harness must reproduce the book's
published fill-mode ladder on the SAME window it was validated on (2019-01 ->
2026-07), within tolerance:

  gap_widen_rsi2 : ideal_close 58.0% | moc_ideal 52.86% | next_open 39.64%
  gap_widen_rsi14: ideal_close 51.6% | moc_ideal 47.71% | next_open 40.79%

Tolerance: ideal_close within +-6pp AND the same ordering of the ladder legs.
The published numbers come from the lab's own engine on a "survivor universe,
grade-B" — a different codebase — so an exact match is not expected; a gross
mismatch means the harness is not measuring the same book and the deep run is
meaningless. **If the anchor fails, the deep run is abandoned and the failure
is what gets recorded** (evidence-parity cell stays empty, with the reason).

## Data
- Deep window: Robinhood split-adjusted daily 2010-01-01 -> 2018-12-31 for the
  467-name GW union universe (both books' qualified + scan tiers). Trading
  starts 2011-01 so rs252 and the 200-day stats have real warmup.
- Recent window: the existing brain + cleaned-RH store (2019 -> 2026-07).
- The two windows are run as SEPARATE self-contained sims so no price series
  crosses vendors mid-stream (the x45 lesson).
- x45 hygiene applies to every fetched series: zero-volume pre-listing padding
  removed, halt rows dropped, names with < 300 real bars in a window excluded
  from that window.

## Known biases — recorded up front, not discovered later
1. SURVIVORSHIP, and it is severe here. The GW universes were assembled from
   names tradable TODAY. Running them back to 2011 tests today's survivors on
   yesterday's tape; companies that died between 2011 and 2018 are absent.
   This biases the deep result UPWARD and cannot be fixed with the data
   available. The deep run is therefore a NECESSARY-not-sufficient test: it can
   kill the book (if survivors can't make money, nothing could) but a pass does
   not certify the book for that era.
2. Membership is also era-inappropriate: many names had not listed by 2011, so
   the effective universe grows through the window. Reported per-era name
   counts will make this visible.

## Pre-registered gates (verbatim from SPEC A)
- PASS  deep-era CAGR positive AND no single year > 60% of the full edge.
- FLAG  deep-era positive but one year contributes 50-60% of the edge ->
        size-down guidance on the dashboard.
- FAIL  deep-era negative OR one year > 60% -> the books stay tradeable, but
        the dashboard bands must widen (the bear floor from the deep run
        replaces the friction-only band) and sizing stays at forward-test
        scale.

"Percent of edge contributed per calendar year" = that year's growth
contribution as a share of the summed log-growth across all years in the run,
computed on the ideal_close leg and repeated on the hybrid leg.

## Pre-committed dashboard deliverable
`{"gapw_deep": {"window", "deep_cagr", "deep_dd", "deep_pf", "trades",
"era_pct": {year: pct}, "anchor": {...}, "verdict"}}` appended to each GW book
in the BOOKS blob; the "Deep OOS / eras" parity cell flips on receipt, with the
survivorship caveat printed next to it in the same tile. On FAIL the book's
status line gains the widened band and the size-down note — the books are NOT
killed by this spec (SPEC A says tradeable either way), which is exactly why
the gates were written before the numbers.
