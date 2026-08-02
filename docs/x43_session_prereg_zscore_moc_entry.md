# x43 (SESSION) — Z-Score 3:45 threshold-entry reopening test
Pre-registered 2026-08-02 in the strategy-lab session BEFORE computing.
Status: SESSION RUN — uses the lab's own panel-verified engine
(market-data-brain scripts/fillmode_sim.py: eta noise model, perturbed_entry,
moc_full mode, chronological fill ordering) driven unmodified; results are
evidence for the lab to adopt or refute, not a self-declared lab verdict.

## Question
x42 ended INCONCLUSIVE: MOC threshold-entry (evaluate the z-score entry on the
3:45 perturbed print, fill at the true close) cleared its +2pp bar on the F22
instrument but the delta concentrated in two years and the wide leg was
uninformative. The x42 ledger lists exact reopening conditions. This run
executes them.

## Instruments
- EXT-31: the live paper book's universe (extended_31, all clean parquets) —
  the instrument that matters for the dashboard's basis estimate.
- WIDE-451: the recorded clean wide universe (brain parquets minus the 14
  corrupt/spliced series); membership list saved in the results file.

## Legs (per universe)
ideal_close | moc_ideal | next_open_020 (deterministic), plus PAIRED seeds
1..10 of: hybrid_moo005 (TRUE signals, next-open MOO entry 0.05%/side, noisy
3:45 MOC exit) and moc_full_005 (3:45 perturbed entry AND exit, fills at the
true close 0.05%/side, confirmed/false-fire tagged).

## Anchors (must pass before any new leg is read)
- A1: F22 ideal_close reproduces the frozen baseline 32.19% CAGR / PF 5.94 /
  260 trades (same parquet vintage as the 08-01 study -> expected exact).
- A2: F22 moc_ideal reproduces 30.86% / PF 5.66.
FAIL either -> stop, report, no further reads.

## Pre-registered gates (x42's own reopening bar)
- G1 (paired seeds, EXT-31): mean CAGR(moc_full) - mean CAGR(hybrid) > +2pp
  AND >= 8/10 paired seed deltas positive.
- G2 (wide direction + the missing control): mean CAGR(wide moc_full) >
  mean CAGR(wide hybrid) AND mean CAGR(wide moc_full) >= wide next_open_020.
- G3 (delta-level era gate, EXT-31): the moc_full-minus-hybrid yearly delta is
  positive in BOTH eras (2019-22, 2023-26) and no single calendar year
  contributes > 60% of the positive total (x38/x42 concentration standard).

## Outcomes (pre-committed)
- PASS all three -> 3:45 threshold-entry is provisionally licensed FOR THE
  Z-SCORE PAPER BOOK ONLY, pending the lab's panel verification. The dashboard
  displays the x43 result alongside the existing x0.71 MOO estimate; live
  paper mechanics stay MOO until the lab co-signs. Real-money wiring remains
  killed (x40 selection) regardless - basis and selection are separate issues.
- FAIL any -> the intraday-entry ban stands, the x43 numbers are recorded on
  the z book, and the question closes unless new data arrives.
- False-fire economics (moc_full confirmed vs false-fire avg) are reported in
  all cases.
