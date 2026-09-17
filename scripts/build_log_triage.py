#!/usr/bin/env python3
"""Triage .daily_build.log: why did a build not publish?

Written 2026-09-17. The Mac's last published build was 2026-09-04 20:43 - every
index.html since carries a "cloud generator" stamp - against a launchd schedule
of weekdays 15:30. Nothing in the repo records why, because daily_build.sh
writes its whole story to .daily_build.log, which is gitignored and never
leaves that machine. So the question "which step is failing" could only be
answered by reading a log by eye, and the answer sits under a few hundred lines
of normal output.

This reads that log and answers the one fork that matters first:

  DID THE JOB EVEN RUN?  daily_build.sh redirects into the log only AFTER it
  starts, so a launchd failure to start - wrong path, not executable, no bash -
  writes nothing here at all and looks identical to a night that went fine and
  quiet. A weekday with no "=== daily build start" line did not fail; it never
  ran, and the evidence is in /tmp/strategylab.daily.err instead (the plist
  points StandardErrorPath there for exactly this case). Pass --err to read it.

  IF IT RAN, WHERE DID IT STOP?  The script is `set -euo pipefail` and
  fail-closed by design, so most deaths print no verdict of their own - the
  last line before the log goes quiet names the step. Where the script DOES
  refuse deliberately it says so in a fixed phrase, and those are recognised
  below and reported as themselves rather than as "died after <line>".

Nothing here fixes anything. It turns "read the log" into a verdict per run.

Usage
  python3 scripts/build_log_triage.py [--log ~/repos/strategy-lab-site/.daily_build.log]
      [--err /tmp/strategylab.daily.err] [--runs 10]
"""

import datetime as dt
import os
import re
import sys

START = re.compile(r"^=== daily build start (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ===")
DONE = re.compile(r"^=== daily build done (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ===")

# Every phrase daily_build.sh prints when it refuses or degrades on purpose.
# Ordered most-fatal first: a run that hit the render gate AND had a pull
# warning stopped at the render gate, and that is the line worth reporting.
FATAL = [
    ("PUSH FAILED after 5 attempts",
     "push rejected 5x - page NOT published and all mail deliberately held"),
    ("RENDER GATE FAILED",
     "smoke suite assertions failed - refused to publish an unverified page"),
    ("RENDER GATE UNAVAILABLE",
     "playwright not installed - refused rather than treat a missing dep as a pass"),
    ("RENDER GATE SKIPPED - node not on PATH",
     "node not on PATH under launchd - refused for the same reason"),
]
# Non-fatal by design, but each one silently narrows what the build produced,
# so a run can look green and still not have refreshed what you assume.
DEGRADED = [
    ("WARNING: pull failed",
     "clone was dirty or diverged - built on local state, push likely to fail"),
    ("blob rebuild FAILED",
     "TRACK-only: SCAN/SIGNALS/BASKETS/REGIME kept their PREVIOUS values"),
    ("blob rebuild not configured",
     "TRACK-only: no SL_BLOB_BUILD_CMD / ~/.strategy_lab_build_cmd"),
    ("jason earnings seed refresh failed",
     "JASON hold gate ran on the committed seed, not a fresh one"),
]


def runs_from(lines):
    """[(start_dt, body_lines, done_dt_or_None)] in log order."""
    out, cur = [], None
    for ln in lines:
        m = START.match(ln)
        if m:
            if cur:
                out.append(cur)
            cur = [dt.datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %H:%M:%S"), [], None]
            continue
        if cur is None:
            continue          # preamble from before the first start line
        d = DONE.match(ln)
        if d:
            cur[2] = dt.datetime.strptime(" ".join(d.groups()), "%Y-%m-%d %H:%M:%S")
        cur[1].append(ln)
    if cur:
        out.append(cur)
    return out


def verdict(body, done):
    """(tag, detail) for one run. Deliberate refusals beat 'died after X'."""
    text = "\n".join(body)
    for needle, why in FATAL:
        if needle in text:
            return "REFUSED", why
    if done is None:
        tail = [l.rstrip() for l in body if l.strip()]
        last = tail[-1] if tail else "(no output at all)"
        return "DIED", "no 'done' line; last output was: " + last[:160]
    if "no changes to publish" in text:
        return "NO-OP", "ran clean to the end, but nothing had changed to commit"
    return "PUBLISHED", "ran to completion and pushed"


def weekdays_in(first, last):
    """Every weekday in [first, last]. A weekday absent from the log's runs did
    not fail - it never started, which is a different investigation."""
    d, out = first, []
    while d <= last:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def main():
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    log = os.path.expanduser(opt("--log", "~/repos/strategy-lab-site/.daily_build.log"))
    err = os.path.expanduser(opt("--err", "/tmp/strategylab.daily.err"))
    show = int(opt("--runs", "10"))

    if not os.path.exists(log):
        print("no log at %s" % log)
        print("If this is the Mac, the build has never started here - check the")
        print("plist is loaded: launchctl list | grep strategylab")
        return 2
    lines = open(log, errors="replace").read().splitlines()
    runs = runs_from(lines)
    if not runs:
        print("%s holds %d line%s but no '=== daily build start' marker."
              % (log, len(lines), "" if len(lines) == 1 else "s"))
        print("The script never got as far as its own banner. Check %s." % err)
        return 2

    print("log: %s  (%d line%s, %d run%s)"
          % (log, len(lines), "" if len(lines) == 1 else "s",
             len(runs), "" if len(runs) == 1 else "s"))
    print()
    print("%-19s  %-9s  %s" % ("RUN STARTED", "VERDICT", "WHAT HAPPENED"))
    print("-" * 100)
    for start, body, done in runs[-show:]:
        tag, why = verdict(body, done)
        print("%-19s  %-9s  %s" % (start.strftime("%Y-%m-%d %H:%M:%S"), tag, why))
        for needle, note in DEGRADED:
            if needle in "\n".join(body):
                print("%-19s  %-9s  ^ also: %s" % ("", "", note))
    print()

    # The decisive fork: a weekday with no run at all did not fail, it never
    # started, and no amount of reading this log will explain it.
    ran = {r[0].date() for r in runs}
    today = dt.date.today()
    # Stop at yesterday. Today's 15:30 run may simply not have fired yet, and
    # reporting it as missing at 09:00 would cry wolf every single morning.
    span = weekdays_in(min(ran), today - dt.timedelta(days=1))
    missing = [d for d in span if d not in ran]
    last_run = max(ran)
    print("last run started : %s (%d day%s ago)"
          % (last_run, (today - last_run).days,
             "" if (today - last_run).days == 1 else "s"))
    published = [r for r in runs if verdict(r[1], r[2])[0] == "PUBLISHED"]
    if published:
        print("last PUBLISHED   : %s" % max(r[0].date() for r in published))
    else:
        print("last PUBLISHED   : none in this log")
    if missing:
        print()
        print("WEEKDAYS WITH NO RUN AT ALL (%d): %s"
              % (len(missing), ", ".join(str(d) for d in missing[-15:])))
        print("  These did not fail - the script never reached its own banner, so")
        print("  nothing about them is in this file. Look at:")
        print("    tail -40 %s" % err)
        print("    launchctl list | grep strategylab")
        print("    launchctl print gui/$(id -u)/com.alex.strategylab.daily")
    else:
        print()
        print("Every weekday in range has a run - the job fires; the failures")
        print("above are the script's own, and the VERDICT column names them.")

    if os.path.exists(err) and os.path.getsize(err):
        print()
        print("--- last 12 lines of %s (launchd's own stderr) ---" % err)
        for l in open(err, errors="replace").read().splitlines()[-12:]:
            print("  " + l)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Piping into `head` closes the pipe early. That is the caller reading
        # the first few lines on purpose, not a failure, and a traceback here
        # would look exactly like the thing this script exists to diagnose.
        os._exit(0)
