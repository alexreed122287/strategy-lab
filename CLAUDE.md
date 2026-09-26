# strategy-lab-site (GitHub: alexreed122287/strategy-lab)

Public static research site, served by GitHub Pages at
alexreed122287.github.io/strategy-lab/. Research and education only; nothing
here trades and no script holds a trading credential. All times US Central
unless marked UTC/ET.

## First, before anything
- `git fetch && git status`. The local clone lags origin by design: the cloud
  Action commits nightly and the entry-snap jobs commit intraday. Never build or
  edit on a stale clone.
- A failed cloud build opens/comments the issue labeled `daily-build-failure`
  (#81). Check it first when the page looks frozen.
- `python3 scripts/build_log_triage.py` turns `.daily_build.log` into a verdict
  per Mac run.

## Pages
- `index.html` (~1.4 MB, single file, data embedded as `const NAME = {...};`
  blobs). Tabs: Today, Signals, Guide, Positions, Scan, Baskets, Strategy Books,
  Reference, Method. Nav also links ROBERT, JASON, LEAPS 5-Filter.
- `robert.html` - ROBERT, RSI(2) DITM long-call line. Spec locked 08/06/2026.
  PAPER ONLY, indefinite forward test, no capital (posture set 08/26/2026; the
  09/01 pilot was withdrawn, do not reinstate a date unless Alex says so).
  Spliced sections: `ROBSIG`, `ROBSHADOW` markers.
- `jason.html` - J.A.S.O.N., VAP-dislocation reversion DITM long-call line,
  S&P 500 universe (`jason_universe.txt`). PAPER ONLY, forward ledger since
  09/12/2026, no capital; ratio tiles stay grey until 20 closed trades.
  Spliced section: `JASSHADOW` markers.
- `leaps-5filter.html` (+ `leaps_5filter_screener.pine`) - static page.

## Who writes what (two writers - read this before touching index.html)
- Mac-only blobs: SCAN, BASKETS, DAILY, REGIME (and SIGNALS when the Mac runs).
  Produced by `~/repos/strategy-lab-dashboard` (build_dashboard.py --public) and
  moved in ONLY by `scripts/refresh_blobs.py --source out/index.html --target
  index.html` (copies exactly SCAN SIGNALS BASKETS DAILY REGIME, fail-closed).
  If the Mac is down these freeze; SCAN sat at 2026-08-19 for 29 days.
- Cloud (`daily-build.yml`) and Mac both write: TRACK, BOOKSIG, SHADOW, HEALTH,
  ROBSIG/ROBSHADOW, JASSHADOW, and data/*.json ledgers. The cloud also
  regenerates SIGNALS via `scripts/signals_cloud.py` (fail-quiet). The workflow
  header saying it "cannot do SIGNALS" is stale; the step exists below it.
- Repo-maintained display blobs: CALLS, TF, METHOD, BOOKS, NOTIFY.
- NEVER `cp` a generated index.html over this one. Splice scripts REPLACE blobs
  and cannot create them; a clobber on 08/14 deleted 2,157 lines of cloud blobs
  and the next build died with "no `const TRACK = ...;` line found". Recovery:
  `git checkout <last good build> -- index.html`. A healthy blob refresh is a
  few changed lines, never thousands.
- `HEALTH.local_build` is Mac-owned; the cloud carries it forward and must never
  stamp it.

## Daily pipeline
- Mac: launchd `com.alex.strategylab.daily` 15:30 CT Mon-Fri runs
  `scripts/daily_build.sh` (steps 0 sync/stash, 0b Tradier token self-heal from
  ~/options-platform/.env, 1-2 `~/.strategy_lab_build_cmd`, 3-4 fetch + splices,
  5 validate, 5b render gate, 6 push = deploy, 7 mail). `.digest` 16:00 CT is a
  backstop; `.signups` 08:05/13:05/18:05/22:05. Install/repair/check procedure:
  docs/notifications.md "Scheduled agents on the Mac". Plists must live in
  ~/Library/LaunchAgents or they vanish at reboot. launchd does not wake a
  sleeping Mac.
- Do NOT reload or bootstrap launchd agents unasked. Alex decides (schedule
  change = STILL ASK).
- Cloud: `daily-build.yml` crons 21:30 + 22:30 UTC; guard keeps one, window
  16-21 CT, skips if today's BOOKSIG is already published. Deliberately an hour
  after the Mac so it backstops rather than races (issue #81). Mails only when
  a feed advances (stateless-runner dedupe). Mail differs by path: the cloud
  sends ONE combined mail (`notify_daily.py`) + the subscriber digest; the Mac
  sends `notify_robert.py` + `notify_buys.py` separately and no JASON mail.
- `robert-entry-snap.yml` / `jason-entry-snap.yml`: UTC crons 10:45-14:45 as a
  drift LADDER; whole-session window, frozen key, earliest in-window firing wins.
  Captures real option quotes into data/*_chain_snaps.json (never rewritten).
- `robert-chain-gate.yml`: Mondays 13:40/14:40/17:40 UTC. `OI_MIN = 10`; cull
  suspended 08/27, threshold deliberately not moved. Do not change either
  without a reason written beside the constant.
- `notify-now.yml` (manual resend, no subscriber digest), `bb-full-coverage.yml`
  (manual research re-run), `pages.yml` (deploy on push to main), `ci.yml`
  (all suites on PR and push).
- GitHub cron drift is real: measured +20 min to +3.5 h. Never assume on-time.

## Running checks
- No venv: build scripts are stdlib-only by rule (`python3`). Exceptions:
  `bb_harness.py`, `bb_per_name_screen.py` need numpy/pandas - do not add
  imports to build-path scripts.
- Suites (what ci.yml runs): `python3 scripts/jason_shadow_test.py`,
  `notify_daily_test.py`, `notify_jason_test.py`, `notify_robert_test.py`,
  `notify_test.py`, `node scripts/smoke_test.js` (render gate, needs global
  playwright/playwright-core; set CHROMIUM_PATH if the probe misses).
- Also: `python3 scripts/robert_chain_snap_test.py`. Run everything from repo root.
- Never delete or loosen a smoke assertion to go green; fix the page or replace
  the assertion with what is now true.
- Mail preview without sending: `notify_*.py ... --dry-run` (see docs/notifications.md).

## Traps that already broke production
- Render gate fails CLOSED on both paths: a missing browser (08/19-08/26) or a
  flaky assertion (equity-cents check, 09/21-09/24, fixed PR #102) freezes the
  whole site. Symptom is silence, not an error.
- launchd PATH: Homebrew node shadowed the node holding playwright (08/31-09/04).
- Stale ~/.tradier_token 401'd the Mac build 08/12-08/14 (now self-healed).
- Dirty tree after a failed run blocked every later Mac pull (fixed 09-17, step 0).
- Commit stamps and earnings --today must use the Chicago date, not UTC.
- Dot tickers (BRK.B) return empty quotes from Tradier, not errors.
- `SCAN.as_of` is the sweep run date, not its last bar; age is floored at 0.

## Numbers and honesty (non-negotiable on this site)
- ROBERT edge: the honest estimate is the pre-admission 2010-2020 figure,
  +0.43pp/trade, t=1.14, NOT significant; the published "out-of-sample" row is
  not out of sample (corrected 08/19). D11 (measured-fill PF) is unrunnable
  under paper posture, so every P&L is contingent on an assumed f and shown as
  an f band (0.16/0.50/1.00). Chain and model bases are never mixed in a trade.
- Every figure carries its basis (paper/backtested/modeled). Stale feeds are
  demoted and disclosed, never printed beside fresh rows.

## Where the detail lives
- docs/notifications.md - mail, digest, launchd agents, cloud build, ROBERT mail.
- docs/forward_gate_basis.md, docs/benchmark_gate.md, docs/x*_prereg_*.md and
  x*_results_*.md - pre-registrations and verdicts (research ledger).
- docs/mac_handoff_checklist.md - Mac-only lab collection (dated 2026-08-02).
- Workflow and script headers carry the incident history; read before editing.
