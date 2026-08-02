# x47 (SESSION) — Point-in-time universe test for the RSI2 and MFI books
Pre-registered 2026-08-02 BEFORE computing. Gates and outcomes below are fixed
now so the result cannot be read selectively afterward.

## Why
Today, Gap Widen was pulled after its own lab showed the gap between a
hindsight-selected universe and a point-in-time one: 51.9% published, 20.7%
curated, **5.1% point-in-time faithful, −14.3% at honest friction**, against a
hindsight "oracle" ceiling of 309%. The failure was never the signal — it was
choosing which names to trade using knowledge of which names worked.

RSI2 and MFI select their universe the same way: **names with 30+ trades that
passed vetting**, i.e. on realized performance. They have never been tested for
this. The benchmark gate they cleared (+17.2pp and +35.4pp) takes the universe
as given and cannot detect the bias. This run asks the question that decided
Gap Widen.

## Rules being tested (collected verbatim from the Mac, 2026-08-02)
- RSI2 — entry `rsi(2) < 10 AND close > sma(200)`; exit `close > sma(5)` or a
  10-bar stop; 3 slots (`agentic-cron/rsi2_engine.py`).
- MFI — identical, with `mfi(3) < 10` replacing the RSI trigger
  (`rsi2_x9_mfi_friday.py`).
- Fills at the close, 0.05%/side — the program's own execution standard.

## Design (a causal fold, the x40/x44 pattern)
Pool: every name in the local brain with ≥300 real bars and the book's own
liquidity gate. No performance filter on the pool.

Three universes, all traded over the SAME forward window 2023-01 → 2026-07:
1. **PIT** — selected using ONLY 2019-01 → 2022-12 per-name results
   (n ≥ 15 trades in-window and positive average trade), then traded forward.
   No knowledge of 2023-26 enters the selection.
2. **CURATED** — today's vetted, n ≥ 30 names: the universe the dashboard
   actually trades, selected with full-sample knowledge.
3. **OBJECTIVE** — the whole pool, no performance selection at all.

Each is compared to equal-weight buy-and-hold of its own names over the same
window (survivorship-neutral, both legs sharing one name list).

## Pre-registered gates
- **P1 — selection is causal.** PIT CAGR ≥ OBJECTIVE CAGR. If picking names on
  past performance is a real skill, it must beat not picking at all, forward.
- **P2 — the book beats owning its names.** PIT CAGR > its own buy-and-hold.
  This is the benchmark gate applied to an honestly-selected universe.
- **P3 — the published universe is not inflated.** CURATED CAGR − PIT CAGR
  ≤ 15pp. A larger gap means the dashboard's numbers carry selection premium
  the book cannot earn forward.

## Pre-committed outcomes
- **All three pass** → the books are validated in a way Gap Widen never was.
  Their dashboard numbers stand, with the PIT figure published alongside as the
  honest forward expectation.
- **P3 fails alone** → the signal works but the published universe is
  selection-inflated. The books stay scanned; their headline numbers are
  replaced by the PIT figures and labeled as such.
- **P1 or P2 fails** → the same finding that pulled Gap Widen. The books are
  pulled from the nightly scanner and kept as paper research, and the
  generator's vetting rule itself is recorded as unsafe for universe choice.
- Either way the numbers are published in full, including a hindsight ceiling
  (top-decile-by-2023-26 names) so the selection premium is visible the way the
  Gap Widen lab's oracle list made it visible.

## Known limits, stated now
- The pool is today's brain — names that delisted before 2026 are absent, so
  every leg here is survivorship-filtered. The PIT-vs-CURATED *comparison* is
  unaffected (both share the pool), but the absolute levels are not clean.
- One fold, not a walk-forward. It answers "was the selection causal", not
  "what is the optimal reselection cadence".
- The MFI exit in the live shadow ledger is `close > ema(7)`, while the
  collected arm uses `close > sma(5)`. The collected definition is used here and
  the discrepancy is recorded for reconciliation.
