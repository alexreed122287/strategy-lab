# The benchmark gate — does a book beat simply owning its own universe?
Added 2026-08-02. This is the test x46 stumbled into while convicting Gap
Widen's 2011-2018 era, generalized and applied to every live book.

## Why this is the right question
Every other gate on this program asks "is the number good?" — CAGR, PF,
drawdown, era stability. None asked the question an investor actually faces:
**is trading this book better than just buying its names and holding them?**
A book can post 40% CAGR and still be a waste of effort and risk if equal-weight
buy-and-hold of the same tickers over the same window returned more.

It is also the only comparison on this dashboard that is **survivorship-neutral
by construction**. Both legs are computed on the identical name list over the
identical window, so the delisted-name hole that qualifies almost every other
result here cancels out. No assumption about dead companies is required.

The book leg is reported at the program's own published execution standard
(0.05%/side), not at idealized fills.

## Results (2019-01 → 2026-07) — all five live books
| Book | Book CAGR (0.05%/side) | Book DD | Buy-and-hold, same names | B&H DD | Excess |
|---|---|---|---|---|---|
| Z-Score (358 names) | 60.83% | −22.97% | 18.75% | −41.78% | **+42.08pp** |
| Gap Widen RSI2 (340) | 50.59% | −31.50% | 19.42% | −41.82% | **+31.17pp** |
| Gap Widen RSI14 (198) | 34.23% | −36.90% | 19.67% | −44.23% | **+14.56pp** |
| MFI (192) | 59.50% | −26.04% | 24.13% | −37.91% | **+35.37pp** |
| RSI2 (193) | 39.93% | −20.73% | 22.72% | −38.46% | **+17.21pp** |

RSI2 and MFI were added 2026-08-02 once the arm definitions came off the Mac
(`agentic-cron/rsi2_engine.py`, `rsi2_x9_mfi_friday.py`): RSI2 enters on
rsi(2) < 10 with close > sma(200); MFI is the same book with mfi(3) < 10
replacing the RSI trigger; both exit on close > sma(5) or a 10-bar stop, 3
slots. Their legs are computed at the same 0.05%/side standard.

**Every live book clears the hurdle, on return and drawdown simultaneously.**
That is the single most reassuring fact on this dashboard, and it was unknown
until now.

All three beat their universe **on return and on drawdown simultaneously** —
they are not simply levering the same exposure. Roughly 19% a year was available
by owning these names and doing nothing, so that is the hurdle any of this work
has to clear, and it is a higher hurdle than most strategy write-ups admit.

## The contrast that matters
Gap Widen RSI2 beats its own universe by **+31pp in 2019-2026** and **lost to it
by ~10.5pp/yr in 2011-2018** (x46). That is a clean, quantified statement of
regime dependence — far more useful than "validated" or "failed" alone. The book
is not broken and it is not proven; it works in tapes that resemble the last six
years.

## Caveats that stay attached
- Buy-and-hold here is equal-weight, daily-rebalanced to equal weight by
  construction of the mean-return calculation, with no costs. That flatters the
  benchmark slightly, which is the conservative direction for the book.
- The universes are today's tradable names, so both legs are survivorship-
  filtered. The comparison is fair; the absolute levels are not clean.
- One name (AUR) was dropped from the RSI14 benchmark for a zero-price bar —
  the same class of vendor defect x45 found in the Robinhood padding.

## What would strengthen it
Apply the same gate to the RSI2 and MFI generator books, which have per-name
records but no portfolio-level sim in this repo. That needs their engine, which
lives with the lab, and is the natural next item after the Mac work.
