# x54 — Z-Score deep out-of-sample (2011–2018) on the MIO universe

**Run:** 2026-08-03 · **Verdict: FAIL** (fails the buy-and-hold gate, passes the
positivity gate) · **Consequence:** the Z-Score book is recorded as
**era-dependent**; it stays on paper, its real-money gate is unchanged.

## Pre-registered gates (fixed before any number was computed)

Identical to x53, which ran this same test on Gap Widen:

1. Executable CAGR > 0 at the program's 0.05%/side friction standard.
2. Executable CAGR > equal-weight buy-and-hold of the **same names** over
   2011–2018.

Both had to hold. Gate 1 passed, gate 2 failed.

## Result

Book column is the executable basis (MOO entry + 3:45 MOC exit, 0.05%/side,
mean of five perturbation seeds). Buy-and-hold is equal-weight, monthly
rebalanced, over the identical window and the identical name list — so both
sides face the same name filter and the comparison needs no survivorship
assumption.

| Era | Names | Book CAGR | DD | PF | Buy & hold | B&H DD | Excess |
|---|---|---|---|---|---|---|---|
| Deep 2011–2018 | 313 | 10.08% | −28.0% | 1.42 | 11.65% | −22.7% | **−1.57pp** |
| Recent 2019–2026 (same names) | 313 | 53.75% | −18.4% | 2.69 | 17.73% | −42.3% | **+36.02pp** |

Idealized close-fill deep CAGR: 13.85% (PF 1.53, 683 trades, 69.7% win).
Executable seeds: 13.44 / 6.22 / 9.53 / 11.27 / 9.94.

## Reading it honestly

- **This is not Gap Widen's failure.** Gap Widen went to roughly zero in the
  deep era (−0.09% and +0.02%) and lost to its own universe by ~10pp at double
  the drawdown. Z-Score stays clearly profitable and merely stops *adding*
  anything over owning the same names.
- **The deep edge is indistinguishable from zero, not reliably negative.** Two
  of the five seeds (13.44%, 11.27%) beat the 11.65% hurdle; three do not. A
  −1.57pp mean sits inside that spread. The defensible claim is "no measurable
  edge in 2011–2018", not "negative edge".
- **The recent number is a regime observation.** +36pp over buy-and-hold on the
  same names in 2019–2026 is real and large, and half the available history says
  it was absent. It must not be treated as a forward expectation.
- **Every cross-era-tested book in this program has now failed at least one
  era.** RSI2 fails 2023–26 (x47) and passes 2015–18 (x50); Gap Widen passes
  2019–26 and fails 2011–18 (x52/x53); Z-Score passes 2019–26 and fails
  2011–18 (x54). That is the finding, and it argues for era-awareness across
  the program rather than for killing any single book.

## Correction — the first run of this test was wrong

The first pass (x54, never shipped) reported **PASS by 0.77pp** on 325 names
(exec 11.37% vs B&H 10.60%). It was contaminated.

Robinhood returned bars flagged `interpolated: true` for 24 of the symbols
fetched for the deep window — several roughly 95% synthetic (BE has real data
only from 2018-07-25; BILI from 2018-03-28). These are zero-volume flat-price
rows: the same padding defect x45 found and stripped. The difference is the
engine. `gw_harness.py`, built in-session for Gap Widen, filters `volume > 0`;
the lab's own `fillmode_sim.py`, which this test used unmodified, does **not**.
So the fakes entered the simulation.

The store was rebuilt — drop `volume <= 0`, require ≥300 real bars — which
dropped 12 names entirely (ACMR, BE, BILI, EVRG, JEF, LIN, MGY, NTR, REZI,
SPOT, STNE, TAN) and truncated 77 series to their first real bar. On the clean
store the verdict flipped from PASS to FAIL. **Only the clean run is reported.**

Standing lesson: any deep test routed through `fillmode_sim` needs the
zero-volume filter applied to the store first. The engine will not do it.

## Caveats

- **Survivorship.** The 2011–2018 universe is today's survivors — names that
  existed then and still trade now. That biases the deep row *up* for both the
  book and its hurdle, which is exactly why the two are compared to each other
  rather than to an absolute bar. 45 of the 358 live MIO names have no
  2011–2018 history at all and are absent from both sides.
- **Basis.** Deep-era bars are Robinhood-sourced (the Tradier re-fetch covers
  the recent era). The recent row here is the audited Tradier basis.
- **Universe.** MIO's own live 358-name list, restricted to the 313 names with
  ≥300 clean bars in the window. Selection is MIO's, not the lab's — the same
  correction x52 applied to Gap Widen.

## Artifacts

- `data/x54_zscore_deep.json` — full record, both legs, all seeds.
- Dashboard: Books tab → "x54 — Z-Score deep era on the MIO list", plus the
  "Deep era 2011-18 (x54)" tile on the Z-Score card and the Today tab tier.
