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
- SPEC A (Gap Widen deep-OOS/eras): STILL OPEN — the one spec with no data yet.
- Earnings wiring: DONE — daily_build.sh now feeds next-confirmed dates from
  the local market-data-brain earnings cache into TRACK and the book scanner
  (z-score no-entry + force-exit rules live).

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
