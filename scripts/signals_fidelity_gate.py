#!/usr/bin/env python3
"""FIDELITY GATE for any attempt to port the RSI2/MFI signal generator into
this repo, so the GitHub build can produce SIGNALS without the Mac.

The rule this enforces: a re-implementation is trusted only if it reproduces
the Mac generator's own SIGNALS blob for a known day, name for name. This
program has been burned twice by re-implementations that looked right and
were not (x39's harness-fidelity gate exists for exactly this), so the gate
runs first and the port ships only if it passes.

  python3 scripts/signals_fidelity_gate.py --brain ~/Projects/market-data-brain/daily

RESULT AS OF 2026-08-03 - the port is NOT wired in, because this gate FAILED:
  * indicator math is exact - 0 depth mismatches, 0 close mismatches, and
    0 false positives across every name the candidate flagged
  * but it found only 33 of the Mac's 89 TAKEs, and 26 of its 65 new-today
  * 38 of the 39 missing new-today signals are on names that are NOT vetted
    arms in SCAN -> THE LIVE SCAN UNIVERSE IS BROADER THAN THE VETTED SET,
    and its actual definition is not in this repo
  * the 1 remaining miss, DD/MFI, fired at mfi3 = 15.96 against a < 10
    threshold -> THE LIVE MFI THRESHOLD IS NOT 10. The research archive names
    the book "mfi3<20 -> ema7", which is consistent with 20.

So two facts are needed from the Mac before the port can be finished, and
neither can be derived from the dashboard alone:
  1. the live scan UNIVERSE rule (which names each arm scans)
  2. the exact entry THRESHOLDS per arm (MFI in particular)
Once those are recorded here, re-run this gate. Exact match -> wire it in.

EVIDENCE AS OF 2026-08-11 - the claim above that neither fact "can be derived
from the dashboard alone" turned out to be wrong once a second generator day
published (07-31 and 08-10, 390 SIGNALS rows on main). Derived and verified:

  * SIGNALS.depth IS the raw indicator value at trigger. Proof: the DD/MFI
    miss this gate measured at mfi3=15.96 appears in the published 07-31 blob
    as depth=15.96, exactly.
  * MFI THRESHOLD IS 20 (fact 2, MFI): highest MFI TAKE depth on record is
    19.84, lowest MFI WATCH is 20.18. RSI2 confirmed at 10 (9.88 vs 10.16).
    WATCH is an approach band, not a trigger state (age always 0, never a
    buy_date, never new_today): RSI2 watch band 10-15, MFI 20-30.
  * UNIVERSE (fact 1, partially): all 225 distinct signal names across both
    days are inside TRACK's 966 and 84 of them are NOT in SCAN's 445 - the
    live universe is a subset of the tracker list, not any SCAN-derived set.
  * The close>SMA200 gate is CONFIRMED live: on the 08-10 bar all 20 fresh
    RSI2 fires sat above their (split-adjusted, dividend-unadjusted) SMA200,
    and 44 of 66 TRACK names under RSI2 10 that did NOT fire sat at/below it,
    including five utilities (LNT CNP DTE AEP ED) that provably ARE in the
    universe (they fired on 07-31).
  * What remains of fact 1: 14 names failed to fire while robustly under
    RSI2 7 and clearly above SMA200 - they are simply not in the Mac's list:
      AAL ULCC ALK JBLU (airlines), BNL NTST XHR DRH KRG (small REITs),
      SCI OUT MQ GTX UNFI.
    Ask the Mac for the generator's ticker list and diff it against TRACK -
    that one diff, plus a --mfi-threshold 20 re-run of this gate, finishes
    the port. (8 more misses sat at RSI2 7-10 where cloud-vs-Mac vendor
    divergence can flip the threshold; they prove nothing either way.)

RUN 2026-08-14 - first execution against a brain cache (the repo mirror at
/workspace/market-data-brain/daily, 465 names through 2026-07-31), scored on
the 07-31 reference blob (commit c655cdf). Still FAILS, but the residue is
now small and understood:

    --universe vetted --mfi-threshold 10 : 34 cand, 51 missed,  1 FP
    --universe vetted --mfi-threshold 20 : 34 cand, 51 missed,  1 FP
    --universe brain  --mfi-threshold 20 : 94 cand, 13 missed,  6 FP
                                           (Mac: 110 TAKEs, 77 new-today)

  * THE UNIVERSE IS NOT THE VETTED SET. Widening the candidate pool to every
    brain name cut missed new-today from 51 to 13 - the single biggest step
    this gate has taken. Added as --universe brain so it is reproducible.
  * INDICATOR MATH REMAINS EXACT at the wider universe: 0 depth mismatches
    and 0 close mismatches across all 94 candidates. The arithmetic is not
    in question; only membership is.
  * ALL 13 RESIDUAL MISSES ARE MIRROR DATA GAPS, not logic: none of the 13
    (AHR ALLY HOG IVE IWN IWR JEF MLKN PRU RBA REXR RSP ...) has a 07-31 bar
    in this 465-name mirror. The Mac's brain is larger. They are not evidence
    of a rule difference.
  * EARNINGS IS NOT A GATE - HYPOTHESIS RAISED AND REFUTED IN THIS RUN. All
    6 false positives have earnings within 9 days of the bar, which looked
    decisive until the signalled set was checked: CHD, D, FRT, LIN and TROW
    all report ON 07-31 and are signalled anyway, carrying earnings_soon=true.
    The generator FLAGS earnings, it does not exclude on them. Do not add an
    earnings filter to a port on the strength of the false positives alone.
  * WHAT IS ACTUALLY LEFT: 6 false positives, i.e. names this gate flags that
    the Mac does not. Five (AIG CL CSX EG SW) are absent from SCAN entirely,
    consistent with a generator ticker list narrower than the brain. The sixth,
    AAPL/RSI2, is IN SCAN and vetted:true with n=67, sat at rsi2 3.53 well
    above its SMA200, was not held by any book, and still did not fire. AAPL
    is the one case no membership rule so far explains, and it is the thread
    to pull next.

The blocker is unchanged in kind but much narrower: the generator's exact
ticker list. Everything else about the rule is now pinned by evidence.

RESOLVED 2026-08-14, same session, an hour later - THE GENERATOR WAS NEVER
MISSING. The real script is scripts/signals.py in the strategy-lab-dashboard
repo (attached to the session all along), importing scan.py beside it. Read
in full, it settles every question this gate was built to answer:

  universe   = x26 snapshot names + every BRAIN/daily parquet, MINUS names
               the brain manifest flags (corrupt/flag/spliced/truncated)
  RSI2       TAKE rsi2<10, WATCH <15      (as evidenced)
  MFI        TAKE mfi3<20, WATCH <30      (as evidenced)
  ZSCORE     TAKE c>20 & av50>1e6 & z50<=-1.5 & rsi3<20 (second condition!)
  earnings   flags RSI2/MFI rows (earnings_soon), EXCLUDES only ZSCORE
             (state -> PASS-EARNINGS); window: next report within 4 days
  liquidity  av50>=300k AND $5M dollar-vol - added 7/31 after the SW
             ticker-splice leak (SW is named in the source comment)
  age        consecutive bars the FULL entry rule held; new_today = age==1

Then the REAL script was executed against this repo's brain mirror (data
through 07-31) and diffed name-for-name against the published 07-31 blob:

  147 rows generated vs the Mac's 189
  145 overlapping rows: ZERO mismatches across all seven fields
    (state, depth, close, age, buy_date, new_today, earnings_soon)
  44 missing rows, all on 33 symbols with NO parquet in the 08-01 mirror
    (the Mac's brain is larger; includes the x26/live-16 ETFs) - data
    availability, not logic
  2 extra rows, both AAPL: unflagged + clean in the mirror, emits TAKE
    here, absent from the Mac's blob. Only self-consistent explanation:
    AAPL was flagged/broken on the Mac ON 07-31 (the 7.4% earnings-gap
    session), excluded from that evening's run, repaired before the 08-01
    mirror push which carries the clean file. Input-snapshot difference,
    not a rule difference. Unprovable from here; ask the Mac.
  SW: correctly absent from BOTH runs - the earlier false positive was
    this gate's harness, not an unknown.

WIRED 2026-08-14, owner approval same day ("Do this for me you have my
permission"). scripts/signals_cloud.py carries the generator's math verbatim
with cloud loaders (Tradier bars / next-date earnings map / baked universe in
data/signals_universe.json), and the daily build now runs it fail-quiet
before the splices. The wiring fidelity test - the EXACT cloud code path,
410-bar truncated series and all, against the published 07-31 blob - scored
145/145 comparable rows with zero field mismatches; extras AAPL-only
(input-snapshot repair), misses all on mirror-absent names. Residual gap:
x26-side names beyond the 33 observed stay absent until market-data-brain
or the x26 snapshot is pushed current; on days the Mac generator also runs,
its fuller feed simply wins the publish race and the guard skips the cloud.

Standing consequence: the fidelity question is CLOSED up to data
availability. What a cloud refresh of SIGNALS now requires is not code or
facts but DATA: a current push of market-data-brain (its native basis is
already Tradier split-only - the same vendor the Actions build uses), plus
the x26 snapshot if the live-16 ETF names should keep appearing. Wiring the
real generator into the daily build is a process change to a live feed and
stays an owner decision.

INCIDENT 2026-08-14 (run #26, the first wired build): signals_cloud.py died
at import time - ModuleNotFoundError: numpy - because the Actions runner
has no numpy/pandas and the workflow deliberately has no pip step (every
other build script is stdlib-only; the wiring was only ever executed in a
sandbox that happened to have pandas). Fail-quiet behaved exactly as
designed: the step warned, SIGNALS stayed at its 08-11 publish, HEALTH
stamped signals_stale=true, and the page disclosed the stale feed. Fix:
signals_cloud.py rewritten as a pure-stdlib line-for-line port (explicit
loops for ewm/rolling/Wilder/MFI, None standing in for NaN with NaN
comparison semantics). Revalidated same day through this gate's standard
before replacing the pandas version: (a) byte-identical signals array vs
the pandas implementation's saved output on the same simulated 07-31
inputs, 147/147 rows, zero differences including order; (b) the wiring
fidelity test reproduced its exact verdict - overlap 145, field mismatches
0, extras AAPL-only, misses all mirror-absent - PASS. Lesson recorded:
validating runner-bound code requires the runner's import surface, not
just its data; stdlib-only is the build's contract, not a style choice.
NOTE: this gate script itself still imports pandas/numpy - it runs on the
Mac or in an analysis sandbox, never on the Actions runner.

CLEARED 2026-09-05 - the data gap this gate has carried since 08-03 is gone,
and the run is no longer a partial-credit comparison. The owner pushed
market-data-brain current (@5d8e644, 680 parquets through 2026-09-04, up from
the 465-name 08-01 mirror), so for the first time the cloud and the Mac can be
scored on the SAME corpus. Method: ran the real generator
(strategy-lab-dashboard/scripts/signals.py @e9700d9, X26 stubbed empty so it
scans brain names only) against that brain, then ran signals_cloud.py against
bars derived from the same parquets truncated to the cloud's 410-bar window,
with the re-baked 660-name universe. Result:

    mac rows 100 | cloud rows 100
    overlap 100 | field mismatches 0   (state/depth/close/as_of/age/
                                        buy_date/new_today/earnings_soon/
                                        stale_days/vehicle)
    cloud-only 0 | mac-only 0 | row ORDER identical | market_asof equal
    FIDELITY: PASS

No missing rows and no extras - the 08-14 run's 44 misses and 2 extras were
both artifacts of the stale mirror, not of the port. The 410-bar warm-up
delta remains below the 0.02 display rounding, now confirmed on 100 rows of
current data rather than 145 rows of 07-31 data.

Two parity repairs landed with this run. (1) market_asof was being taken as
the max as_of across EMITTED ROWS; the Mac takes it across every symbol the
scan processes. Identical on any normal day, but on a day when only frozen
names signal the row-only max equals the stale date and demote_stale would
demote nothing - the one input that could silently un-stale a dead ticker.
Now derived corpus-wide, matching signals.py. (2) The universe no longer
excludes inactive names. PR #78 dropped EA by hand; demote_stale (ported
08-14, exercised here on EA/EQR/WBS at -31/-18/-16 days) is the class fix, so
exclusion would now DIVERGE from the Mac by dropping rows it emits. Membership
is once again exactly the Mac's rule: brain parquets minus manifest-flagged
minus full-history len/continuity failures. 480 -> 660 names; observed_only is
empty for the first time.

Standing consequence: the fidelity question is now CLOSED outright, not "up to
data availability". Re-bake data/signals_universe.json on every brain push and
re-run this comparison; that is the whole maintenance contract.
"""
import argparse, glob, json, os, re
import numpy as np, pandas as pd


def frame(path):
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df[(df["volume"] > 0) & (df["close"] > 0)].set_index("date")
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 2, min_periods=2, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / 2, min_periods=2, adjust=False).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn)
    tp = (h + l + c) / 3.0
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0.0)
    neg = mf.where(tp < tp.shift(1), 0.0)
    f["mfi3"] = 100 * pos.rolling(3).sum() / (pos.rolling(3).sum() + neg.rolling(3).sum())
    f["sma200"] = c.rolling(200).mean()
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default=os.path.expanduser("~/Projects/market-data-brain/daily"))
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--rsi2-threshold", type=float, default=10.0)
    ap.add_argument("--universe", choices=("vetted", "brain"), default="vetted",
                    help="candidate set: SCAN-vetted arms, or every name in the brain")
    ap.add_argument("--mfi-threshold", type=float, default=20.0)  # evidenced 2026-08-11: TAKE max 19.84, WATCH min 20.18
    a = ap.parse_args()

    page = open(a.page).read()
    g = lambda n: json.loads(re.search(r"const %s = (.*?);\n" % n, page, re.S).group(1))
    SIG, SCAN = g("SIGNALS"), g("SCAN")
    as_of = max(x.get("as_of", "") for x in SIG["signals"])
    thr = {"RSI2": a.rsi2_threshold, "MFI": a.mfi_threshold}

    vetted = {arm: {s for s, v in SCAN["tickers"].items()
                    if (v.get("strats", {}).get(arm) or {}).get("vetted")}
              for arm in thr}
    # --universe brain scans every name the brain has, which the 08-14 run
    # showed is far closer to the generator's real list than the vetted set.
    if a.universe == "brain":
        allbrain = sorted(os.path.basename(p)[:-8]
                          for p in glob.glob(os.path.join(a.brain, "*.parquet")))
        cand = {arm: allbrain for arm in thr}
    else:
        cand = {arm: sorted(vetted[arm]) for arm in thr}
    mine = {}
    for arm, trig in (("RSI2", "rsi2"), ("MFI", "mfi3")):
        for s in cand[arm]:
            p = f"{a.brain}/{s}.parquet"
            if not os.path.exists(p):
                continue
            try:
                f = frame(p)
            except Exception:
                continue
            d = pd.Timestamp(as_of)
            if d not in f.index:
                continue
            r = f.loc[d]
            if np.isnan(r[trig]) or np.isnan(r["sma200"]):
                continue
            if r[trig] < thr[arm] and r["close"] > r["sma200"]:
                mine[(s, arm)] = {"depth": round(float(r[trig]), 2),
                                  "close": round(float(r["close"]), 2)}

    theirs = {(x["sym"], x["strat"]): x for x in SIG["signals"]
              if x["strat"] in thr and x["state"] == "TAKE"}
    new = {k for k, x in theirs.items() if x.get("new_today")}
    mk, tk = set(mine), set(theirs)
    both = mk & tk
    dmis = [k for k in both if abs(mine[k]["depth"] - (theirs[k]["depth"] or 0)) > 0.02]
    cmis = [k for k in both if abs(mine[k]["close"] - (theirs[k]["close"] or 0)) > 0.02]
    print(f"as_of {as_of}   thresholds RSI2<{thr['RSI2']} MFI<{thr['MFI']}")
    print(f"  candidate TAKEs {len(mk)}   Mac TAKEs {len(tk)}   Mac new-today {len(new)}")
    print(f"  false positives (mine, not Mac's): {len(mk - tk)}")
    print(f"  missed new-today                 : {len(new - mk)}")
    print(f"  depth mismatches / close mismatches: {len(dmis)} / {len(cmis)}")
    outside = [k for k in (new - mk) if k[0] not in vetted[k[1]]]
    print(f"  missed because NOT in the vetted universe: {len(outside)}")
    ok = (not (mk - tk)) and (not (new - mk)) and not dmis and not cmis
    print("VERDICT:", "PASS - safe to wire in" if ok else "FAIL - do not wire in")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
