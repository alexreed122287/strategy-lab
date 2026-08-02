# Panel co-sign packet — what the panel is being asked to decide
Assembled 2026-08-02. Everything here is already in the repo; this is the index
and the specific questions, so a reviewer can work through it in one sitting.

## The ask
Three session runs (x43, x44, x45) currently gate the Z-Score book's move from
paper toward real money. They were run under program law — pre-registered before
computing, verdicts binding — but no panel has co-signed them. **Co-signing means
affirming that the run's method matches its pre-registration and that its stated
conclusion follows from its numbers.** It does not mean approving real-money use;
that has separate gates listed at the end.

## What each run claims, and its artifact

| Run | Prereg | Result artifact | Claim |
|---|---|---|---|
| x43 | `docs/x43_session_prereg_zscore_moc_entry.md` | `data/x43_results.json` | 3:45 threshold entry → MOC fill keeps ×0.87 of idealized per trade (vs ×0.71 MOO); +5.76pp over hybrid; 10/10 seeds; era-clean |
| x44 | `docs/x44_session_prereg_zscore_mio_universe.md` | `data/x44_results.json` | On the real MIO universe's 143 runnable names: 43.5% CAGR idealized, PF 3.24, every year positive; curation *hurts* (19.8% vs 45.6% forward) |
| x45 | `docs/x45_session_prereg_zscore_universe_completion.md` | `data/x45v2_results.json` | Completed 358-name live universe: 68.5% idealized, PF 3.24, 788 trades, matching MIO's claimed 67.2% |

Supporting, not requiring co-sign: `docs/x45_provenance_and_data_hygiene.md`
(provenance + Robinhood padding fix), `data/x45d_provenance_test.json`,
`data/x45c_earnings_sensitivity.json`, `data/bench_own_universe.json`.

## OWNER ANSWERS (recorded 2026-08-02, alexreed122287)
1. **Displayed basis** — "whichever is more profitable reflecting" → use the basis
   that reflects the actual mechanism. x43 measured x0.87 for the 3:45 threshold
   entry the book actually uses; the x0.71 MOO figure describes a mechanism it
   does not use. ACTION: adopt x0.87 as the displayed executable basis, with x0.71
   retained on the card as the conservative floor.
2. **Curation** — "no, don't curate" → the book trades the FULL list. Confirmed
   three times independently (x40, x44, x48b): performance-selecting inside the
   list destroys the edge.
3. **Tradier re-run** — "yes, re-run" → the 68.5% headline must be recomputed on
   the refreshed brain before co-sign. OPEN, needs the Mac.
4. **Survivorship** — "that is sufficient" → x45d's point-in-time check accepted;
   no point-in-time data purchase required.

## Specific questions for the panel
1. **x43** — the displayed basis stays at MOO ×0.71 while x43 measured ×0.87.
   Is the conservative basis still correct, or should the book display ×0.87?
2. **x44/x45** — the causal fold shows curation hurting, i.e. the full list beats
   any performance-selected subset. Does the panel accept that as sufficient
   evidence the MIO list is not hindsight-curated, given the list is provably
   cumulative (48 names dead 2021-25 alongside names first traded 2024-26)?
3. **x45 data basis** — 215 of 358 names were re-fetched from Tradier on
   2026-08-02 (215/215 written, 0 unavailable). The sim behind the 68.5% headline
   still ran on the Robinhood-basis store. Does the panel require a re-run on the
   refreshed brain before co-signing? (Recommended: yes. It is one command.)
4. **Survivorship** — 48 delisted names were removed from the universe by owner
   instruction. x45d showed the edge holds on the 323 names that predate the test
   (65.5% vs 68.5%). Is that sufficient, or is point-in-time data required?

## What the panel should know went wrong, in this session
Recording these because a co-sign is worth less if the reviewer has to discover
them independently.

- **x46 (Gap Widen)** — my anchor claim was **refuted** by adversarial review:
  reproducing 57.26% against a published 58.0% proved nothing, because the ±6pp
  tolerance also passes specs with entry conditions deleted. Two overstatements
  were removed from the writeup. Details in
  `docs/x46_results_gapwiden_deep_oos.md`.
- **Gap Widen** was pulled from the scanner after the local lab's own results
  (point-in-time 5.1% faithful, −14.3% honest; deep OOS −4.2%/−22.2%) contradicted
  its published 51.9%. `data/gapwiden_lab_own_results.json`.
- **x47** found RSI2's point-in-time fold trailing buy-and-hold of its own names
  in 2023-26 under every universe. The owner kept the book live citing the brain's
  accumulated evidence, which is not reachable from the session. **This conflict
  is open and unreconciled** — see the caveat on the book's card.
- **x48** (Z-Score point-in-time) had a design flaw in its first run: the
  "objective" universe was accidentally identical to the curated one, so its P1
  gate measured nothing. Corrected run recorded separately. The substantive
  finding was unaffected: performance-selecting names from the MIO list makes the
  book markedly *worse* (31.5% vs 86.3%), which is evidence *against* selection
  bias, the opposite of MFI's signature.

## Gates that remain regardless of co-sign
Real-money wiring stays off until all of these are true:
1. **20+ closed forward paper trades.** Currently **0** — the ledger began
   2026-07-31. This is the binding constraint and nothing accelerates it.
2. Z-Score sim re-run on the refreshed Tradier brain (question 3 above).
3. Panel co-sign of x43/x44/x45 — this document.
4. MIO screen creation date, now low-stakes after x45d.

## How to record a co-sign
Append to `docs/lab_runs_evidence_parity.md` under the relevant run: who signed,
the date, and either "co-signed" or the specific objection. A rejection is as
useful as an approval and should be recorded the same way.
