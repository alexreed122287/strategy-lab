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

## Security notes

- Credentials: local file only, `chmod 600`, never committed — the repo's
  standing rule (keys live outside the repo) applies here too.
- ntfy topics are a public namespace protected only by obscurity — fine for
  buy alerts, wrong for anything sensitive. Rotate the topic name if it leaks.
- Recipients see backtest-derived decision support with basis labels intact;
  the email repeats that nothing places orders.
