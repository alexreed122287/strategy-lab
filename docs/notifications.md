# Daily new-buy notifications — email + phone push

After every green daily build, `scripts/notify_buys.py` reads the freshly
published page and sends the day's NEW BUYS — the same picks the Signals tab
ranks — by email and/or phone push. It runs automatically as the last step of
`daily_build.sh` and never fails the build. No credentials live in this repo,
ever: everything sits in one local config file you create on your Mac.

What a notification contains:
- **RANKED** — new vetted signals with 30+ trades (the Top-4 pool): ticker,
  book, entry timing (close vs next-open MOO), last close, strength, win %,
  avg/trade, sample size.
- **PAPER / RESEARCH** — z-score triggers (killed for real-money wiring; the
  paper forward test). Clearly labeled, stats at the ×0.71 executable estimate.
- BB never appears (book killed 2026-08-01).
- Exits pointer + dashboard link. Nothing in it places orders.

## 1) Create the config (one file, local only)

```bash
cat > ~/.strategy_lab_notify.json <<'EOF'
{
  "to": ["you@example.com", "buddy1@example.com", "buddy2@example.com"],
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_ssl": false,
  "smtp_user": "YOUR_GMAIL@gmail.com",
  "smtp_pass": "PASTE_APP_PASSWORD_HERE",
  "from": "YOUR_GMAIL@gmail.com",
  "ntfy_topic": "PICK_AN_UNGUESSABLE_TOPIC_NAME",
  "dashboard_url": "https://alexreed122287.github.io/strategy-lab/"
}
EOF
chmod 600 ~/.strategy_lab_notify.json
```

Omit what you don't want: no `to`/`smtp_host` → email off; no `ntfy_topic` →
push off. The file never leaves your machine and is never read by anything in
this repo except the notify script.

### Gmail note (the `smtp_pass`)
Use an **app password**, not your real password: Google Account → Security →
2-Step Verification → App passwords → generate for "Mail". Paste the 16-char
code as `smtp_pass`. Any other SMTP provider works the same way — set host,
port, and `"smtp_ssl": true` if your provider uses implicit TLS on port 465.

## 2) Phone push for you and your buddies (ntfy — free, no accounts)

1. Pick a topic name nobody could guess, e.g. `alex-slab-x9k24qzt` — the topic
   name IS the only secret (anyone who knows it can read and post to it).
2. Everyone installs the **ntfy** app (iOS/Android), taps + and subscribes to
   that topic. Done — pushes arrive after each green build.
3. Web fallback works too: `https://ntfy.sh/YOUR_TOPIC`.

## 3) Test the wiring

```bash
# see exactly what today's message looks like, sending nothing:
python3 ~/repos/strategy-lab-site/scripts/notify_buys.py \
  --page ~/repos/strategy-lab-site/index.html --dry-run

# send a real test through every configured channel:
python3 ~/repos/strategy-lab-site/scripts/notify_buys.py \
  --page ~/repos/strategy-lab-site/index.html --test
```

## 4) How it decides "new"

Buys = signals whose entry rule FIRST fired on the latest scanned bar (the
page's NEW flag) plus the book scanner's fresh TAKEs. A state file
(`~/.strategy_lab_notify_state.json`) remembers the last as-of date sent, so a
re-run of the build doesn't re-send; `--force` overrides. Days with no new
buys send nothing at all.

## Friends subscribe THEMSELVES (the alerts card on the Signals tab)

The dashboard has a "Daily buy alerts — subscribe yourself" card: friends type
an email address or a US mobile number and hit Subscribe (or Unsubscribe), and
the push section shows one-tap ntfy setup. No backend involved: the page posts
signup requests to a second unlisted ntfy topic, and your Mac harvests them
into `~/.strategy_lab_notify.json` automatically.

**Turn it on (one time):**

1. Pick TWO unguessable topic names — one for alerts, one for signups, e.g.
   `alex-slab-x9k24qzt` and `alex-slab-signup-p3m81vd`. Put the first in your
   config as `ntfy_topic` and the second as `signup_topic`.
2. Publish the topics into the page (run in your site clone, then push):

```bash
cd ~/repos/strategy-lab-site
python3 - <<'EOF'
import re
ALERTS  = "PUT_ALERTS_TOPIC_HERE"
SIGNUP  = "PUT_SIGNUP_TOPIC_HERE"
CONTACT = "your@email.com"   # fallback shown if the relay is unreachable
html = open("index.html").read()
line = ('const NOTIFY = {"ntfy_topic": "%s", "signup_topic": "%s", '
        '"owner_contact": "%s"};' % (ALERTS, SIGNUP, CONTACT))
html2, n = re.subn(r"const NOTIFY = .*?;", line, html, count=1)
assert n == 1
open("index.html", "w").write(html2)
print("NOTIFY set")
EOF
git add index.html && git commit -m "enable alert signups" && git push origin main
```

3. Install the harvester schedule (ntfy only retains messages ~12h, so it
   polls 4x daily; the nightly build also harvests right before sending):

```bash
cp scripts/com.alex.strategylab.signups.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.alex.strategylab.signups.plist
```

4. (Optional) enable TEXTS for phone signups — needs a Twilio account
   (~$1/mo number + ~$0.01/text). Add to the config:
   `"twilio_sid": "AC...", "twilio_token": "...", "twilio_from": "+1..."`.
   Until those exist, phone signups queue in `sms_to` and the nightly log
   reports how many are waiting; email and push work regardless.

**How requests flow:** page card → ntfy signup topic → `notify_signups.py`
(4x daily + at build) → `to` / `sms_to` lists in your local config →
`notify_buys.py` sends after each green build. Unsubscribes remove from both
lists. Lists cap at 200 entries as an abuse guard.

**Exposure to understand:** both topic names ship inside the public page, so
anyone with your dashboard URL can subscribe to the push topic, post junk
signups, or read signup messages during their ~12h relay retention (emails and
phone numbers are PII — friends should know they transit ntfy.sh). Your
dashboard link is the real secret. If a topic gets spammed, rotate both names
(step 1-2 again) — subscribers you already harvested are unaffected.

## Security notes

- Credentials: local file only, `chmod 600`, never committed — the repo's
  standing rule (keys live outside the repo) applies here too.
- ntfy topics are a public namespace protected only by obscurity — fine for
  buy alerts, wrong for anything sensitive. Rotate the topic name if it leaks.
- Recipients see backtest-derived decision support with basis labels intact;
  the email repeats that nothing places orders.

---

# The 12:30 digest — simplified daily email

A second, plain-language email: **the day's new buys, ranked, with the strategy
that fired and that name's own backtest record.** One screen, no jargon. Sent by
the same script with `--simple`, on its own schedule and its own recipient list.

## What it looks like

An **HTML table** with the dashboard Signals tab's own columns, in its own
top-to-bottom order (Strength descending):

| Ticker | Rank | State | New | Strategy | Exit | Vehicle | Strength | Win % | PF | Avg/trade % | Trades | PF 19-22 | PF 23-26 | Trigger | Earnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TROW | 1 | TAKE | NEW | RSI2 | close>SMA5 \| 10 bars | 1x | 0.94 | 71.7 | 2.86 | 1.15 | 46 | 2.71 | 3.05 | RSI2 8.19 | yes |
| ACGL | 2 | TAKE | NEW | MFI | close>EMA7 \| 10 bars | 1x | 0.91 | 83.1 | 3.44 | 1.01 | 89 | 4.68 | 2.27 | MFI 0.0 | |

Sent as `multipart/alternative`: HTML is the real deliverable (sixteen columns
cannot align in plain text without wrapping), with a monospace text fallback for
clients that refuse HTML. `EXITS` and `TRIGL` are ported verbatim from
`index.html` so the email and the Signals tab cannot drift apart.

Preview the HTML itself with `--dry-run --html`.

## Recipients

Add to `~/.strategy_lab_notify.json`. `to_digest` is optional and applies only to
`--simple`; without it the digest goes to the same `to` list as the full alert.

```json
{
  "to": ["alexander.s.reed@gmail.com"],
  "to_digest": ["alexander.s.reed@gmail.com",
                "jasoncolvin7.0@gmail.com",
                "ruizrk@yahoo.com"],
  "...": "smtp settings as above"
}
```

## Schedule

```bash
cp ~/repos/strategy-lab-site/scripts/com.alex.strategylab.digest.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.alex.strategylab.digest.plist
launchctl list | grep strategylab      # expect BOTH daily and digest
```

Preview without sending anything:

```bash
python3 ~/repos/strategy-lab-site/scripts/notify_buys.py \
  --page ~/repos/strategy-lab-site/index.html --simple --dry-run
```

The digest keeps its own dedupe state (`~/.strategy_lab_digest_state.json`), so
it never suppresses or is suppressed by the post-build alert, and it will not
re-send the same session's signals twice.

## Timing — resolved

**The digest sends after the build, not on a clock.** `daily_build.sh` calls it
as its last step, so it can never read a half-written page: the build has
finished and pushed by the time the digest runs. Signals confirm on the close,
the build runs 15:30, the digest goes out immediately after — recipients have the
whole evening to place market-on-open orders for the next open, which is exactly
the validated basis.

The 16:00 launchd job is a **backstop**, for the days the build's own digest step
fails. It cannot double-send: the digest keeps its own dedupe state keyed on the
signal date, so if the build already sent, the 16:00 run is a no-op.

An earlier draft scheduled this at 12:30, which would have been one full session
late for every strategy — the build hadn't run, so 12:30 carried the *previous*
close's signals whose fill window had already passed that morning. Recorded here
because the mistake is easy to repeat.
