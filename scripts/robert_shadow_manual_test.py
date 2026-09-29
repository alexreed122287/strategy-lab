#!/usr/bin/env python3
"""Manual-capture disclosure tests. Run: python3 scripts/robert_shadow_manual_test.py

Why this exists. On 2026-09-28 GitHub fired none of this repo's scheduled
workflows all morning, so ROBERT's queued TRGP entry was captured by a
hand-dispatched robert-entry-snap run (#60) at 13:38 ET. The quote is real, but
its `captured` stamp - 233 minutes after 09:45 - measures when a person clicked,
not how late the scheduled ladder runs, and the snap row cannot say so: the
store is frozen per key. robert_shadow.MANUAL_CAPTURES carries that provenance
instead and the page tags the row. These tests pin the two ways that goes wrong:
labelling a leg that was NOT priced from the manual quote, and a note that
points at no real capture.

JASON renders through the same helpers with its OWN map (jason_shadow.
MANUAL_CAPTURES, keyed against data/jason_chain_snaps.json). The two stores
share the TICKER|DATE|E format, so the third failure pinned here is bleed: a
scheduled JASON entry tagged because ROBERT's map holds the same key. These run
in CI only - jason_shadow_test.py runs inside both publishing builds, and a
disclosure test has no business being able to block a publish.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import robert_shadow as RS  # noqa: E402

KEY = "TRGP|2026-09-28|E"
ran, fails = [], []


def t(name, ok):
    print(("PASS - " if ok else "FAIL - ") + name)
    ran.append(name)
    if not ok:
        fails.append(name)


def chain(**kw):
    o = {"basis": "CHAIN", "captured_e": "2026-09-28 13:38 ET"}
    o.update(kw)
    return o


manual_open = {"t": "TRGP", "entry_date": "2026-09-28", "opt": chain()}

t("the hand-captured TRGP entry is tagged",
  "manual capture" in RS.manual_tag(manual_open))
note = RS.manual_note([manual_open])
t("the note names the leg, the date and the run that took it",
  "TRGP entry 2026-09-28" in note and "run #60" in note and "13:38 ET" in note)
t("the note says the timing is not the ladder's",
  "says nothing about how late the scheduled captures run" in note)

# A capture that failed falls back to the model; the key alone must not label it.
model_leg = dict(manual_open, opt={"basis": "MODEL"})
t("a MODEL-priced leg under the same key is not tagged",
  RS.manual_tag(model_leg) == "" and RS.manual_note([model_leg]) == "")
unstamped = dict(manual_open, opt=chain(captured_e=None))
t("a CHAIN leg without its capture stamp is not tagged",
  RS.manual_tag(unstamped) == "")

scheduled = {"t": "TRGP", "entry_date": "2026-09-15", "exit_date": "2026-09-18",
             "opt": chain(captured_e="2026-09-15 11:41 ET",
                          captured_x="2026-09-18 19:54 ET")}
t("a scheduled capture of the same ticker is not tagged",
  RS.manual_tag(scheduled) == "" and RS.manual_note([scheduled]) == "")

closed_later = dict(manual_open, exit_date="2026-09-30",
                    opt=chain(captured_x="2026-09-30 19:55 ET"))
cn = RS.manual_note([closed_later])
t("once closed, the row keeps its tag and only the manual leg is named",
  RS.manual_tag(closed_later) != "" and "TRGP entry 2026-09-28" in cn
  and " exit " not in cn)
t("the same row listed twice is named once",
  RS.manual_note([manual_open, closed_later]).count("TRGP entry 2026-09-28") == 1)

led = json.load(open(os.path.join(ROOT, "data", "robert_shadow.json")))
rows = led.get("open", []) + led.get("closed", [])
t("no row already in the ledger is retroactively labelled manual",
  all(RS.manual_tag(r) == "" for r in rows if r.get("entry_date") != "2026-09-28"))

store = json.load(open(os.path.join(ROOT, "data", "robert_chain_snaps.json")))
snaps = store.get("snaps", {})
t("every MANUAL_CAPTURES key is well formed",
  all(re.fullmatch(r"[A-Z.]+\|\d{4}-\d{2}-\d{2}\|[EX]", k)
      for k in RS.MANUAL_CAPTURES))
t("every MANUAL_CAPTURES key points at a real capture in the snap store",
  all(k in snaps for k in RS.MANUAL_CAPTURES))
t("the TRGP note agrees with the stored capture time",
  KEY in snaps and snaps[KEY].get("captured") == "2026-09-28 13:38 ET"
  and snaps[KEY].get("late_min") == 233)
t("no note text breaks the HTML it is dropped into",
  not any(c in v for v in RS.MANUAL_CAPTURES.values() for c in "<>&"))
t("an explicit empty map tags nothing, even ROBERT's own manual key",
  RS.manual_tag(manual_open, {}) == "" and RS.manual_note([manual_open], {}) == "")

# ------------------------------------------------------------------ JASON
import jason_shadow as JS  # noqa: E402


def jleg(**kw):
    o = {"expiry": "2026-11-20", "strike": 250.0, "basis": "CHAIN",
         "captured_e": "2026-09-28 13:38 ET", "prem_paid": 31.70, "contracts": 3}
    o.update(kw)
    return o


def jrender(open_rows, closed=()):
    marks = [dict(r, held=1, stock_ret=0.01, mark_mid=r["opt"]["prem_paid"],
                  contracts=r["opt"]["contracts"], ret=0.0, pnl=0.0)
             for r in open_rows]
    st = {"open": list(open_rows), "closed": list(closed), "queued": []}
    bk = {"n": len(closed), "net": 0.0, "meaningful": False,
          "win_pct": 100.0, "pf": None, "avg_ret": 0.0}
    return JS.render(st, bk, marks, "2026-09-29", [], 499, 503)


t("JASON keeps its own map, separate from ROBERT's",
  isinstance(JS.MANUAL_CAPTURES, dict) and JS.MANUAL_CAPTURES is not RS.MANUAL_CAPTURES)

# The exact key ROBERT marks manual, on a JASON row: must NOT be tagged.
bleed = {"t": "TRGP", "entry_date": "2026-09-28", "opt": jleg()}
html = jrender([bleed])
t("a JASON row sharing ROBERT's manual key is not tagged (no cross-book bleed)",
  "manual capture" not in html and "Captured by hand" not in html)

saved = JS.MANUAL_CAPTURES
try:
    JS.MANUAL_CAPTURES = {"CSCO|2026-09-29|E":
                          "jason-entry-snap run #99 at 12:00 ET, dispatched by hand (test)"}
    manual_j = {"t": "CSCO", "entry_date": "2026-09-29",
                "opt": jleg(strike=100.0, captured_e="2026-09-29 12:00 ET")}
    sched_j = {"t": "AMAT", "entry_date": "2026-09-29",
               "opt": jleg(strike=380.0, captured_e="2026-09-29 11:30 ET")}
    html = jrender([manual_j, sched_j])
    csco = re.search(r"<tr><td><b>CSCO</b>.*?</tr>", html).group(0)
    amat = re.search(r"<tr><td><b>AMAT</b>.*?</tr>", html).group(0)
    t("a key in JASON's own map tags that JASON row", "manual capture" in csco)
    t("...and only that row", "manual capture" not in amat)
    t("...with one note naming the leg and the run",
      html.count("Captured by hand") == 1 and "CSCO entry 2026-09-29" in html
      and "run #99" in html)
    closed_j = dict(manual_j, exit_date="2026-10-02", bars=3, reason="VAP", net=0.02,
                    opt=jleg(strike=100.0, captured_e="2026-09-29 12:00 ET",
                             exit_recv=33.0, ret=0.04, pnl=390.0))
    html = jrender([], [closed_j])
    t("the tag follows the JASON row into the closed table",
      "manual capture" in re.search(r"<tr><td><b>CSCO</b>.*?</tr>", html).group(0))
finally:
    JS.MANUAL_CAPTURES = saved

html = jrender([bleed])
t("with JASON's map empty the section carries no tag and no note",
  "manual capture" not in html and "Captured by hand" not in html)

jstore = json.load(open(os.path.join(ROOT, "data", "jason_chain_snaps.json")))
t("every JASON MANUAL_CAPTURES key points at a real capture in JASON's store",
  all(k in jstore.get("snaps", {}) for k in JS.MANUAL_CAPTURES))

# ------------------------------------------------ TRGP's corrected entry leg
# The Mac build of 2026-09-28 froze TRGP on the model beside its captured quote
# (the wrong-store bug below). On the owner's decision the leg was re-priced
# from that quote before any exit, keeping the replaced leg. Searched in open
# AND closed, so these hold for the life of the trade.
import robert_option_leg as OL  # noqa: E402

trgp = [r for r in led.get("open", []) + led.get("closed", [])
        if r.get("t") == "TRGP" and r.get("entry_date") == "2026-09-28"]
leg = (trgp[0].get("opt") or {}) if trgp else {}
want = OL.quote_leg(snaps[KEY])
t("TRGP's 09-28 entry is priced from its captured quote, as freeze_entry would",
  len(trgp) == 1 and all(leg.get(k) == want[k] for k in
                         ("basis", "expiry", "strike", "prem_mid", "prem_paid",
                          "contracts", "cost", "captured_e")))
was = (leg.get("corrected") or {}).get("was") or {}
t("the replaced model leg is kept in the ledger, not erased",
  was.get("basis") == "MODEL" and was.get("strike") == 260.0
  and was.get("prem_paid") == 24.7122)
t("the page note discloses the correction and what it replaced",
  "re-priced from this quote" in RS.MANUAL_CAPTURES[KEY]
  and "260C at 24.71" in RS.MANUAL_CAPTURES[KEY])
t("the corrected row carries the manual-capture tag",
  bool(trgp) and RS.manual_tag(trgp[0]) != "")

# ------------------------------------------------- which store the Mac reads
# A manual capture is only disclosed if the renderer reads the store it is in.
# On 2026-09-28 the Mac's build ran from $WORK (the dashboard repo) and read a
# relative default out of THAT repo - silently empty - so TRGP was frozen on
# the model beside its real quote. The default is now anchored to the script.
import subprocess  # noqa: E402

probe = subprocess.run(
    [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
     "import robert_shadow as RS; print(RS.SNAPS_PATH)", HERE],
    cwd="/", capture_output=True, text=True)
store = os.path.join(ROOT, "data", "robert_chain_snaps.json")
t("run from any directory, the default snap store is THIS repo's store",
  probe.returncode == 0 and os.path.realpath(probe.stdout.strip()) == os.path.realpath(store))
sh = open(os.path.join(HERE, "daily_build.sh")).read()
call = re.search(r'scripts/robert_shadow\.py".*?--splice', sh, re.S)
t("daily_build.sh hands robert_shadow the repo's store explicitly, as it does JASON",
  bool(call) and '--snaps "$REPO/data/robert_chain_snaps.json"' in call.group(0))

# Both halves of that bug, as invariants over the committed data. WRITE side:
# ASML's 2026-09-17 exit was priced from a real quote that the Mac then filed
# in the dashboard repo's stray store, so this ledger carried a CHAIN exit with
# no measurement behind it until the quote was recovered on 09-28. READ side:
# TRGP's 09-28 entry quote sat in this store while the build froze the leg on
# the model. Either one now fails CI on the next push to main.
for book, led_p, st_p in (("ROBERT", "robert_shadow.json", "robert_chain_snaps.json"),
                          ("JASON", "jason_shadow.json", "jason_chain_snaps.json")):
    bl = json.load(open(os.path.join(ROOT, "data", led_p)))
    bs = json.load(open(os.path.join(ROOT, "data", st_p))).get("snaps", {})
    brows = bl.get("open", []) + bl.get("closed", [])
    unfiled = []
    for r in brows:
        o = r.get("opt") or {}
        if o.get("basis") != "CHAIN":
            continue
        for side, day, cap, mid in (("E", "entry_date", "captured_e", "prem_mid"),
                                    ("X", "exit_date", "captured_x", "exit_mid")):
            if not o.get(cap):
                continue
            s = bs.get("%s|%s|%s" % (r["t"], r.get(day), side)) or {}
            if s.get("captured") != o[cap] or abs((s.get("mid") or 0) - (o.get(mid) or 0)) > 1e-9:
                unfiled.append("%s %s %s" % (r["t"], r.get(day), side))
    t(f"{book}: every quoted leg's quote is on file in {st_p} (same mid, same stamp)"
      + (f" - missing: {unfiled}" if unfiled else ""), not unfiled)
    unused = []
    for r in brows:
        k = "%s|%s|E" % (r["t"], r.get("entry_date"))
        if k in bs and (r.get("opt") or {}).get("captured_e") != bs[k].get("captured"):
            unused.append(k)
    t(f"{book}: every stored entry quote for a ledger row priced that row's leg"
      + (f" - on the model instead: {unused}" if unused else ""), not unused)

print()
if fails:
    sys.exit("FAILURES:\n  " + "\n  ".join(fails))
print(f"all {len(ran)} passed")
