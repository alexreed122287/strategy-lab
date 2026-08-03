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
