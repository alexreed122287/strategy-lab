# LAB RUN-SPECS — Evidence Parity for BB / Gap Widen / Z-Score
Drafted 2026-08-02 from the strategy-lab session. Purpose: bring every dashboard
book to the same evidential standard as RSI2/MFI, using ONLY data the local labs
already hold. Each spec defines the dashboard deliverable so results flow back
into the page mechanically. Status: DRAFT — adopt in the local repo under the
program's prereg convention before computing.

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
## Quick wiring item (not a backtest)
Z-score earnings force-exits are OFF until the daily build gets a
confirmed-earnings feed: emit {"SYM": "YYYY-MM-DD"} to $TMP/earnings.json in
daily_build.sh step 3 (source: the same earnings data the x37 fetcher used).

## Order of value
1. SPEC B Q1 (z-score MOO basis) - changes displayed numbers immediately.
2. SPEC C (BB validation) - BB currently has no honest number at all.
3. SPEC A (GW deep/eras) - hardening before real size.
4. SPEC B Q2/Q3, earnings feed, exit gates as the labs schedule them.
Forward testing continues in parallel regardless - it is the one dataset no
backtest can substitute.
