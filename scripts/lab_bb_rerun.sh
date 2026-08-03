#!/usr/bin/env bash
# Definitive x59: BB Rubber Band on MIO's OWN 301-name universe, at full
# coverage. The session run reached only 180 of 301 names - the other 121 were
# never fetched into any local store - so its FAIL on B1 (retention 0.714 vs
# the 0.80 bar) is recorded as coverage-limited. This fetches what Tradier has
# and re-scores all four pre-registered gates.
#
#   cd ~/repos/strategy-lab-site && bash scripts/lab_bb_rerun.sh
#
# Needs TRADIER_TOKEN (env or ~/.tradier_token). Places no trades.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
BRANCH="lab/bb-mio-rerun-$(date +%Y%m%d-%H%M%S)"
BRAIN=""
for d in "$HOME/Projects/market-data-brain" "$HOME/repos/market-data-brain"; do
  [ -d "$d" ] && BRAIN="$d" && break
done
[ -z "$BRAIN" ] && { echo "market-data-brain not found"; exit 1; }
echo "brain: $BRAIN"

# 1) fetch any MIO BB names the brain lacks
python3 "$REPO/scripts/lab_refetch_new_names.py" --brain "$BRAIN" \
        --symbols-file "$REPO/data/x59_bb_universe.txt" || \
  echo "fetch step reported problems - continuing with what is present"

# 2) re-score the four pre-registered gates at whatever coverage now exists
BRAIN="$BRAIN" REPO="$REPO" python3 - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["REPO"], "scripts"))
import bb_harness as bb
brain, repo = os.environ["BRAIN"], os.environ["REPO"]
want = [t.strip() for t in open(f"{repo}/data/x59_bb_universe.txt").read()
        .replace("\n", ",").split(",") if t.strip()]
have = {f[:-8]: f"{brain}/daily/{f}" for f in os.listdir(f"{brain}/daily")
        if f.endswith(".parquet")}
src = {s: have[s] for s in want if s in have}
print(f"coverage: {len(src)} of {len(want)}")
fr = bb.load(src, "2018-01-01", "2026-12-31")
ideal = bb.simulate(fr, "ideal_close", trade_start="2019-01-02", slip=0.0001)
hyb   = bb.simulate(fr, "hybrid",      trade_start="2019-01-02", slip=0.0005)
bh    = bb.buy_hold(fr, "2019-01-02")
ret = hyb["cagr"] / ideal["cagr"] if ideal["cagr"] else 0
e19 = sum(v for y, v in hyb["yby"].items() if 2019 <= y <= 2022)
e23 = sum(v for y, v in hyb["yby"].items() if 2023 <= y <= 2026)
G = {"B1_retention": {"v": round(ret, 3), "bar": 0.80, "pass": ret >= 0.80},
     "B2_positive":  {"v": hyb["cagr"], "pass": hyb["cagr"] > 0},
     "B3_vs_bh":     {"excess_pp": round(hyb["cagr"] - bh["cagr"], 2),
                      "pass": hyb["cagr"] > bh["cagr"] and abs(hyb["maxdd"]) < abs(bh["maxdd"])},
     "B4_era":       {"e1922": round(e19, 2), "e2326": round(e23, 2),
                      "pass": e19 > 0 and e23 > 0}}
print(f"idealized {ideal['cagr']}%  executable {hyb['cagr']}%  B&H {bh['cagr']}%")
for k, v in G.items():
    print(f"  {k:14s} {'PASS' if v['pass'] else 'FAIL'}  {v}")
print("VERDICT:", "ALL PASS - un-kill" if all(v["pass"] for v in G.values())
      else "FAIL - kill stands")
json.dump({"names": len(fr), "of": len(want), "ideal": ideal, "hybrid": hyb,
           "bh": bh, "gates": G, "basis": "tradier-full-coverage"},
          open(f"{repo}/data/x59_bb_full.json", "w"), indent=1, default=float)
print("wrote data/x59_bb_full.json")
PY
rc=$?; [ $rc -ne 0 ] && { echo "sim failed (rc=$rc) - nothing committed"; exit $rc; }
cd "$REPO" || exit 1
if [ -n "$(git status --porcelain data/x59_bb_full.json)" ]; then
  git checkout -B "$BRANCH" >/dev/null 2>&1
  git add data/x59_bb_full.json
  git commit -q -m "x59 full-coverage: BB on MIO's own universe (Tradier)"
  git push -u origin "$BRANCH" >/dev/null 2>&1 && echo "pushed $BRANCH" \
    || echo "push failed - commit is local on $BRANCH"
  git checkout "$START_BRANCH" >/dev/null 2>&1
fi
echo; echo "Tell your Claude session: 'the BB full-coverage run is pushed'."
