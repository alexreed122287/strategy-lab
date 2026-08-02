# x45 (SESSION) — Z-Score universe completion: the live MIO list on session-fetched data
Pre-registered 2026-08-02 BEFORE computing any strategy result on the new data.
Engine: lab fillmode_sim.py unmodified (anchors reproduced the F22 frozen
baseline exactly in x43; x44 ran on the same engine). Data: brain parquets +
a session Robinhood fetch for the names the brain lacks.

User instruction (2026-08-02): "Remove the delisted tickers altogether but
incorporate the live tickers not already included in the brain or run the
backtested data required on them then optimize."

## Data work already done (fetch + classification only — no strategy stats yet)
- Fetched the 267 missing/corrupt MIO-list names via the Robinhood API
  (split-adjusted daily bars, 2018-01-01 → 2026-07-31).
- Anchored RH bars against Tradier-vintage brain parquets on overlap names:
  AAPL p99 close diff 0.006%, index/sector ETFs ≈0%; GE p99 4.7% (spin-off
  adjustment convention), OHI 1.8% (special dividends), EWT one 17.9% bad
  print. Verdict: usable with eyes open; a Tradier re-fetch on the Mac stays
  the final data authority for any real-money step.
- 218 live clean RH names (incl. JMIA/NBIS/SKIN rescued by dropping
  zero-price rows; corrupt brain parquets for AIG/CSX repaired with RH data).
  FCEL excluded — unfixable wild prints.
- 48 dead/unfetchable names REMOVED per the user instruction (ATVI, XLNX,
  WORK, RDS-A/B, PXD, MRO, GPS, K, DFS, ... — full list in x45_universe.json
  and the results artifact). Stated plainly: this bakes survivorship bias
  into the run — ~12% of the MIO list is unknowable from RH, and MIO's
  67.2% claim presumably includes those names' trades. The bias is a data
  hole, not a modeling choice, and it cuts both ways (dead ≠ losing: many
  were acquisitions).
- Expanded live universe: 361 names = 143 brain + 218 RH.
- Earnings: brain earnings files cover the 143; the 218 RH names have none,
  so the engine's mandatory z-score earnings no-entry rule is inert for them
  (missing file → empty set). That is closer to the raw MIO spec (which has
  no earnings rule); the lab's earnings backfill for the new names is a
  documented TODO before real-money consideration.

## Legs (universe = the 361 live names, membership recorded in results)
ideal_close (MIO mechanics, 0.01%/side) | moc_ideal | next_open_020 |
hybrid_moo005 ×10 seeds | moc_full_005 ×10 seeds (x43-licensed basis) |
per-name screen for all 361 (close fills, 0.02% spread, earnings-free —
same harness as x44) | causal fold exactly as x44: tier-select on 2019-22
per-name stats (win≥78, avg≥1.2, n≥6), trade 2023-26, vs the full 361 on
2023-26.

## "Optimize" scope (pre-committed)
Universe completion + the causal fold re-check ONLY. No parameter re-tuning:
x40 banned hindsight curation, the z parameter plateau was validated in the
lab, and the user's screenshots pinned the spec. If the fold again shows
full-universe ≥ curated (as in x40 and x44), "optimize" resolves to "trade
the full live list."

## Pre-registered gates
- E1 replication strength (expanded): ideal_close CAGR ≥ 30% AND PF ≥ 2.5
  AND every calendar year positive.
- E2 executable: moc_full seed-mean CAGR ≥ 0.75 × ideal_close AND ≥ 22%.
- E3 continuity: expanded ideal_close within 8pp of x44's 143-name 43.51%
  (i.e. ≥ 35.5%). Adding 218 names may dilute or improve the aggregate; a
  collapse would say the 143-name result was a subset artifact or the RH
  data disagrees with Tradier where it matters.

## Pre-committed outcomes
- ALL PASS → the paper book's scanner universe becomes the 361-name live
  list (`mio_universe_live`, delisted removed per the user instruction),
  replacing the 143-name runnable subset; per-name stats for the 218 new
  names join BOOKS with src "rh-session" and the RH-basis caveat; x45
  record + tile on the z card. Book remains ACTIVE PAPER. Display basis
  stays MOO ×0.71 until the lab panel co-signs x43/x44/x45. REAL-MONEY
  wiring remains OFF pending: MIO screen-creation-date provenance, Tradier
  re-fetch of the RH-basis names into the brain + earnings backfill, ≥20
  forward paper trades, lab panel co-sign.
- E1 or E2 FAIL → numbers recorded on the book; scanner stays on the
  143-name x44 universe; the expanded run stands as evidence against
  universe expansion on RH data.
- E3 FAIL alone (E1+E2 pass) → treated as a data-quality alarm, not an edge
  verdict: scanner stays on the 143-name universe until the lab's Tradier
  re-fetch arbitrates dilution-vs-vendor-artifact; both results recorded.
