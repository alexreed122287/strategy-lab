# What to run on the Mac — consolidated checklist

## TL;DR — one command does all of it

    cd ~/path/to/strategy-lab && bash scripts/lab_mac_session.sh

It runs the Tradier re-fetch + earnings backfill, collects the `gap_widen_lab`
config needed to resolve the RSI14 reproduction gap, collects your generator's
RSI2/MFI arm definitions so the benchmark gate can be extended to them, then
commits and pushes the artifacts on a `lab/mac-collect-<date>` branch. Every
step is fail-soft and safe to re-run; credential lines are redacted before
anything is written to the repo, and nothing in it trades.

If a path is not auto-detected, re-run with it supplied:

    GWLAB=/path/to/gap_widen_lab GEN=/path/to/generator bash scripts/lab_mac_session.sh

Then tell your Claude session "the lab collect branch is pushed".

The detail for each step follows, if you'd rather run them individually.

Last updated 2026-08-02. Everything here needs either a broker token or a lab
engine that only exists on your machine; none of it can run from a session.
Ordered by value. Nothing here is urgent enough to interrupt a day.

## 1. Tradier re-fetch + earnings backfill for the z-score book (~20 min)
Why: 215 of the z-score book's 358 live names ride Robinhood history. Robinhood
is usable (anchored 8/10 p99 < 0.2%) but it pads pre-listing history with fake
zero-volume bars — 29,856 of them were found and removed in x45 v2 — and it
adjusts spin-offs/special dividends differently (GE p99 4.7%, OHI 1.8%).
Tradier is the program's data authority.

    export TRADIER_TOKEN=...          # already set if daily_build.sh works
    cd ~/path/to/strategy-lab
    python3 scripts/lab_refetch_new_names.py \
        --brain ~/Projects/market-data-brain \
        --names data/x45_rh_basis_names.json \
        --earnings

Adding `--rh-dir <dir>` (a directory of the session's Robinhood parquets, if you
still have them) turns on a per-symbol Tradier-vs-Robinhood diff. Report lands in
`market-data-brain/results/x45_tradier_refetch.json`; anything with p99 close
divergence > 0.5% is listed under `material_divergence` and deserves a look
before its per-name stats are trusted.

`--earnings` also seeds earnings files for the new names and runs the brain's own
`refresh_earnings.py` (Yahoo), which fixes the one hole the session could not:
the 215 names have no earnings history, so the z-score no-entry rule is inert for
them in backtests. Measured impact is only ±0.5pp of CAGR (x45c), so this is
hygiene, not a correction.

Afterwards: re-run the z-score sim against the refreshed brain, compare to
`data/x45v2_results.json`, and retire `data/earnings_seed/` from the repo once the
brain files are populated (`next_earnings.py` will then pick everything up from
the brain, and the seed becomes dead weight).

Dry-run first if you want to see what it will touch:
`... --earnings-only --dry-run` (writes nothing, prints the plan).

## 2. Resolve the Gap Widen RSI14 reproduction gap (~15 min, needs the GW lab)
Why: x46 built an independent harness from the RSI14 book's published spec and
could NOT reproduce its published 51.6% ideal-close CAGR on any published
universe tier — qualified 41.6%, qualified+scan 38.8%, priority-25 77.8%, at full
199/199 name coverage. The same harness reproduces the RSI2 book to within
0.74pp (57.26% vs 58.0%), so the harness itself is not obviously broken.

Either the RSI14 book's published number came from a universe or parameter set
that is not what the dashboard states, or the harness differs from the lab engine
in a way that matters only for the 14-period variant. Open `gap_widen_lab` and
check which universe and slot count produced `results/moc_results.json` /
`moo_results.json` for the RSI14 book, then tell me and I will reconcile the
dashboard to whichever is right.

Until then the dashboard labels the RSI14 deep-era result UNANCHORED — computed
and shown, but not permitted to flip its evidence-parity cell.

## 3. Check the MIO screen's creation date (~1 min, low stakes now)
Why: it was the last provenance unknown. It has since been largely settled from
the list's own composition — the list is provably cumulative (it holds 48 names
dead since 2021-25 alongside names first traded in 2024-26), and restricting the
book to the 323 names that already existed at the 2019 backtest start still earns
65.5% vs 68.5% for all 358. So late additions are not carrying the edge, and the
creation date can no longer overturn the result. Worth reading off the screen next
time you are in MarketInOut, not worth a special trip.

## 4. Nothing else is blocked on you
The forward paper record accrues on its own from the nightly build — it is the one
gate that cannot be accelerated, and at roughly one z-score signal every few days
the 20-trade threshold is months out. The lab panel co-sign of x43/x44/x45 is the
other, and that is a decision, not a task.
