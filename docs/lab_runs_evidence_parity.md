# LAB RUN-SPECS — Evidence Parity for BB / Gap Widen / Z-Score
Drafted 2026-08-02 from the strategy-lab session. Purpose: bring every dashboard
book to the same evidential standard as RSI2/MFI, using ONLY data the local labs
already hold. Each spec defines the dashboard deliverable so results flow back
into the page mechanically.

STATUS UPDATE 2026-08-02 — the local labs had already run most of this
(results/ in market-data-brain, 07/30–08/01), and the dashboard now carries it:
- SPEC B Q1 (basis): ANSWERED by the x41 fill-mode study + x42 — idealized
  same-close 32.2% → executable hybrid (MOO entry + 3:45 MOC exit) 20.4% on the
  F22 instrument; retention 0.634 = gate FAIL, failure is the ENTRY leg. The
  dashboard shows the ladder and applies a ×0.71 per-trade executable estimate
  to every z-score signal row. Ext-31-specific MOO re-run remains open (the
  only unlanded piece of Q1).
- SPEC B Q2 (selection): ANSWERED — x40 kill + causal folds in the adversarial
  review (select-19-22/trade-23-26 = 17.2% vs SPY 20.5%; reverse 4.1%).
  Curated numbers are labeled selection-optimistic; book is paper-only.
- SPEC B Q3 (per-name): LANDED — audited 438-name wide screen spliced into the
  BOOKS blob (+12 curated-book names via the session harness, anchor 432/438).
- SPEC C (BB): EXECUTED AND KILLED 2026-08-01 — first honest baseline 8.1%
  CAGR / PF 1.20 idealized; executable hybrid ~0.8% / PF 1.07; noise-gate
  retention 0.096 = FAIL; era flag fired. Per the pre-registered gate BB is
  OUT of the nightly scanner; a 402-name per-name research table (session run,
  same anchored harness) stays on the dashboard for reference.
  RE-VET 2026-08-02 (user's MIO screenshot): the ACTUAL MIO entry is
  rsi(2)<10, not the rsi(3)<20 the port encoded. Corrected-spec re-run with
  MIO's own mechanics ($100k, 40%/trade, 3 slots, lowest-RSI3 ranking, close
  fills, 0.02% spread, 2019->present, no earnings rules) on the 451-name clean
  universe: 9.1% CAGR / PF 1.27 / 0.39%/trade / -38.5% DD, 2025 AND 2026
  negative; earnings-aware variant 8.9%/1.23; executable next-open 3.6%/1.10.
  MIO claims 73.5% / PF 3.38 / 1.96%/trade / -15% DD on 577 trades. KILL
  STANDS under the corrected spec. Unresolved in MIO's favor and re-openable
  only by a lab run: whole-exchange universe breadth (thousands of names vs
  our 451 large caps) and the unverified [000 bb rubber band] embedded screen
  (the same pitfall the z-score handoff flagged). Per-name table on the
  dashboard replaced with the corrected-spec run (402 names, 4,912 trades).
- x43 SESSION (2026-08-02): the z-score 3:45 threshold-entry reopening test
  (prereg docs/x43_session_prereg_zscore_moc_entry.md, lab fillmode_sim.py
  engine unmodified, anchors exact) PASSED all three x42 reopening gates:
  Ext-31 moc-entry 30.7% mean [28.5-33.0] vs hybrid 24.9% (+5.76pp paired,
  10/10 seeds), wide direction +2.79pp with the missing next-open true-signal
  control (17.0% vs 3.5%), delta era-clean (max year 21%). Per-trade keep-rate
  x0.87 vs idealized (vs x0.71 MOO); false fires remain profitable (+1.11%
  avg) — threshold entries are not adversely selected the way structural
  entries were. Full artifact: data/x43_results.json. PROVISIONAL pending the
  lab panel: the dashboard keeps the MOO x0.71 display basis until co-signed;
  real-money wiring stays killed (x40) regardless.
- x44 SESSION (2026-08-02): the user's MIO screenshots verified the z spec
  matches exactly and revealed [000 z score] = the 410-name universe list.
  Replication on its 143 runnable names (prereg
  docs/x44_session_prereg_zscore_mio_universe.md, lab engine): 43.5% CAGR
  idealized / PF 3.24 / 608 trades / every year positive (claim: 67.2%/4.15/
  608 on all 410); executable ladder MOC-full 38.6% [35.2-41.2], worst-case
  next-open 24.5% — vs 13.8% on the neutral wide universe. Causal fold:
  tier-curation on 2019-22 earned 19.8% in 2023-26 vs 45.6% for the full
  list — curation hurts, x40 confirmed. ALL GATES PASS -> z book UN-KILLED
  TO ACTIVE PAPER scanning the runnable MIO list. Real money stays gated on:
  fetching the 263 missing names into the brain (decisive next lab step),
  the list's assembly date (check the MIO screen's creation date), 20+
  forward paper trades, and panel co-signs of x43/x44. Artifact:
  data/x44_results.json.
- x45 SESSION (2026-08-02): universe completion per the user's instruction
  ("remove the delisted tickers altogether but incorporate the live tickers
  not already included in the brain"). The 267 missing/corrupt MIO names were
  session-fetched from Robinhood (split-adjusted daily 2018->2026-07-31,
  anchored vs Tradier parquets on overlaps: 8/10 p99<0.2%, GE/OHI-class
  spin-off/dividend divergences flagged); 218 live clean names joined the 143
  brain names (AIG/CSX repaired, JMIA/NBIS/SKIN rescued, FCEL excluded),
  48 dead names removed — survivorship bias stated up front. Replication on
  the 361-name LIVE universe (prereg
  docs/x45_session_prereg_zscore_universe_completion.md, lab engine,
  merged brain+RH store) PASSED all gates: 68.5% CAGR idealized / PF 3.12 /
  789 trades / every year positive — MATCHING MIO's claimed 67.2%; universe
  breadth, not hidden sauce, was the x44 gap. Executable ladder MOC-full
  55.5% [46.3-64.1], hybrid 46.4%, worst-case next-open 34.8%. Causal fold
  again: curation 21.4% vs full 91.2% forward. Scanner now scans the live
  list (mio_universe_live); per-name rows for the 218 RH names joined BOOKS
  as src=rh-session. Real money stays gated on: MIO screen-creation-date
  provenance, Tradier re-fetch + earnings backfill of the RH-basis names
  into the brain, 20+ forward paper trades, and panel co-signs of
  x43/x44/x45. Artifact: data/x45_results.json.
- x45 FOLLOW-THROUGH (2026-08-02, docs/x45_provenance_and_data_hygiene.md):
  the user asked for the remaining gates to be closed now. Three of the four
  were addressed in-session; two are genuinely closed.
  * PROVENANCE (x45d): MarketInOut is not reachable from the session, so the
    list was interrogated instead of its UI. It is provably CUMULATIVE - it
    contains 48 names dead since 2021-25 AND names first traded in 2024-26,
    which no single-moment export can. Rather than assert, the risk was
    tested: restricted to the 323 names already trading at the 2019 start,
    the book earns 65.5% (774 trades, PF 3.16, MOC-full 50.5%) vs 68.5% on
    all 358; the 35 late listings contribute ~3pp. The edge is NOT an
    artifact of late additions. Residual manual check (screen creation date)
    survives but can no longer overturn the result.
    Artifact: data/x45d_provenance_test.json.
  * DATA HYGIENE (x45 v2): Robinhood pads pre-listing history with
    zero-volume flat-price bars - 29,856 across 37 names (up to 2,137 on one
    name). All removed, NBIS/PS/UN dropped (splice / <300 real bars), 41
    series truncated; universe 361 -> 358. Re-run reproduced the headline
    EXACTLY (68.52% -> 68.52%) with better executable legs (MOC-full 55.5 ->
    57.3%, next-open 34.8 -> 39.0%, PF 3.12 -> 3.24): the fake bars never
    fired signals because zero-volume fails the 1M ADV gate. All gates still
    PASS. Artifact: data/x45v2_results.json (now the book's basis).
  * EARNINGS (x45c): Yahoo and Tradier are both proxy-blocked here, so the
    rule's WORTH was measured rather than the history fetched: running the
    same universes with and without earnings files moves CAGR by +0.29pp
    (143 names) and -0.49pp (358 names), blocking 3-5 of ~790 trades. The
    missing backfill does not bias the backtest; it is live single-trade
    risk control. Wired anyway: data/earnings_seed/ (213 files, 81 confirmed
    dates from a Robinhood calendar snapshot), next_earnings.py --seed-dir
    merging UNDER the brain feed, daily_build.sh passing it - coverage
    145 -> 220 of 358. Artifact: data/x45c_earnings_sensitivity.json.
  * TRADIER RE-FETCH: impossible in-session (no token by design, host
    blocked). Packaged as one Mac command - scripts/lab_refetch_new_names.py
    re-fetches the 215 RH-basis names into the brain, applies the same
    zero-volume hygiene, diffs Tradier vs Robinhood per symbol (median/p99/
    worst day, flags p99 > 0.5%), and with --earnings seeds files and runs
    the brain's own refresh_earnings.py.
  Real money REMAINS OFF. The two gates that cannot be shortcut are
  unchanged: 20+ forward paper trades, and lab panel co-sign of x43/x44/x45.
- SPEC A (Gap Widen deep-OOS/eras): EXECUTED 2026-08-02 as x46 (prereg
  docs/x46_session_prereg_gapwiden_deep_oos.md, results
  docs/x46_results_gapwiden_deep_oos.md). gap_widen_rsi2 -> FAIL on SPEC A's
  own first clause: deep-era 2011-2018 CAGR is NEGATIVE at the program's
  published 0.05%/side execution standard (-3.26%; +0.21% at 0.01%/side,
  -15.22% at the 0.2% sensitivity), on 1,043 trades over 276 names, DD -39.7%,
  PF 1.05. Survivorship-neutral kicker: equal-weight buy-and-hold of the SAME
  names over the SAME window returned +10.75%/yr at -24.9% DD, so the book lost
  to simply owning its universe by ~10.5pp/yr with more drawdown. Per SPEC A
  this does NOT kill the book - it stays tradeable, bands now use the deep-era
  floor, sizing stays at forward-test scale. gap_widen_rsi14 -> UNANCHORED: the
  session harness reproduces 38.8% vs the published 51.6% at full coverage and
  no published tier closes the gap, so its deep numbers are recorded but not
  binding and its parity cell STAYS OPEN.
  Verified adversarially before publication (4 agents): harness-bug and
  data-quality attacks failed to refute; the ANCHOR CLAIM WAS REFUTED (the
  +-6pp tolerance passes 14/20 randomly mutilated universes and passes specs
  with entry conditions deleted, so reproducing 57.26% vs 58.0% is not
  validation); the survivorship argument was struck as unsupported (the
  IPO-exclusion bias runs ~14pp the OTHER way). Two claims were removed from
  the dashboard as overstated: "the edge does not exist pre-2019" (CI spans
  ~-12% to +15%) and "survivorship makes the fail decisive". The coded FAIL
  originally fired on a DEGENERATE era-concentration metric (per-year shares of
  1423% because total log growth is ~0.017); the verdict was re-grounded on the
  level and the concentration gate is recorded INCONCLUSIVE.
  Resolving RSI14 and re-running with the real vehicles/sizing needs the
  gap_widen_lab engine - see docs/mac_handoff_checklist.md.
- Earnings wiring: DONE — daily_build.sh now feeds next-confirmed dates from
  the local market-data-brain earnings cache into TRACK and the book scanner
  (z-score no-entry + force-exit rules live).

- GAP WIDEN PULLED FROM THE SCANNER 2026-08-02 (user decision). The local
  gapwiden-lab's own results were collected off the Mac and do not support the
  book's published 51.9%/51.5% hybrid CAGR: faithful replication 23.0% at
  -64.6% DD (PF 1.10); OBJECTIVE universe 3.3%; POINT-IN-TIME 5.1% faithful and
  -14.3% at an honest 15bp spread; DEEP OOS -4.2% and -22.2%. A 24-cell
  parameter grid spans -25.2% to +47.4%, and the lab's own hindsight 'oracle'
  top-150 list returns 309% - the selection-bias ceiling. The qualified/scan
  tiers the dashboard traded were themselves chosen for having 5+ profitable
  trades. x46 reached the same conclusion independently (deep 2011-2018 ~0%
  faithful, -3.26% at the program's 0.05%/side standard).
  Effect: scan_book_signals.py no longer emits GAPW rows (SL_SCAN_GAPW=1
  re-enables for research), GAPW rows stripped from BOOKSIG, both books marked
  PAPER RESEARCH ONLY with the published headline retired as unreproduced, and
  the Today tab tiers them PULLED. Open shadow positions are left to exit on
  their own rules. Z-Score is now the only book the scanner drives.
  Artifact: data/gapwiden_lab_own_results.json.

The standard being matched (what RSI2 has): in-sample result, execution-basis
match, deep out-of-sample + era decomposition, a selection-bias control
(walk-forward / causal fold), per-name stats, a validated exit class, and a
forward record. The Evidence Parity matrix on the Strategy Books tab tracks
these seven cells per book.

--------------------------------------------------------------------------
## SPEC A — Gap Widen: deep out-of-sample + era decomposition
Question: does the GW edge (51.9%/51.5% hybrid) survive outside its validation
era, and is no single year carrying the edge?
Inputs: existing GW lab engine (gap_widen_lab/engine) + full-history Tradier
bars for the qualified universes (272 + 175 names; extend history fetch as far
back as listings allow — no new data purchases).
Method:
  1. Rerun both books, identical rules and hybrid basis, on the longest
     available window; report per-era: pre-2019 (as deep as data allows),
     2019-22, 2023-26.
  2. Era-concentration decomposition of the FULL edge per the x31/x38/x42
     standard: percent of total edge contributed per calendar year.
Pre-registered gates:
  PASS  deep-era CAGR positive AND no single year > 60% of the full edge.
  FLAG  deep-era positive but one year 50-60% of edge -> size-down guidance.
  FAIL  deep-era negative or one year > 60% -> books stay tradeable but the
        dashboard bands must widen (bear floor from the deep run replaces the
        friction-only band), and sizing stays at forward-test scale.
Dashboard deliverable: {"gapw_deep": {"window": "...", "deep_cagr": x,
"deep_dd": x, "era_pct": {"2016": ..}}} appended to the BOOKS blob per book;
matrix cells "Deep OOS / eras" flip on receipt.

--------------------------------------------------------------------------
## SPEC B — Z-Score: MOO-entry re-run + causal fold + per-name stats
Question 1 (basis): what do Ext-31 / Core-15 earn with NEXT-OPEN MOO entries
(the executable standard) instead of the sim's same-close entries?
  Method: identical mechanics, entry price = next session's open, both
  universes, seeds >= 3. Report alongside the same-close originals.
  Gate: the MOO numbers REPLACE the same-close numbers everywhere on the
  dashboard (whatever they are - no keeping the prettier figure).
Question 2 (selection): does Ext-31 survive a causal fold, per the x40 kill
precedent (curated FINAL-22 died of selection bias)?
  Method: re-derive the curated universe using ONLY pre-2023 data under the
  documented selection procedure; trade 2023+ on that fold-selected set.
  Gate: fold-selected 2023+ CAGR within noise (~2pp) of the hindsight-curated
  set -> selection control PASSES. Worse by > 2pp -> the curated numbers are
  flagged selection-optimistic on the Strategy Books tab.
Question 3 (per-name): emit per-name n / win / avg from the existing sim
trades so z-score signals can carry real Strength in the ranking.
  Dashboard deliverable: per-name entries in the BOOKS blob universe (same
  shape as GW qualified: {"signal","n","win","avg_net"}) - the ranking picks
  them up with zero page changes.
Also: the exit-class noise gate (already pending in the lab) flips the "Exit
class" cell when it passes.

--------------------------------------------------------------------------
## SPEC C — BB Rubber Band: first honest validation
Question: does BB have any validated edge at all? (Current evidence = MIO's
close-fill idealized 67% claim only.)
Method: run BB's exact entry/exit spec through the SAME machinery as the
z-score validation (same simulator, same friction, seeds >= 3), on a
pre-registered universe: start with the alive_base scan set; NO curation
before the first run (x40 lesson - curate only via a causal procedure
afterwards if at all).
Pre-registered gates (program standards):
  n >= 100 trades pooled; PF >= 1.3; win >= 60%; positive in both eras;
  no single year > 60% of edge; MOO-entry basis from the start.
  KILL if the selection-free run shows no edge (the x40 z-score wide-universe
  precedent: PF 0.93-1.05 = dead) - BB then drops from the dashboard's book
  scanner rather than lingering as paper.
Dashboard deliverable: validated_metrics for bb_rubber_band in the BOOKS blob
(same shape as the others) + per-name stats if the edge is real; the paper
label lifts only when the exit gate AND this validation both pass.

--------------------------------------------------------------------------
## SPEC A addendum — Gap Widen per-name PF (added 2026-08-02) — LANDED same day
Original problem: per_ticker_*.csv only carries n / win / avg_net aggregates,
and trades_*.csv are the PORTFOLIO sim's slot-taken trades — a different object
(JBLU: 5 portfolio trades vs 19 in the per-name arm record).
RESOLUTION: the per-name arm run's own trade log turned out to already exist as
results/events_RSI2.csv / events_RSI14.csv (ticker, entry, exit, bars, gross,
net). Anchor check before use: recomputing n / win / avg_net per name from
events_* reproduced EVERY published per_ticker row exactly (272/272 RSI2,
175/175 RSI14). Per-name PF = gross wins / -gross losses over those same rows
(99-cap when a name has zero losing trades) is spliced into the BOOKS
qualified/priority entries and renders on the Scan tab, the signal rows, and
the priority-25 tables.
Remaining lab nicety (optional): emit the `pf` column directly from the arm
loop on future re-runs so the splice needs no side computation.

--------------------------------------------------------------------------
## Quick wiring item (not a backtest)
Z-score earnings force-exits are OFF until the daily build gets a
confirmed-earnings feed: emit {"SYM": "YYYY-MM-DD"} to $TMP/earnings.json in
daily_build.sh step 3 (source: the same earnings data the x37 fetcher used).

## SPEC E — Delisting / halt rule (owed per the PIT audit, 2026-07-30)
The audit's one hard consequence for live use: sudden-halt-from-strength deaths
(SIVB-class: last print 106.04, ~zero recovery) are UNREPRESENTED in every
backtest, and the SMA200 filter is a leaky vaccine (103/937 dead names still
fired final-year signals). Before any open-scan variant gets real size:
  1. Position rule: if a held name is halted for more than 1 session, exit at
     the first available print on resumption - no discretion, no averaging.
  2. Entry rule: skip any name with a pending going-private / merger close or
     an exchange deficiency notice (the scanner's liquidity gate does not catch
     these). Cheapest implementation: a manual exclusion list the scanner reads.
  3. Sizing rule (already binding): armed open-scan variants sized to survive a
     40%+ strategy drawdown.
Dashboard: nothing to render until the rule exists; the shadow book and manual
book both inherit it once encoded in the scanner.

## Maintenance cadence
- QUARTERLY: re-run the leveraged-vehicle turnover gate (the 2026-08-01 list of
  240 twins churns as new 2x ETFs list and liquidity shifts) - refresh the
  VEHICLES blob from the dedupe script. A quarterly reminder is in
  docs/trading_schedule.ics.
- The shadow forward book (data/shadow_book.json) accumulates automatically;
  review its per-book realized-vs-validated gap monthly once n >= 20.

## Order of value
1. SPEC B Q1 (z-score MOO basis) - changes displayed numbers immediately.
2. SPEC C (BB validation) - BB currently has no honest number at all.
3. SPEC A (GW deep/eras) - hardening before real size.
4. SPEC B Q2/Q3, earnings feed, exit gates as the labs schedule them.
Forward testing continues in parallel regardless - it is the one dataset no
backtest can substitute.

## GAP WIDEN RSI14 REPRODUCTION GAP — RESOLVED 2026-08-03
x46 could not reproduce the RSI14 book's published 51.6% ideal-close CAGR on any
published universe tier (qualified 41.6%, qualified+scan 38.8%, priority-25
77.8%) at full 199/199 coverage, and recorded the book UNANCHORED.

The gapwiden-lab collection (2026-08-02) resolves it. The lab's own results do
not contain a 51.6% figure for any faithful configuration: its replication is
23.0% (DD -64.6%, PF 1.10), its objective universe 3.3%, its point-in-time arm
5.1% faithful and -14.3% at an honest 15bp spread. What the lab does contain is
a 24-cell parameter sensitivity grid spanning -25.2% to +47.4%, and an explicit
hindsight "oracle" list returning 309%.

CONCLUSION: the published 51.6%/51.9% figures are not reproducible because they
do not correspond to any faithful run in the lab - they sit at or above the best
cell of a parameter grid, on a universe selected with knowledge of which names
worked. The harness was not broken; it was being asked to reproduce a number no
honest configuration produces. This is consistent with x46 matching the RSI2
book to 0.74pp while missing RSI14 by 12.8pp - the anchor itself was later shown
(by adversarial review) to have no discriminating power.

STATUS: gap closed. Both Gap Widen books were pulled from the scanner
2026-08-02 and remain paper research. No further reconciliation is owed.
