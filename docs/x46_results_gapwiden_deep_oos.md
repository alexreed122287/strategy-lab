# x46 (SESSION) — SPEC A results: Gap Widen deep OOS
Prereg: docs/x46_session_prereg_gapwiden_deep_oos.md. Every number below was
re-derived first-hand AFTER a four-agent adversarial verification pass, which
refuted one of the four original findings and forced qualifications onto two
more. What that pass changed is recorded here rather than quietly dropped.

## Verdicts
- **gap_widen_rsi2 → FAIL** (SPEC A's own first clause: deep-era CAGR negative
  at the program's published execution standard).
- **gap_widen_rsi14 → UNANCHORED**: the harness cannot reproduce this book, so
  its deep numbers are recorded but are NOT binding and its parity cell stays open.

Per SPEC A, FAIL does **not** kill the book. It stays tradeable; the dashboard's
return bands now use the deep-era floor and sizing stays at forward-test scale.

## gap_widen_rsi2 — the numbers (276 names, 2011-01 → 2018-12, 1,043 trades)
| Friction (per side) | Deep CAGR |
|---|---|
| 0.01% (idealized) | **+0.21%** |
| **0.05% (the program's own execution standard)** | **−3.26%** |
| 0.20% (the standard's stated sensitivity) | **−15.22%** |

Next-open fills: −1.52%. Max drawdown −39.74%, PF 1.05, win 73.7%.

**The decisive comparison is survivorship-neutral.** Over the same window, on the
same 276 names, equal-weight buy-and-hold returned **+10.75%/yr at −24.9% max
drawdown**. The book underperformed simply owning its own universe by ~10.5pp/yr
while taking ~15pp more drawdown. That comparison needs no assumption about dead
names, because both sides are exposed to the identical survivorship filter.

**The honest recent-era comparator is 43.51%, not 57.26%.** 64 of the 340 recent
names (PLTR, RKLB, DASH, ZM, IONQ, LUNR…) had no 2011-2018 history at all.
Restricting the recent era to the 276 names common to both windows drops it from
57.26% to 43.51%, so ~14pp of the apparent era gap is universe composition, not
era.

## What the adversarial pass changed
Four independent agents attacked the findings; two attacks failed to refute, one
refuted a claim outright, one forced a rewrite.

1. **Harness bugs — SURVIVES (high confidence).** Every hypothesized defect was
   tested and none is material. rs252 warmup is structurally symmetric across
   eras (1.27% of deep signals lost to NaN vs a *higher* 1.57% in the recent
   era). No position can get stuck: all 378 deep parquets end on 2018-12-28,
   max hold is 10 bars, zero missing-bar events. The ignition predicate was
   independently reimplemented (0 mismatches over 60 names) and proven causal by
   truncation. The one lever that lifts the deep result (0.21% → 1.69%) is a spec
   deviation, and it simultaneously *degrades* the recent-era reproduction — the
   opposite signature of a bug that suppresses 2011-2018.
2. **Data quality — SURVIVES (high confidence).** The 2018 overlap between the
   deep store and the anchor store is essentially exact: median of per-symbol
   median close differences is 0.000000%, with 248 of 371 symbols matching to
   <0.01% on every shared bar.
3. **Anchor validity — REFUTED.** My claim that reproducing 57.26% against a
   published 58.0% *validated* the implementation does not hold. Randomly
   dropping 10% of the universe swings the result by ~6pp (sd); 14 of 20
   mutilated universes still clear the ±6pp gate; and deleting the "widening"
   (57.84%) or "stack" (58.13%) entry condition matches the published number
   *better* than the faithful spec does. The gate has no discriminating power.
   The number is real; the inference was not, and has been removed.
4. **Survivorship direction — PARTIAL.** My reasoning was half wrong. The
   dead-name channel is real but bounded by the 10-bar stop (worst deep trade
   −31.7%), and the look-ahead-selection channel is empirically nil (Spearman
   correlation between a name's 2019-26 return and its 2011-18 signal returns is
   +0.02). Meanwhile the IPO-exclusion channel runs ~14pp the *other* way. So
   "survivorship should inflate the deep result, making a fail decisive" is
   unsupported and has been struck.

## Two sentences that are NOT on the dashboard, deliberately
- "The book's edge does not exist before 2019." The deep CAGR's 95% confidence
  interval spans roughly −12% to +15%; the level is too imprecise for that claim.
- "Survivorship bias should inflate this, so the failure is decisive." Net sign
  is not established, and the largest measured bias runs the other way.

## Bugs this exposed in the session harness (recorded, not hidden)
- `era_pct()`'s degeneracy guard (`|total log growth| < 1e-9`) is far too tight.
  Deep total log growth is 0.0166, so it returned per-year shares of 1423% and
  −1187%, and **the coded FAIL fired on that arithmetic artifact**. The verdict
  has been re-grounded on the level; the concentration gate is INCONCLUSIVE.
- `moc_ideal` is dead code — identical to `ideal_close` — so the published
  moc rungs (52.86 / 47.71) were never actually tested.
- The ladder-order check compared the harness's 0.01%/side next-open against a
  published rung measured at 0.2%/side: different quantities.
- The harness cannot represent the books' leveraged trade vehicles (IONX, GMEU,
  NVDL, GGLL…) and sizes by cash/open-slots rather than the published
  40%-of-equity. Both are unstated deviations from the spec it was anchoring to.
- 12 symbols disagree on back-adjustment convention between the two stores
  (TFC, TT, RTX, SPGI…); splicing them on levels would inject a phantom one-day
  return up to 138%. The two windows are run separately, so no result here is
  affected — but any future study that splices them must splice on returns.

## What would settle it
The `gap_widen_lab` engine on the Mac. It can (a) say whether the RSI14 book's
published 51.6% is reproducible at all, and (b) run this deep window with the
real vehicles, real sizing and the spec's own friction. Until then x46 is an
independent second opinion, not the lab's verdict — which is exactly how the
dashboard now labels it.
