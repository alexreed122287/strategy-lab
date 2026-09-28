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

print()
if fails:
    sys.exit("FAILURES:\n  " + "\n  ".join(fails))
print(f"all {len(ran)} passed")
