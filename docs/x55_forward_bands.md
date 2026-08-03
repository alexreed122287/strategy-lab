# x55 — forward bands on the books, and the name-matching test

**Run 2026-08-03.** Two things: the books get the three-band forward expectation
the basket cards have always had, and building it surfaced a finding that
matters more than the bands themselves.

## The bands

No new modeling. The formula is the program's existing one, verified against the
basket cards (`live16_rsi2`: test 28.3% × 0.94 = 26.6% friendly; floor 6.8%;
blended 16.7% = the midpoint):

- **friendly regime** = honest recent-era CAGR × 0.94 (what re-selection cost in
  walk-forward testing)
- **bear floor** = the book's **own measured** deep-era CAGR — not the shared
  6.8% RSI2 floor the baskets use
- **blended expectation** = the midpoint

Until now each book card headlined its good era and left the failing one in a
separate card further down. After x53 and x54 every book has a measured floor,
so it gets published at the same altitude as the headline.

## The finding: the two eras were never measured on the same names

A deep run can only use names that existed back then. So the recent leg (398 /
305 / 358 names) and the deep leg (311 / 216 / 313) described *different
universes*, and any spread between them mixed a regime effect with a universe
effect. This re-ran the recent era restricted to exactly the deep-era name sets.

| Book | Recent, all names | Recent, deep-matched | Difference | Deep 2011–18 | Friendly | Blended | Floor |
|---|---|---|---|---|---|---|---|
| Gap Widen RSI2 | 38.42% (398) | 33.29% (311) | −5.13pp | −1.62% | 31.3% | **14.8%** | −1.6% |
| Gap Widen RSI14 | 49.17% (305) | 23.91% (216) | **−25.26pp** | 2.33% | 22.5% | **12.4%** | 2.3% |
| Z-Score | 52.78% (358) | 53.75% (313) | **+0.97pp** | 10.08% | 50.5% | **30.3%** | 10.1% |

**Gap Widen RSI14 loses roughly half its published recent edge** when restricted
to names that also have deep history. **Z-Score loses nothing** — 52.78% on all
358, 53.75% on the 313 with deep history. Gap Widen RSI2 gives back 5.1pp.

That contrast is now the strongest single reason to rank these three books
differently, and it was invisible while each era was measured on its own
universe. A book whose recent number depends on names that did not exist in the
deep era is making a bet on a listing cohort, not only on a rule.

## Deep numbers vs x53

These supersede x53 slightly, in the same direction:

| Book | x53 deep | x55 deep | Names |
|---|---|---|---|
| Gap Widen RSI2 | −0.09% | −1.62% | 302 → 311 |
| Gap Widen RSI14 | 0.02% | 2.33% | 201 → 216 |

The cause is coverage, not method. The deep store grew after x53 ran — the x54
Z-Score fetch added 248 names, and 325 of the 593 deep parquets are Z-Score MIO
names — so more Gap Widen names now have 2011–18 history. Same engine, same
spec, same verdict: both books sit near zero in the deep era against ~10%/yr for
simply owning the same names.

## Caveats

- **Survivorship**, as with every deep test here: the 2011–18 universe is
  today's survivors, which lifts both the book and its hurdle. That is why the
  two are compared against each other rather than an absolute bar.
- **The bands are not a promise.** They are three numbers bracketing measured
  eras. The blended figure is a midpoint, not a forecast, and no backtest can
  say which regime comes next.
- **The band inputs differ by book in one way worth naming:** the friendly leg
  uses the *matched* recent number, which for Gap Widen RSI14 is well below what
  it would trade on the full MIO list. That is deliberate — a band whose two
  legs describe different universes is not a band.

## Artifacts

- `data/x55_forward_bands.json` — all three books, both eras, band inputs.
- Dashboard: Books tab → "x55 — forward bands, and how much of each recent
  number needs recent listings", plus a three-band block on each book card and
  the blended figure in the Today tab tier reasons.
