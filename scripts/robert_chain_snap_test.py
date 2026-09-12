#!/usr/bin/env python3
"""Window tests for the entry snapshotter. Run: python3 scripts/robert_chain_snap_test.py

Why a whole-session window and not 09:30-11:30. The workflow's crons are
13:45/14:45 UTC (09:45 ET either side of DST), but GitHub's scheduler fired
them at 17:11-17:55 UTC on both 2026-09-10 and 2026-09-11 - over three hours
late. The two-hour window rejected every firing, the run reported success, and
the first live TAKE since the workflow was re-enabled (ATI, signalled on the
09-10 bar) was entered on a MODEL basis with no chain ever captured. A window
the scheduler cannot reach measures nothing. The frozen key, not the clock, is
what prevents a duplicate; the `captured` stamp on each row is what records
how far from 09:45 the quote actually was.
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robert_chain_snap as rcs  # noqa: E402

ET = ZoneInfo("America/New_York")


def at(wd_date, hh, mm):
    return dt.datetime.combine(wd_date, dt.time(hh, mm), tzinfo=ET)


FRI = dt.date(2026, 9, 11)   # weekday
SAT = dt.date(2026, 9, 12)
CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        print("FAIL -", msg)
        sys.exit(1)
    print("PASS -", msg)


# The drifted firings that actually happened, and must now be accepted.
check(rcs.in_entry_window(at(FRI, 13, 13)), "Fri 13:13 ET (the 09-11 17:13 UTC firing) is inside the window")
check(rcs.in_entry_window(at(FRI, 13, 55)), "Fri 13:55 ET (the 09-11 17:55 UTC firing) is inside the window")
# The intended moment and the old window's bounds still pass.
check(rcs.in_entry_window(at(FRI, 9, 45)), "Fri 09:45 ET (the spec moment) is inside the window")
check(rcs.in_entry_window(at(FRI, 9, 30)), "Fri 09:30 ET (open) is inside the window")
check(rcs.in_entry_window(at(FRI, 11, 30)), "Fri 11:30 ET (old upper bound) is still inside the window")
check(rcs.in_entry_window(at(FRI, 16, 0)), "Fri 16:00 ET (close) is inside the window")
# Pre-open, post-close and weekends stay out: an on-time 11:45 UTC cron is
# 07:45 ET and must be a harmless skip, not a pre-market quote.
check(not rcs.in_entry_window(at(FRI, 7, 45)), "Fri 07:45 ET (on-time 11:45 UTC cron) is outside")
check(not rcs.in_entry_window(at(FRI, 9, 29)), "Fri 09:29 ET is outside")
check(not rcs.in_entry_window(at(FRI, 16, 1)), "Fri 16:01 ET is outside")
check(not rcs.in_entry_window(at(SAT, 10, 0)), "Sat 10:00 ET is outside")

# Lateness is recorded as minutes after 09:45 so a row can be read without
# parsing its stamp; before the open it is 0, never negative.
check(rcs.late_minutes(at(FRI, 9, 45)) == 0, "09:45 ET is 0 minutes late")
check(rcs.late_minutes(at(FRI, 13, 55)) == 250, "13:55 ET is 250 minutes late")
check(rcs.late_minutes(at(FRI, 9, 30)) == 0, "09:30 ET clamps to 0, not -15")

print("all %d window tests passed" % CHECKS)
