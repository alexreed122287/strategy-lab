#!/usr/bin/env bash
# One command for everything that needs YOUR Mac.
#
# The cloud session that builds this dashboard has no path to your machine, and
# three open items need it: a Tradier token, the gap_widen_lab engine, and the
# local generator's arm definitions. This script does all three, commits the
# artifacts, and pushes them so the next session can pick up where it left off.
#
#   cd ~/path/to/strategy-lab && bash scripts/lab_mac_session.sh
#
# Safe to re-run. Every step is fail-soft: one step failing does not stop the
# others, and the summary at the end says exactly what landed and what did not.
# Nothing here places a trade, and no secret is ever written to the repo.

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/data/lab_collect"
mkdir -p "$OUT"
BRANCH="lab/mac-collect-$(date +%Y%m%d-%H%M%S)"   # unique per run: a re-run must not collide with an already-pushed branch
# daily_build.sh does `git pull --ff-only origin main` on step 0, so this script
# MUST hand the repo back on whatever branch it found it on.
START_BRANCH="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
STATUS=()
say(){ printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok(){  STATUS+=("OK   $1"); }
bad(){ STATUS+=("SKIP $1"); }

# ---------- locate the brain and the labs -----------------------------------
BRAIN=""
for d in "$HOME/Projects/market-data-brain" "$HOME/repos/market-data-brain" \
         "$HOME/market-data-brain"; do
  [ -d "$d" ] && BRAIN="$d" && break
done
# Honor a caller-supplied path FIRST - only search if none was given.
GWLAB="${GWLAB:-}"
if [ -n "$GWLAB" ] && [ ! -d "$GWLAB" ]; then
  echo "WARNING: GWLAB=$GWLAB does not exist - falling back to a search."
  GWLAB=""
fi
if [ -z "$GWLAB" ]; then
  for d in "$HOME/Projects/gapwiden-lab" "$HOME/repos/gapwiden-lab" \
           "$HOME/Projects/gap_widen_lab" "$HOME/repos/gap_widen_lab" \
           "$HOME/gap_widen_lab" "$HOME/repos/gap-widen-lab" \
           "$HOME/Projects/gap-widen-lab" "$HOME/Projects/gapwiden_lab" \
           "$HOME/repos/strategy-lab-dashboard/gap_widen_lab" \
           "$BRAIN/../gap_widen_lab"; do
    [ -n "$d" ] && [ -d "$d" ] && GWLAB="$(cd "$d" && pwd)" && break
  done
fi
# Last resort: look for the lab by its results signature.
if [ -z "$GWLAB" ]; then
  cand="$(find "$HOME/repos" "$HOME/Projects" -maxdepth 4 \
          \( -name "moc_results.json" -o -name "moo_results.json" \
             -o -name "VERDICT_gapwiden*" -o -name "gapwiden_lib.py" \) 2>/dev/null | head -1)"
  [ -n "$cand" ] && GWLAB="$(cd "$(dirname "$(dirname "$cand")")" && pwd)" && \
    echo "found a lab by its results signature: $GWLAB"
fi
echo "repo   : $REPO"
echo "brain  : ${BRAIN:-NOT FOUND}"
echo "gw lab : ${GWLAB:-NOT FOUND}"

# ---------- 1. Tradier re-fetch + earnings backfill -------------------------
say "1/3  Tradier re-fetch + earnings backfill (215 Robinhood-basis names)"
if [ -z "${TRADIER_TOKEN:-}" ]; then
  echo "TRADIER_TOKEN is not set in this shell - skipping."
  echo "  export TRADIER_TOKEN=...   then re-run (it is the same token daily_build.sh uses)"
  bad "Tradier re-fetch (no token in shell)"
elif [ -z "$BRAIN" ]; then
  echo "market-data-brain not found - skipping."
  bad "Tradier re-fetch (brain not found)"
else
  if python3 "$REPO/scripts/lab_refetch_new_names.py" \
       --brain "$BRAIN" \
       --names "$REPO/data/x45_rh_basis_names.json" \
       --earnings; then
    cp -f "$BRAIN/results/x45_tradier_refetch.json" "$OUT/" 2>/dev/null && \
      echo "copied refetch report -> data/lab_collect/"
    ok "Tradier re-fetch + earnings backfill"
  else
    bad "Tradier re-fetch (script returned non-zero)"
  fi
fi

# ---------- 2. Collect what resolves the Gap Widen RSI14 gap ----------------
say "2/3  Collect gap_widen_lab config (to resolve the RSI14 reproduction gap)"
if [ -z "$GWLAB" ]; then
  echo "gap_widen_lab not found in the usual places."
  echo "  Re-run with:  GWLAB=/path/to/gap_widen_lab bash scripts/lab_mac_session.sh"
  bad "GW lab collection (lab not found)"
else
  GWLAB="$GWLAB" OUT="$OUT" python3 - <<'PY'
import json, os, glob
lab, out = os.environ["GWLAB"], os.environ["OUT"]
SECRET = ("key", "token", "secret", "password", "passwd", "auth", "cred")
def clean(o):
    """Drop anything that smells like a credential before it touches the repo."""
    if isinstance(o, dict):
        return {k: ("<redacted>" if any(s in k.lower() for s in SECRET) else clean(v))
                for k, v in o.items()}
    if isinstance(o, list):
        return [clean(x) for x in o[:2000]]
    return o
col = {"lab_path": lab, "results": {}, "configs": {}, "listing": []}
for p in sorted(glob.glob(f"{lab}/**/*.json", recursive=True)):
    rel = os.path.relpath(p, lab)
    col["listing"].append(rel)
    if os.path.getsize(p) > 1_500_000:      # keep git history lean
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    tgt = "results" if "result" in rel.lower() else "configs"
    col[tgt][rel] = clean(d)
json.dump(col, open(f"{out}/gw_lab_config.json", "w"), indent=1, default=str)
n = len(col["results"]) + len(col["configs"])
json.dump(col, open(f"{out}/gw_lab_config.json", "w"), indent=1, default=str)
mb = os.path.getsize(f"{out}/gw_lab_config.json") / 1e6
print(f"collected {n} json files ({len(col['listing'])} seen) -> "
      f"data/lab_collect/gw_lab_config.json ({mb:.1f} MB)")
# surface the numbers the reproduction gap hinges on
for rel, d in list(col["results"].items()):
    s = json.dumps(d)
    if "51.6" in s or "rsi14" in rel.lower() or "moc" in rel.lower():
        print(f"  candidate: {rel}")
PY
  [ -f "$OUT/gw_lab_config.json" ] && ok "GW lab collection" || bad "GW lab collection"
fi

# ---------- 3. Collect the RSI2 / MFI generator arm definitions -------------
say "3/3  Collect the generator's RSI2 / MFI arm definitions (for the benchmark gate)"
GEN="${GEN:-}"
[ -n "$GEN" ] && [ ! -d "$GEN" ] && echo "WARNING: GEN=$GEN does not exist - searching." && GEN=""
[ -z "$GEN" ] && for d in "$HOME/Projects/agentic-cron" "$HOME/repos/agentic-cron" "$HOME/agentic-cron" \
         "$HOME/Projects/strategy-generator" "$HOME/repos/strategy-generator"; do
  [ -d "$d" ] && GEN="$(cd "$d" && pwd)" && break
done
if [ -z "$GEN" ]; then
  echo "generator not found in the usual places."
  echo "  Re-run with:  GEN=/path/to/your/generator bash scripts/lab_mac_session.sh"
  bad "generator arm specs (not found)"
else
  GEN="$GEN" OUT="$OUT" python3 - <<'PY'
import json, os, glob, re
gen, out = os.environ["GEN"], os.environ["OUT"]
SECRET = ("key", "token", "secret", "password", "passwd", "auth", "cred")
hits = {"generator_path": gen, "files": {}}
pat = re.compile(r"rsi\s*\(?\s*2|mfi|sma\s*\(?\s*5|ema\s*\(?\s*7", re.I)
for p in sorted(glob.glob(f"{gen}/**/*.*", recursive=True)):
    if os.path.splitext(p)[1].lower() not in (".py", ".json", ".yaml", ".yml", ".toml"):
        continue
    if os.path.getsize(p) > 400_000:
        continue
    try:
        t = open(p, errors="ignore").read()
    except Exception:
        continue
    if not pat.search(t):
        continue
    # Redact credential-bearing LINES, keep the rest - withholding the whole
    # file would throw away the arm definition we are here to collect.
    keep, redacted = [], 0
    for line in t.splitlines():
        low = line.lower()
        if any(s in low for s in ("api_key", "apikey", "secret", "token", "password",
                                  "bearer ", "passwd")) and ("=" in line or ":" in line):
            keep.append("<redacted credential line>")
            redacted += 1
        else:
            keep.append(line)
    if redacted:
        print(f"   redacted {redacted} credential line(s) in {os.path.relpath(p, gen)}")
    hits["files"][os.path.relpath(p, gen)] = "\n".join(keep)[:60_000]
json.dump(hits, open(f"{out}/generator_arm_specs.json", "w"), indent=1)
print(f"collected {len(hits['files'])} candidate files -> data/lab_collect/generator_arm_specs.json")
for k in list(hits["files"])[:12]:
    print("  ", k)
PY
  [ -f "$OUT/generator_arm_specs.json" ] && ok "generator arm specs" || bad "generator arm specs"
fi

# ---------- commit + push ---------------------------------------------------
say "Committing artifacts"
cd "$REPO" || exit 1
if [ -n "$(git status --porcelain data/lab_collect 2>/dev/null)" ]; then
  git checkout -B "$BRANCH" >/dev/null 2>&1
  git add data/lab_collect
  git commit -q -m "lab collect $(date +%Y-%m-%d): Tradier re-fetch report, GW lab config, generator arm specs

Produced by scripts/lab_mac_session.sh on the Mac - the three items the cloud
session cannot reach. Credentials are redacted by the collector."
  if git push -u origin "$BRANCH" >/dev/null 2>&1; then
    ok "pushed branch $BRANCH"
  else
    bad "push failed - commit is local on $BRANCH"
  fi
  # hand the repo back where we found it, or the nightly build breaks
  if git checkout "$START_BRANCH" >/dev/null 2>&1; then
    echo "returned to branch $START_BRANCH"
  else
    echo "WARNING: could not return to $START_BRANCH - you are on $BRANCH."
    echo "         run: git checkout $START_BRANCH   before tonight's build"
  fi
else
  echo "nothing new to commit."
fi

# ---------- summary ---------------------------------------------------------
say "Summary"
printf '  %s\n' "${STATUS[@]}"
cat <<TXT

Next: tell your Claude session "the lab collect branch is pushed" and it will
  - reconcile the Gap Widen RSI14 reproduction gap against the real lab config,
  - run the benchmark gate (book vs buy-and-hold of its own universe) for the
    RSI2 and MFI books using the arm definitions collected here,
  - and re-run the z-score sim against the refreshed Tradier data, replacing the
    Robinhood-basis numbers on the dashboard.

Nothing in this script trades, and your token never leaves your shell.
TXT
