#!/usr/bin/env python3
"""Harvest self-service alert signups from the page's ntfy signup topic into
the local notify config - the bridge that makes the dashboard's "subscribe
yourself" card work with zero backend.

Flow: the public page POSTs {action, kind, value} JSON messages to an unlisted
ntfy.sh topic. This script polls that topic's JSON feed and applies the
requests to ~/.strategy_lab_notify.json:
    kind=email -> the "to" list          (daily email recipients)
    kind=phone -> the "sms_to" list      (texts send once Twilio keys exist)
    action=add / remove                  (remove works on either list)

ntfy.sh retains messages ~12 hours, so run this several times a day (launchd
template: scripts/com.alex.strategylab.signups.plist, 4x daily) plus at build
time from daily_build.sh. Processing is idempotent - re-reading old messages
is harmless.

Usage:
  python3 notify_signups.py [--config ~/.strategy_lab_notify.json]
      [--topic SIGNUP_TOPIC] [--test-file signups.ndjson] [--max 200]
The topic comes from --topic or the config's "signup_topic" key. Fail-quiet:
no topic / network trouble prints a note and exits 0 so builds never break.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+1\d{10}$")


def clean(kind, value):
    v = str(value or "").strip()
    if kind == "email" and EMAIL_RE.match(v) and len(v) <= 120:
        return v.lower()
    if kind == "phone":
        d = re.sub(r"\D", "", v)
        if len(d) == 10:
            return "+1" + d
        if len(d) == 11 and d.startswith("1"):
            return "+" + d
    return None


def fetch_messages(topic):
    url = "https://ntfy.sh/%s/json?poll=1" % urllib.parse.quote(topic)
    req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace").splitlines()


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    cfg_path = os.path.expanduser(opt("--config", "~/.strategy_lab_notify.json"))
    cap = int(opt("--max", "200"))
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path))
        except Exception as e:
            sys.exit("signups: config unreadable (%r) - refusing to overwrite" % e)
    topic = opt("--topic") or cfg.get("signup_topic")
    test_file = opt("--test-file")
    if not topic and not test_file:
        print("signups: no signup_topic configured - nothing to harvest")
        return
    try:
        lines = (open(test_file).read().splitlines() if test_file
                 else fetch_messages(topic))
    except Exception as e:
        print("signups: poll failed (non-fatal): %r" % e)
        return

    to = list(cfg.get("to") or [])
    sms = list(cfg.get("sms_to") or [])
    added, removed, skipped = [], [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            skipped += 1
            continue
        if ev.get("event") not in (None, "message"):
            continue
        raw = ev.get("message", line if test_file else "")
        try:
            req = json.loads(raw)
        except Exception:
            skipped += 1
            continue
        action = req.get("action")
        val = clean(req.get("kind"), req.get("value"))
        if action not in ("add", "remove") or not val:
            skipped += 1
            continue
        target = to if "@" in val else sms
        if action == "add":
            if val not in target:
                if len(target) >= cap:
                    print("signups: list cap %d reached - ignoring %s" % (cap, val))
                    continue
                target.append(val)
                added.append(val)
        else:
            if val in to:
                to.remove(val); removed.append(val)
            if val in sms:
                sms.remove(val); removed.append(val)

    if added or removed:
        cfg["to"], cfg["sms_to"] = to, sms
        tmp = cfg_path + ".tmp"
        json.dump(cfg, open(tmp, "w"), indent=1)
        os.replace(tmp, cfg_path)
        try:
            os.chmod(cfg_path, 0o600)
        except Exception:
            pass
    print("signups: +%d added %s | -%d removed %s | %d skipped | now %d email, %d sms"
          % (len(added), added, len(removed), removed, skipped, len(to), len(sms)))


if __name__ == "__main__":
    main()
