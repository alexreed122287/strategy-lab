# Forward-record gate — which ledger counts

**Decided 2026-08-03, before any forward trade closed.** Recording it here is
the point: choosing the denominator after seeing which one looks better is
exactly the hindsight this program is built to prevent.

## The decision

> The binding real-money gate is **20 closed trades in the shared $100k paper
> account, program-wide.** The skip-free per-book ledger is still published, but
> it does not open the gate.

## Why the question existed

The shadow book keeps two records off the same signals:

- **The skip-free ledger** takes *every* qualifying signal, ignoring slots and
  cash. It answers "does this rule's edge show up forward?"
- **The account replay** puts those same signals through one $100k account —
  equal sleeve per book, each book's own 3-slot limit inside its sleeve — and
  skips anything that arrives with no free slot or no cash. It answers "what
  would this system have done with real money?"

On 2026-07-31, the first day of the record, the two diverged immediately: the
ledger filled **27** positions; the account took **6** and skipped **21**. MFI
alone fired 23 signals against 3 slots.

At that rate the ledger clears 20 closed trades in roughly two weeks and the
account in roughly five to six. Whichever was chosen after the fact would have
been chosen *because* of its timeline or its numbers.

## Why the account

Real money follows the account, not the ledger. The gate exists to decide
whether to wire real capital, so it has to count the trades real capital would
have taken. A record built from 21 skipped signals is a measurement of the
rule, not of the system — a useful thing, and a different thing.

The cost is accepted knowingly:

- **It is ~5× slower.** Five to six weeks instead of two.
- **It pools all five books.** Twenty account trades spread across five books is
  about four per book — enough to validate that the system runs, not enough to
  validate any single book. Per-book confidence still comes from the backtests
  and from the skip-free ledger, both of which stay published.
- **It is sensitive to modeling choices.** The equal-sleeve split and the
  sleeve-equity/slots sizing are not lab-validated parameters. They are
  documented in `scripts/shadow_book.py` and were fixed before this decision.

## Where it shows up

- `scripts/shadow_book.py` — `GATE_CLOSED_TRADES = 20`; `portfolio()` returns
  `gate_closed`, `gate_target`, `gate_remaining`, `gate_met`, `closed_by_book`,
  and the closed-trade win/avg/PF.
- Dashboard → Positions → "Real-money gate" tile, and the per-book Closed column.
- Dashboard → Books → Evidence parity, column renamed **Forward (account)**.
  Cells go *partial* on a book's first account close and *has it* when the
  program-wide count reaches 20.

## What this does not change

Clearing 20 closed account trades does not by itself authorize real money. The
other standing gates are unaffected: the lab panel co-sign, and every book's own
evidence-parity row. Z-Score, Gap Widen RSI2 and Gap Widen RSI14 are all
recorded era-dependent (x53, x54) and stay on paper regardless of trade count.

## Amendment — one slot per book (2026-08-03, at zero closed trades)

The account now holds **one position per book**, not three. Decided the same day
as the gate basis above and for the same reason: the account had **zero closed
trades**, so the model could still be changed by pre-registration rather than
re-cut around a record already in flight. Both decisions are now fixed.

**What it selects.** Each book's own #1-ranked signal by its own ranking rule —
Gap Widen by 52-week relative strength, Z-Score by RSI(3). Nothing is picked
across books by hand, which matters because this program has established twice
over, from two independent evidence chains, that discretionary selection inside
these books destroys the edge. Friday's scan resolves to **JBLU** (Gap Widen
RSI2), **BEN** (Gap Widen RSI14) and **KNX** (Z-Score), plus one each for
RSI2 and MFI.

**Position size is unchanged, and that took a correction.** The first cut of this
change used one constant for two different things — the concurrency cap and the
position-size divisor — so dropping slots from 3 to 1 silently tripled per-name
risk to a full ~$20k sleeve. Caught and split the same day, still at zero closed
trades:

- `SLOTS` — how many positions a book may hold at once. **1**, per this decision.
- `SIZE_DIVISOR` — the validated sizing denominator. **Unchanged at 3**, so a
  position remains ~1/3 of its sleeve (~$6.7k): the 40%-of-equity, 3-concurrent
  rule every book was validated under.

Holding fewer names must not enlarge each one. Those are independent choices and
they are now independent constants.

**The real cost is idle cash, not concentration.** Five books × ~$6.7k is ~$33k
deployed against ~$67k sitting in cash. That is deliberate rather than an
oversight: x40 tested an overlay to put idle cash to work and **killed** it, so
the cash stays in cash instead of being levered into the remaining names.

**It still departs from validated mechanics in one way.** Every book was
validated at three *concurrent* positions; this account holds one. Per-trade risk
matches the backtests, portfolio construction does not — so the forward record is
a test of *this account*, and its aggregate return is not comparable to any
book's published CAGR.

**Effect on the gate.** Unchanged in definition — still 20 closed account
trades, program-wide. Fewer concurrent positions means slower accrual: on the
current signal rate, roughly two months rather than five to six weeks.

**Effect on the record so far.** `portfolio()` is a pure replay, so the account
history recomputes under the new model: Friday's fills narrow from six positions
to two (one RSI2, one MFI at ~$6.7k each), with 25 signals skipped rather than
21. No closed trade is affected, because there are none.

## Amendment — RSI2 and MFI move to MOO entry (2026-08-03, at one closed trade)

The shadow book recorded RSI2 and MFI entries **at the signal close** — their
validated basis. But the signal is only known *at* that close, the daily build
runs after it, and the buy email lands ~15:50 CT. **Those fills were not
obtainable**, and crediting the account with them inflated the forward record on
the two books that fire most often — the record that gates real money.

Measured cost of waiting for the next open, same universes and window as the
benchmark gate:

| Book | MOC (signal close) | MOO (next open) | Cost | Retention |
|---|---|---|---|---|
| MFI | 59.50% | 50.48% | −9.02pp | 0.848 |
| RSI2 | 39.93% | 34.22% | −5.71pp | 0.857 |

Both lose ~15% of CAGR. **MFI loses more in points**, because it starts higher
and fires far more often — the opposite of an earlier reading of this program's
archive, which noted MFI survives a full day's lag with PF 2.33 intact. Both are
true: MFI remains viable under delay, and the delay is not cheap. Note also that
next-open is a *smaller* delay than the archive's lag-1 (next day's close),
which is why RSI2's −5.71pp here is far gentler than the 59.8→31.9 recorded
there.

`BASIS` is therefore `moo` for all five books. The record now stores what the
owner can actually get.

**One closed trade predates this** (KRE/MFI, entered at a close). It is
disclosed rather than back-dated — the ledger accumulates entries and cannot be
replayed from itself the way `portfolio()` can. Open positions carried at the
old basis are likewise left as recorded.

**Reversible, and the reversal must be pre-registered too.** If the intraday
3:45 send is built and actually used, close fills become obtainable and these
two books move back to `close` — but that change has to be registered before the
trades it would affect, exactly as this one was.

## Correction — the replay was dropping same-day round trips (2026-08-04)

Not a model change and not a re-cut. The rules above are untouched; the replay
that applies them had a bug, and fixing it **added** trades the account really
took under the already-registered rules.

`portfolio()` sorted each date's events with every exit ahead of every entry, so
a position that opened and closed on the *same* date had its exit processed
while the account still held nothing. The exit found no position and was
discarded; the entry then ran and left a position open that had in fact already
closed. Two things followed, both wrong:

- the round trip never reached the closed-trade count that **is** the gate, and
- the phantom open position held the book's only slot indefinitely.

This was not an edge case. The Gap Widen books round-trip intraday **by
design** — MOO entry, `3:45 -> MOC` exit — so it fired every time they did.

**What it cost, on the record as it stood 2026-08-03:**

| | Before | After |
|---|---|---|
| Closed account trades (the gate) | 1 of 20 | **3 of 20** |
| Account open positions | 4 | 2 |
| Cash | $73,421 | $87,036 |

The two recovered trades are **JBLU** (Gap Widen RSI2, +1.04%) and **BEN** (Gap
Widen RSI14, +3.18%) — two of the three the owner authorized on 2026-08-03. They
had been executing correctly in the ledger and were being dropped on the way
into the account record. KNX (Z-Score) was unaffected and remains open.

Ordering is now three-phase within a date: exits of positions opened on an
**earlier** date (these free a slot first), then entries, then exits of
positions opened the **same** date. The sort is stable, so each book's ranking
order still decides which signal takes a contested slot.

**Why this is a correction and not hindsight.** The gate's definition, the slot
count, the sizing divisor and the entry basis are all unchanged and all were
fixed before the trades they govern. The published count moved because the
replay now counts what the account did, which is what the pre-registered rule
always said to count. Recording the direction matters: it moved the gate
*closer*, which is exactly the direction that warrants disclosure rather than
silence.
