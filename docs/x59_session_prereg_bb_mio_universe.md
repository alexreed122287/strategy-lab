# x59 (SESSION) — BB Rubber Band re-run on MIO's OWN universe

Pre-registered 2026-08-03 **before computing anything**. Written after checking
data coverage only; no strategy result exists at the time of writing.

## Why this is being re-run

BB was killed 2026-08-01 by the pre-registered SPEC C gate. The owner has now
supplied MIO's own 301-name ticker list for this screen. That is exactly the
correction x52 applied to Gap Widen: both books were killed on **lab-derived**
universes, and a universe chosen from a book's own backtest results is hindsight,
not the rule. The rule deserves a test on the list its author actually uses.

**This is not a re-litigation of the kill.** The kill was not about CAGR. BB
failed on **execution retention** — the executable leg kept 0.096 of the
idealized leg against a pre-registered bar of 0.80 (idealized 8.1% → executable
0.78%). A different universe can change the level; whether an edge survives
execution is a property of the rule and the fills. So the gate that killed it is
re-tested first and unchanged.

## Spec (screenshot-corrected 2026-08-02, unchanged here)

Entry, all true at the close:
- price > 20
- 50-day average volume > 1,000,000 shares
- price > sma(200)
- price < bblb(20,2)  — the lower Bollinger band, sma(20) − 2·stddev(20)
- **rsi(2) < 10** — the actual MIO gate; the originally-ported rsi(3)<20 is dead
- healthcare excluded; NYSE/NASDAQ

Exit: price > ema(5) at the 3:45 screen → MOC, or the 10-bar time stop.

Mechanics: the program standard — $100k, 3 slots, 40% of equity per position,
0.05%/side friction, MOO entry into the next opening auction.

## Universe

MIO's 301 supplied names, verbatim. Local coverage at write time is **180 of
301**; the remaining 121 are fetched before the run and the final count is
recorded in the artifact. Names that cannot be sourced are listed, not silently
dropped.

Two properties of this list are recorded now, before any result, because both
will shape how the numbers read:

1. **It contains roughly a dozen leveraged and inverse ETFs** — TQQQ, UPRO,
   SPXS, SDS, FAS, TECL, GUSH, TBT, QLD, VXX, UCO among them. Mean reversion on
   3× instruments is a different animal from mean reversion on equities: it
   inflates both return and drawdown, and x22–x24 in the prior research archive
   already found levered-beta baskets flatter this family of books. If the result
   is carried by those names, that is the finding.
2. **It contains delisted names** (BBBY, XLNX, RDS-A/B, NUAN, UTX, HFC, STL,
   STOR, SWCH, PDCE, FBHS, LTHM, MMP, UNVR, CLR, OSTK, SPLK, FTCH). They are
   unfetchable, so their trades are missing from the run — survivorship bias in
   the book's favour, same hole as x45. Direction is knowable; magnitude is not.

## Pre-registered gates

All four must pass. They are the same bars this program has already used, not
new ones written for this run.

- **B1 — execution retention (the gate that killed it).** executable CAGR ÷
  idealized CAGR **≥ 0.80**, the SPEC C bar verbatim. This fires first: if the
  edge does not survive execution, nothing else matters and the kill stands.
- **B2 — positive at the program standard.** Executable CAGR > 0 at 0.05%/side.
- **B3 — beats its own universe.** Executable CAGR > equal-weight buy-and-hold
  of the **same names** over the **same window**, on return **and** drawdown.
  Survivorship-neutral by construction — both sides face the identical filter.
- **B4 — era.** Executable CAGR positive in **both** 2019–22 and 2023–26. No
  single-era edge.

## Pre-committed outcomes

- **ALL FOUR PASS** → BB is **un-killed to ACTIVE PAPER**. It rejoins
  `scan_book_signals.py` on the MIO universe, takes one slot in the shadow
  account like every other book, and its numbers are published with the standard
  era and survivorship caveats. Real money remains off — that gate is unchanged
  and unrelated.
- **ANY FAIL** → the kill **stands**, the numbers are recorded on the book's card
  anyway, and the specific gate that failed is named. A second failure on MIO's
  own list would close the question: it would mean the earlier kill was not a
  universe artifact.

## What would make this run worthless

Recorded in advance so it cannot be rationalised afterwards:

- Reporting the idealized leg as the headline. BB's idealized number was never
  the problem; the executable one was.
- Quietly widening B1. The 0.80 bar was pre-registered in SPEC C and is reused
  verbatim here.
- Treating a pass carried by the leveraged ETFs as a pass for the rule. If the
  book's return concentrates in TQQQ/UPRO/SPXS and their kin, that is reported as
  the result, whatever the aggregate says.

---

# RESULT — 2026-08-04, full coverage on GitHub Actions

**VERDICT: FAIL on B1. The kill stands.** Per the pre-committed outcomes above,
a second failure on MIO's own list closes the question: the earlier kill was not
a universe artifact.

| Pre-registered gate | Measured | |
|---|---|---|
| **B1 execution retention ≥ 0.80** | **0.744** | **FAIL** |
| B2 executable CAGR > 0 | 42.10% | PASS |
| B3 beats B&H of same names, return AND drawdown | +21.84pp, −26.6% vs −40.5% | PASS |
| B4 both eras positive | +102.7 / +228.8 | PASS |

| Leg | CAGR | Max DD | PF | Trades |
|---|---|---|---|---|
| Idealized (close fills) | 56.62% | −25.33% | — | 718 |
| **Executable (MOO → MOC)** | **42.10%** | **−26.60%** | — | 718 |
| Worst case (next-open, 0.2%/side) | 29.06% | −33.34% | — | 718 |
| Buy & hold, same names | 20.26% | −40.49% | — | — |

The bar was not touched. 0.80 is the SPEC C figure, reused verbatim, exactly as
this document committed.

## What the universe was worth

Retention went **0.096 → 0.744**. The universe mattered enormously and the
verdict did not change. Both are true, and the reason for the kill has changed:
not "this book has almost no edge" but "this book has a real edge that loses
**25.6%** of itself between the signal and the fill."

## Coverage

**263 of 301** ran, up from 180 in the session run. The 121-name gap that made
the session verdict provisional is now down to 38, listed here as this document
required:

> ABB, BK, CFX, CLR, CMA, CWAN, ERJ, FBHS, FTCH, FYBR, HFC, IAC, K, LTHM, MAXN,
> MMP, NCR, NUAN, NYCB, OSTK, PDCE, RDS-A, RDS-B, SATS, SEAS, SMAR, SPLK, SPR,
> SRC, STL, STOR, SWCH, TPH, UNVR, UTX, VRNT, XLNX, YY

Roughly half are the delistings predicted above (CLR, FBHS, FTCH, HFC, LTHM,
MMP, NUAN, OSTK, PDCE, RDS-A/B, SPLK, STL, STOR, SWCH, UNVR, UTX, XLNX) — their
absence biases **in the book's favour**. The remainder are live, liquid names
Tradier did not return in this run; cause unconfirmed.

Two separate effects moved retention, in opposite directions, and they should
not be run together:

- **Coverage 180 → 263 moved it UP**: 0.714 → 0.787.
- **The window correction moved it DOWN**: 0.787 → 0.744, on the same 263 names.

Neither is a clean controlled comparison — the 180-name session run also used a
local store rather than Tradier — so the honest statement is that the two
largest known defects in the earlier number pushed it in opposite directions and
it lands at 0.744. Every version of this measurement misses the 0.80 bar.

## The leveraged-ETF check, which this document pre-committed

Named above as a way the run could be worthless. Measured per trade: **6**
levered names traded (FAS, GUSH, SDS, SPXS, TBT, UCO), **16 of 718** trades,
contributing **−3.2% of P&L**. They are not carrying the result — they were a
small drag on it. This is an equity result.

## A correction inside this run, disclosed rather than buried

The first full-coverage attempt fetched 2600 **calendar** days, reaching only
2019-06-20. `sma(200)` then stayed NaN until roughly 2020-04, so the book sat in
**cash for the first ten months of its own window — including the entire COVID
crash**. It posted −18.2% max drawdown against buy-and-hold's −40.5% on an
advantage that came from fetch depth, not from the rule. `yby[2019] = 0.00` was
the tell.

Re-run at 3300 days with a full warmup. First trade lands 2019-01-02 as
intended, and **every number moved against the book**:

| | short window | corrected |
|---|---|---|
| B1 retention | 0.787 | **0.744** |
| Executable CAGR | 49.19% | 42.10% |
| Executable max DD | −18.22% | **−26.60%** |
| B3 excess | +30.42pp | +21.84pp |

**B1 was never affected** — it is a ratio of two legs over identical trades on an
identical window — so the verdict never moved. The published comparisons against
buy-and-hold did, and they were flattering the book, which is why this was fixed
before publication rather than after. The workflow now asserts its own
first-trade date and fails loudly instead of publishing a short window again.
