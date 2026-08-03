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
