# x44 (SESSION) — Z-Score replication on the ACTUAL MIO universe
Pre-registered 2026-08-02 BEFORE computing. Engine: lab fillmode_sim.py
unmodified (anchors already reproduced the F22 frozen baseline exactly in x43).

## What the user's screenshots established
- The MIO "0-0-0 Z-Score" screen formula MATCHES the registered spec exactly:
  exch(nyse,nasdaq), price>20, avol>1(M), price>sma(200),
  (price-sma50)/stddev(50) <= -1.5, !sector(healthcare), rsi(3)<20;
  exit price>ema(5) | 10 bars; close fills both sides; $100k, 40%/trade,
  3 positions, 0.02% spread; period 1/1/2019-12/31/2026.
- The [000 z score] bracket = the ticker-universe list (410 names, provided).
- Claim on that universe: $6,012,003 / 6,012% / 67.2% CAGR / PF 4.15 /
  80% win / 608 trades / avg 1.73% / -10% DD / every year positive.

## Data limitation (stated up front)
Only 143/410 names have clean local parquets (4 more excluded as corrupt).
Missing 263 = foreign ADRs, sector ETFs, small/mid caps, and delisted names
(ATVI, XLNX, WORK, YNDX, ...). The presence of long-delisted symbols in the
list is evidence about its assembly date - if the MIO screen predates its
backtest window, provenance is far cleaner than a hindsight-curated list;
the user should check the screen's creation date in MIO. Completing the
replication requires a lab-side Tradier fetch of the missing live names into
the brain (delisted names are unfetchable via Tradier - a permanent hole
that biases BOTH directions).

## Legs (universe = the 143 runnable names, membership recorded)
ideal_close (their mechanics, 0.01%/side) | moc_ideal | next_open_020 |
hybrid_moo005 x10 seeds | moc_full_005 x10 seeds (x43-licensed basis) |
per-name screen | causal fold: tier-select on 2019-22 per-name stats
(win>=78, avg>=1.2, n>=6), trade 2023-26, vs the full 143 on 2023-26
(the honest "better combination" test - hindsight curation is banned, x40).

## Pre-registered gates ("viable" for un-kill-to-paper)
- R1 replication strength (subset): ideal_close CAGR >= 30% AND PF >= 2.5
  AND every calendar year positive. (Neutral-wide control was 13.8%.)
- R2 executable: moc_full mean CAGR >= 0.75 x ideal_close AND >= 22%.
- R3 era: both eras positive AND ex-best-year growth > 1 on ideal and on
  moc_full seed means (no one-year edge).

## Pre-committed outcomes
- ALL PASS -> "un-kill to ACTIVE PAPER": the z book's scanner universe
  becomes the runnable MIO subset (replacing Ext-31), per-name table from
  this run joins BOOKS, the book stays PAPER with the x40 note narrowed to
  its true residual (list provenance + missing-names hole), display basis
  stays MOO x0.71 with the x43 x0.87 shown until the lab co-signs.
  REAL-MONEY wiring remains off pending: full-universe fetch, list
  provenance, forward record.
- ANY FAIL -> numbers recorded on the book; status unchanged; the missing
  262-name fetch is documented as the decisive next lab step.
