# x45 follow-through — list provenance, data hygiene, earnings
Session work 2026-08-02, after x45 completed the live MIO universe. Each item
below was pre-registered in spirit by x45's "real money stays gated on ..."
list; this document records what the follow-through actually found.

## 1. List provenance — answered with composition, not a UI timestamp
The open question was whether the 410-name [000 z score] list was curated with
hindsight, which would invalidate the replication. MarketInOut's screen-creation
date is not reachable from this session, so the list was interrogated directly.

**The list is provably cumulative, not a point-in-time snapshot.** It contains
both:
- 48 names that stopped trading between 2021 and 2025 (WORK/Slack, XLNX, ATVI,
  CTXS, NUAN, CREE, MLHR, HFC, PXD, MRO, DFS, ...), and
- names whose first trading day is 2024, 2025, even 2026 (GEV 2024-03, VIK
  2024-05, FERG 2024-07, INFO 2024-10, FNGU 2025-02, and two names that began
  trading only weeks ago).

A single-moment screen export cannot contain both, so the list was added to over
time and dead names were never pruned. That is the "kitchen-sink watchlist"
pattern — which is *evidence against* fresh hindsight curation (a list built
today to flatter a backtest would not carry 48 corpses), but it does mean recent
additions could in principle be there because they had been doing well.

**So the decisive test was run instead of asserted (x45d).** Split the 358-name
live universe by first trading day and re-run:

| Universe | Names | Ideal CAGR | Trades | PF | MOC-full |
|---|---|---|---|---|---|
| Everything (x45 v2) | 358 | 68.5% | 788 | 3.24 | 57.3% |
| **Existed at backtest start (2019-01-02)** | **323** | **65.5%** | 774 | 3.16 | 50.5% |
| Listed after the start | 35 | 26.2% | 150 | 8.37 | 21.9% |

The edge survives almost entirely on names that were already tradable when the
test begins — late additions contribute ~3pp. Whatever the screen's creation
date turns out to be, the result is not an artifact of names added late.

Residual (still a one-minute manual check, now low-stakes): open the screen in
MarketInOut and read its creation/modified date. It would tighten the story but
can no longer overturn it.

## 2. Data hygiene — Robinhood pre-listing padding (x45 v2)
Robinhood pads a symbol's history backward to the requested start with
**zero-volume, flat-price rows at the IPO price**. 37 of the 218 session names
carried such padding — 29,856 synthetic bars, up to 2,137 rows on a single name.

Fix: every RH series is truncated to its first real-volume bar; remaining
zero-volume rows (trading halts) are dropped; names left with fewer than 300
real bars are removed, as is NBIS (a 390-day halt marking the Yandex→Nebius
splice — the brain excluded it for the same reason). Dropped: **NBIS, PS, UN**.
Live universe 361 → **358**.

Re-running on the cleaned store changed essentially nothing:

| Leg | v1 (padded) | v2 (clean) |
|---|---|---|
| Ideal close | 68.52% | **68.52%** |
| MOC-full (10 seeds) | 55.48% | **57.27%** |
| Next-open (worst case) | 34.80% | **39.04%** |
| Trades / PF | 789 / 3.12 | 788 / **3.24** |

The padding never produced signals because zero-volume bars fail the book's
1M-average-volume gate — the executable legs actually improve slightly once the
fake bars stop diluting the volume average. All x45 gates still PASS. The
headline is unchanged and now rests on audited bars.

## 3. Earnings — what the missing backfill is actually worth (x45c)
The 215 session names have no brain earnings files, so the z-score's mandatory
no-entry / force-exit rule was inert for them. Yahoo (the brain's fetcher) and
Tradier are both unreachable from this session, so the historical backfill must
run on the Mac. Its *importance* was measured instead, by running the same
universes with and without the earnings files present:

| Universe | With earnings | Rule inert | Δ CAGR |
|---|---|---|---|
| 143 brain names | 43.51% | 43.22% | +0.29pp |
| 358 live names | 68.52% | 69.01% | −0.49pp |

The rule is worth a fraction of a point either way and blocks 3-5 trades out of
~790. **The missing backfill does not bias the x45 result materially** — it is a
live single-trade risk control (don't hold through a report), not a driver of
the backtest. That downgrades it from "decisive gate" to "hygiene".

It is still wired up rather than left inert:
- `data/earnings_seed/` — 213 repo-committed files from a Robinhood calendar
  snapshot; 81 names carry a confirmed report date in the next 31 days.
- `next_earnings.py --seed-dir` merges them **under** the brain feed (the brain
  always wins where it has data), lifting universe coverage 145 → 220 of 358.
- `daily_build.sh` passes the seed automatically, so tonight's scan honors the
  rule for the new names.

## 4. Tradier re-fetch — scripted for the Mac
`api.tradier.com` is blocked by this environment's proxy and no token is present
here (by design — keys live in the Mac's shell env only). The re-fetch is
therefore packaged as one command:

    export TRADIER_TOKEN=...        # already set if daily_build.sh works
    python3 scripts/lab_refetch_new_names.py \
        --brain ~/Projects/market-data-brain \
        --names data/x45_rh_basis_names.json \
        --rh-dir <session parquet dir>      # optional, enables the diff
        --earnings                          # also fix the earnings hole

It re-fetches each name from Tradier into the brain, applies the same
zero-volume hygiene, diffs Tradier vs the Robinhood series (median / p99 / worst
day per symbol) and flags any name whose p99 close divergence exceeds 0.5%, then
seeds earnings files and runs the brain's own `refresh_earnings.py` so Yahoo
fills real history. Report lands at `results/x45_tradier_refetch.json`.

After it runs: re-run the z-score sim against the refreshed brain and compare to
`data/x45v2_results.json` before treating any of it as real-money evidence, and
retire `data/earnings_seed/` once the brain files are populated.

## Where the real-money gates stand after this session
- List provenance — **substantially answered** (cumulative list; edge holds on
  names that predate the test). Manual creation-date check remains, low stakes.
- Data basis — **improved but not final**: padding removed, but 215 names still
  ride Robinhood. Tradier re-fetch scripted; the Mac is the only place it can run.
- Earnings — **quantified and wired** (worth ±0.5pp; seed live, backfill scripted).
- Forward paper record — **unchanged, still the binding gate**: 20+ trades needed.
- Lab panel co-sign of x43/x44/x45 — **unchanged, still required**.

Real-money wiring stays OFF. Two of the four blocking items moved from "unknown"
to "measured"; the two that remain are the ones that cannot be shortcut.
