#!/usr/bin/env bash
# Re-run the Z-Score book against the REFRESHED Tradier brain and publish the
# comparison. This is panel question 3, answered "yes, re-run" by the owner:
# the 68.5% headline was computed on Robinhood-basis data, and 215 of the 358
# names have since been re-fetched from Tradier (215/215, 2026-08-02).
#
#   cd ~/repos/strategy-lab-site && bash scripts/lab_zscore_rerun.sh
#
# Reads the live universe straight off the dashboard, runs the lab's own
# fillmode_sim unmodified, compares against data/x45v2_results.json, writes
# data/x45_tradier_rerun.json, and pushes it on its own branch. Places no
# trades. Needs no token - it only reads local parquets.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
BRANCH="lab/zscore-tradier-rerun-$(date +%Y%m%d-%H%M%S)"

BRAIN=""
for d in "$HOME/Projects/market-data-brain" "$HOME/repos/market-data-brain" \
         "$HOME/market-data-brain"; do
  [ -d "$d" ] && BRAIN="$d" && break
done
[ -z "$BRAIN" ] && { echo "market-data-brain not found"; exit 1; }
[ -f "$BRAIN/scripts/fillmode_sim.py" ] || { echo "fillmode_sim.py not in $BRAIN/scripts"; exit 1; }
echo "brain: $BRAIN"

BRAIN="$BRAIN" REPO="$REPO" python3 - <<'PY'
import json, os, re, sys
import numpy as np
brain, repo = os.environ["BRAIN"], os.environ["REPO"]
sys.path.insert(0, f"{brain}/scripts")
import fillmode_sim as fs
fs.BRAIN = brain

page = open(f"{repo}/index.html").read()
books = json.loads(re.search(r"const BOOKS = (.*?);\n", page, re.S).group(1))
z = next(s for s in books["strategies"] if s["id"] == "zscore_000")
want = z["universe"].get("mio_universe_live") or z["universe"].get("mio_universe_runnable")
have = {f[:-8] for f in os.listdir(f"{brain}/daily") if f.endswith(".parquet")}
uni = sorted(set(want) & have)
missing = sorted(set(want) - have)
print(f"universe: {len(uni)} of {len(want)} live names present in the brain")
if missing:
    print(f"  missing {len(missing)}: {', '.join(missing[:12])}{' ...' if len(missing) > 12 else ''}")
if len(uni) < 100:
    sys.exit("too few names present - did the Tradier re-fetch write into this brain?")

frames, cal, M = fs.matrices(uni)
EN = fs.entry_matrix(frames, cal, uni, "ZSCORE")
out = {"universe_n": len(uni), "missing": missing, "basis": "tradier-refreshed"}
out["ideal_close"] = fs.simulate(uni, cal, M, EN, "ideal_close")
print("ideal_close:", out["ideal_close"]["cagr"], "% | PF", out["ideal_close"]["pf"],
      "| trades", out["ideal_close"]["trades"], flush=True)
seeds = [fs.simulate(uni, cal, M, EN, "moc_full", seed=s, entry_cost=0.0005)
         for s in range(1, 6)]
out["moc_full_mean"] = round(float(np.mean([s["cagr"] for s in seeds])), 2)
out["moc_full_seeds"] = [s["cagr"] for s in seeds]
print("moc_full mean:", out["moc_full_mean"], "%", flush=True)

prior_path = f"{repo}/data/x45v2_results.json"
if os.path.exists(prior_path):
    prior = json.load(open(prior_path))
    out["prior_rh_basis"] = {"ideal_close": prior["ideal_close"]["cagr"],
                             "moc_full_mean": prior["moc_full_005"]["cagr_mean"],
                             "universe_n": prior["universe_n"]}
    d = out["ideal_close"]["cagr"] - prior["ideal_close"]["cagr"]
    out["delta_ideal_pp"] = round(d, 2)
    out["verdict"] = ("CONFIRMS the Robinhood-basis headline" if abs(d) <= 5
                      else "MATERIALLY DIFFERENT from the Robinhood-basis headline")
    print(f"\nprior (RH basis): {prior['ideal_close']['cagr']}%  ->  "
          f"now (Tradier): {out['ideal_close']['cagr']}%   delta {d:+.2f}pp")
    print("verdict:", out["verdict"])
json.dump(out, open(f"{repo}/data/x45_tradier_rerun.json", "w"), indent=1,
          default=lambda o: float(o) if isinstance(o, np.floating)
          else int(o) if isinstance(o, np.integer) else str(o))
print("\nwrote data/x45_tradier_rerun.json")
PY
rc=$?
[ $rc -ne 0 ] && { echo "sim failed (rc=$rc) - nothing committed"; exit $rc; }

cd "$REPO" || exit 1
if [ -n "$(git status --porcelain data/x45_tradier_rerun.json)" ]; then
  git checkout -B "$BRANCH" >/dev/null 2>&1
  git add data/x45_tradier_rerun.json
  git commit -q -m "z-score re-run on the refreshed Tradier brain (panel question 3)"
  git push -u origin "$BRANCH" >/dev/null 2>&1 && echo "pushed $BRANCH" \
    || echo "push failed - commit is local on $BRANCH"
  git checkout "$START_BRANCH" >/dev/null 2>&1 && echo "returned to $START_BRANCH"
else
  echo "no change to commit"
fi
echo
echo "Tell your Claude session: 'the z-score Tradier re-run is pushed'."
