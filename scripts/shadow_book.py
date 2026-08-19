#!/usr/bin/env python3
"""Shadow forward book - the automated paper ledger.

The program's law: the forward record is the one dataset no backtest can
substitute, and every book owes 20 closed paper trades ("Forward n>=20" on the
Evidence Parity matrix). This script keeps that record WITHOUT relying on
manual logging: each nightly build it

  1. FILLS market-on-open entries queued at the previous build (Gap Widen and
     Z-Score paper signals fill at the NEXT session's open - their validated
     basis) using the fresh bars,
  2. EVALUATES every open position against its book's exact exit rule on the
     newest bar (rsi2>80 / rsi14>60 for GW, close>EMA5 + earnings force-exit
     for Z, close>SMA5 for RSI2, close>EMA7 for MFI, 10-bar time stop for all)
     and closes at that bar's close (the MOC print),
  3. QUEUES/OPENS today's qualifying signals: every Gap Widen and Z-Score TAKE
     from BOOKSIG (queued for tomorrow's open), and every fresh vetted 30+
     RSI2/MFI TAKE from SIGNALS (opened at the signal close - their validated
     basis). One position per (book, symbol).

Friction: GW nets 0.05%/side (the validated auction assumption), Z nets
0.02pp round trip; RSI2/MFI close prints are recorded gross and labeled.
The manual Positions book remains for REAL fills; this ledger is the
skip-free evidence machine.

State: data/shadow_book.json (committed by the daily build, so the record
survives machines). Output: `const SHADOW = ...;` spliced into the page.

Usage:
  python3 shadow_book.py --bars bars.json --page index.html
      [--earnings earnings.json] [--ledger data/shadow_book.json] [--splice]
"""
import datetime
import json
import os
import re
import sys

FRICTION_RT = {"GAPW_RSI2": 0.001, "GAPW_RSI14": 0.001, "ZSCORE": 0.0002,
               "RSI2": 0.0, "MFI": 0.0}
# ENTRY BASIS. Everything is MOO as of 2026-08-03.
#
# RSI2 and MFI were "close" - their validated basis is a fill at the signal
# close. But the signal is only known AT that close, and the daily build runs
# after it: the buy email lands ~15:50 CT. Recording a close fill the owner
# could not have obtained inflates the forward record on the two books that
# fire most often, and that record is what gates real money. Measured cost of
# waiting for the next open, same universes and window as the benchmark gate:
#
#   MFI   MOC 59.50% -> MOO 50.48%   -9.02pp   retention 0.848
#   RSI2  MOC 39.93% -> MOO 34.22%   -5.71pp   retention 0.857
#
# So the honest record is ~15% below the backtest on both, and that is what
# this now stores. Changed with ONE closed trade on the books (KRE/MFI, entered
# at a close) - disclosed rather than back-dated, since a pure replay of entries
# is not possible from the ledger alone.
#
# This is reversible: if the intraday 3:45 send is built and actually used,
# close fills become achievable and RSI2/MFI move back to "close" - which must
# itself be pre-registered before the trades it would affect.
#
# 2026-08-18: the owner set the Z-SCORE TARGET basis to a 2:45pm CST (3:45pm
# ET) threshold filled MOC - the x43 basis, retention 0.87, co-signed by the
# x57 panel - and index.html now discounts every displayed z-score stat to it.
# ZSCORE IS DELIBERATELY LEFT AT "moo" HERE ANYWAY, for the reason the
# paragraph above exists:
#
#   * The send does not exist. daily_build.sh fires at 15:30 CT (see
#     com.alex.strategylab.daily.plist), forty-five minutes AFTER the decision
#     point. Nothing in this repo can tell anyone at 2:45 what to buy, so a
#     "moc" fill here would record a price the owner could not have obtained -
#     which is precisely the inflation this basis map was introduced to stop.
#   * The paragraph above requires a basis change to be PRE-REGISTERED before
#     the trades it affects. Flipping it silently, mid-record, on a live
#     forward test that gates real money, would be the opposite.
#
# So the displayed expectancy is currently the TARGET basis while the forward
# record is the ACHIEVED one, and both surfaces say so out loud. To close the
# gap, build the intraday send first, then pre-register, then flip this to
# "moc" and set ZEXEC.mechanism_built = true in index.html.
BASIS = {"GAPW_RSI2": "moo", "GAPW_RSI14": "moo", "ZSCORE": "moo",
         "RSI2": "moo", "MFI": "moo"}
BASIS_PRIOR = {"RSI2": "close", "MFI": "close"}

# ---------------------------------------------------------------- capital model
# The per-trade ledger above answers "is the signal edge real" (the Evidence
# Parity "Forward n>=20" gate). It deliberately takes EVERY signal, so it can
# hold 37 positions at once - which no $100k account could. This layer replays
# the same ledger through an account that CAN be traded, so the forward record
# can also be compared to the books' backtest CAGRs.
#
# Modeling choices (explicit, and not themselves validated by any lab run):
#   - one shared $100,000 paper account, the program's standing paper balance
#   - split into equal sleeves per book so no book can crowd out another; each
#     book then applies its own slot count inside its sleeve, preserving the
#     mechanics each book was validated with (z-score is spec'd at 3 slots)
#   - position size = sleeve equity / slots, capped by sleeve cash
#   - a signal arriving with no free slot or no cash is SKIPPED AND RECORDED -
#     the skip count is the honest cost of a real account and must be visible
#
# GATE BASIS (owner decision, pre-registered 2026-08-03, BEFORE any trade
# closed): the binding real-money gate counts trades THIS ACCOUNT actually
# took - 20 closed account trades, program-wide - not the skip-free per-book
# ledger. The account is what real money would have done; the ledger measures
# whether a rule fires, which is a different question. Both counts are
# published; only the account count opens the gate.
CAPITAL = 100_000.0
# OWNER DECISION 2026-08-03, taken while the account had ZERO closed trades - the
# only honest moment to change a capital model, and the same reason the gate basis
# was fixed the same day. The account holds ONE position per book: each book's own
# #1-ranked signal by its own ranking rule (Gap Widen by rs252, Z-Score by rsi3),
# so nothing is hand-picked across books. Friday's scan resolves to JBLU
# (GAPW_RSI2), BEN (GAPW_RSI14) and KNX (ZSCORE), plus one each for RSI2/MFI.
#
# CORRECTED same day, before any trade closed: the concurrency cap and the
# position-SIZE divisor were briefly the same number, which silently tripled
# per-name risk when slots went 3 -> 1. They are separate concepts and are now
# separate constants:
#   SLOTS        - how many positions a book may hold at once (owner: 1)
#   SIZE_DIVISOR - the validated sizing denominator, unchanged at 3, so a
#                  position is still ~1/3 of its sleeve (~$6.7k), which is the
#                  40%-of-equity/3-concurrent rule every book was validated under
# Consequence of the split: the account holds 5 names at ~$6.7k = ~$33k deployed
# and ~$67k idle. Idle cash is a known, accepted feature here - x40 tested an
# overlay to deploy it and KILLED the idea - so it stays in cash rather than
# being levered into the remaining names.
SLOTS = {"RSI2": 1, "MFI": 1, "GAPW_RSI2": 1, "GAPW_RSI14": 1, "ZSCORE": 1}
SLOTS_PRIOR = {"RSI2": 3, "MFI": 3, "GAPW_RSI2": 3, "GAPW_RSI14": 3, "ZSCORE": 3}
SIZE_DIVISOR = {"RSI2": 3, "MFI": 3, "GAPW_RSI2": 3, "GAPW_RSI14": 3, "ZSCORE": 3}
GATE_CLOSED_TRADES = 20

# --- SOLO ACCOUNTS: one $100k per book (owner decision 2026-08-04) ----------
# Each book ALSO runs its own separate $100k, so books never compete with each
# other for capital. The shared account above is unchanged and still the
# program-wide gate; this is strictly additional.
#
# Why: the shared account was taking 16% of signals (7 of 44). MFI alone fired
# 23 and the account took 1, because one slot in a $20k sleeve cannot hold a
# book that signals in bursts. That is a real measurement of finite capital and
# it is kept - but it is a terrible rate at which to accumulate per-book
# evidence, and per-book evidence is what decides which books deserve funding.
#
# Mechanics here are the VALIDATED ones, not the owner's 1-slot choice: 3
# concurrent, position = equity/3. That is the 40%-of-equity/3-concurrent rule
# every book was tested under, so a solo account is the closest forward analogue
# of its own backtest.
#
# What this does NOT do, measured before it shipped: it does not stop trades
# being skipped. Capture goes 16% -> 43%, not 100%. With sizing held at /3,
# three positions consume the whole $100k, so raising concurrency to 5 or 10
# changes nothing - CAPITAL binds, not slots. Taking all 23 MFI signals would
# need 23 concurrent at ~$4.3k, i.e. 1/23 sizing and 23-way diversification,
# which is a different strategy from the one that was validated. The
# take-everything measurement already exists and stays published: it is the
# skip-free ledger.
SOLO_CAPITAL = 100_000.0
SOLO_SLOTS = 3
SOLO_DIVISOR = 3


def portfolio(led, books, capital=None, slots=None, divisor=None):
    """Replay the ledger through one account. Pure function - it never mutates
    `led`, so the per-trade record stays exactly as it was.

    Defaults reproduce the shared program account. Pass a single book with
    capital=SOLO_CAPITAL to get that book's solo account instead: sleeve0 is
    capital/len(books), so one book gets the whole thing."""
    capital = CAPITAL if capital is None else capital
    slots = SLOTS if slots is None else slots
    divisor = SIZE_DIVISOR if divisor is None else divisor
    sleeve0 = capital / len(books)
    cash = {b: sleeve0 for b in books}
    open_pos = {b: {} for b in books}          # sym -> {cost, net_pending}
    skipped, taken = [], 0
    today = led.get("as_of")
    exits_today = []                           # ACCOUNT-basis exits, not ledger
    ev = []                                    # (date, entered, exited) events
    for p in list(led.get("closed", [])) + list(led.get("positions", [])):
        b = p.get("book")
        if b not in cash:
            continue
        if p.get("entry_date") and p.get("entry_px"):
            ev.append((p["entry_date"], "in", p))
        if p.get("exit_date") and p.get("net") is not None:
            ev.append((p["exit_date"], "out", p))
    # Ordering within a date, and it is load-bearing:
    #   0  exits of positions opened on an EARLIER date - these free a slot
    #      before the day's entries compete for it
    #   1  entries
    #   2  exits of positions opened the SAME date - a round trip has to open
    #      before it can close
    # Sorting all exits ahead of all entries (the first cut) processed a
    # same-day round trip's exit while the account still held nothing, so the
    # exit found no position, was dropped, and the entry then left a phantom
    # open position holding the book's only slot forever. The Gap Widen books
    # round-trip intraday by design (MOO entry, 3:45 -> MOC exit), so this hit
    # them every time they fired and undercounted the real-money gate.
    def _phase(kind, p):
        if kind != "out":
            return 1
        return 2 if p.get("entry_date") == p.get("exit_date") else 0
    # THE SORT KEY IS AN EVIDENCE BOUNDARY, NOT A FORMATTING CHOICE.
    #
    # This read `(date, _phase)` and relied on Python's stable sort with the
    # comment "keeps rank order" - asserting a property of the input that the
    # input does not have. `ev` is built from `closed + positions`, so inside
    # any one (book, date, entries) contention group EVERY eventually-closed
    # row precedes EVERY still-open row. The book's single slot was therefore
    # awarded on the basis of which trade LATER TURNED OUT TO CLOSE SOONER.
    # That is look-ahead, and it lands on the one number that decides whether
    # real money gets deployed:
    #
    #   shipped (closed + positions)   gate_closed = 21   -> "21 of 20 LEG MET"
    #   reversed input                              7     -> not met
    #   (entry_date, sym)                          12     -> not met
    #   (signal_date, sym)                         12     -> not met
    #   four seeded shuffles                 10,12,16,10  -> not met
    #
    # 31 contended groups exist; ('GAPW_RSI14','2026-08-05') is the clean
    # demonstration - HBM, ATI, VZLA, HD, KRMN, UNM (all closed) ahead of CLS,
    # NMRK, INTR, OTIS (all open).
    #
    # slot_rank is the fix: the book's own rank for that signal, recorded by
    # queue() on the morning it fired, so contention is settled on information
    # that existed then. Rows written before 2026-08-18 have no slot_rank; they
    # fall to a symbol tie-break, which is arbitrary but EXIT-INDEPENDENT, which
    # is the property that matters. Backfilling is not possible from the ledger
    # alone (the published rank was never stored), so the honest gate count
    # stays a lower bound until enough post-fix trades close.
    def _slot(p):
        r = p.get("slot_rank")
        return (0, r) if isinstance(r, int) else (1, 0)
    ev.sort(key=lambda e: (e[0], _phase(e[1], e[2]), _slot(e[2]), e[2]["sym"]))
    closed = []                                # account-basis closed trades
    for date, kind, p in ev:
        b, sym = p["book"], p["sym"]
        if kind == "out":
            held = open_pos[b].pop(sym, None)
            if held is not None:
                cash[b] += held["cost"] * (1.0 + p["net"])     # net already net of friction
                closed.append({"date": date, "book": b, "sym": sym,
                               "net": p["net"], "cost": held["cost"]})
                # The ledger exits every qualifying name; the account only exits
                # what it actually bought. Today's surface must show the second.
                if today and date == today:
                    exits_today.append({"sym": sym, "book": b,
                                        "why": p.get("exit_reason"),
                                        "net": p["net"], "cost": held["cost"]})
            continue
        if sym in open_pos[b]:
            continue
        if len(open_pos[b]) >= slots[b]:
            skipped.append({"date": date, "book": b, "sym": sym, "why": "no free slot"})
            continue
        equity_b = cash[b] + sum(h["cost"] for h in open_pos[b].values())
        # Size on the VALIDATED divisor, not the concurrency cap - holding fewer
        # names at once must not silently enlarge each one.
        size = min(equity_b / divisor[b], cash[b])
        if size <= 1.0:
            skipped.append({"date": date, "book": b, "sym": sym, "why": "no cash"})
            continue
        cash[b] -= size
        open_pos[b][sym] = {"cost": size}
        taken += 1
    invested = {b: sum(h["cost"] for h in open_pos[b].values()) for b in books}
    equity = sum(cash.values()) + sum(invested.values())
    nets = [c["net"] for c in closed]
    gross = sum(n for n in nets if n > 0)
    loss = -sum(n for n in nets if n <= 0)
    return {
        "capital": capital, "slots_per_book": slots,
        # Published so the page cannot re-derive size from the slot count. Those
        # are independent constants and conflating them tripled per-name risk
        # once before (forward_gate_basis.md, amendment of 2026-08-03).
        "size_divisor": divisor,
        # --- the binding real-money gate (owner decision 2026-08-03) ---
        "gate_target": GATE_CLOSED_TRADES,
        "gate_closed": len(closed),
        "gate_remaining": max(GATE_CLOSED_TRADES - len(closed), 0),
        "gate_met": len(closed) >= GATE_CLOSED_TRADES,
        "closed_win_pct": round(100.0 * sum(1 for n in nets if n > 0) / len(nets), 1)
                          if nets else None,
        "closed_avg_pct": round(100.0 * sum(nets) / len(nets), 2) if nets else None,
        "closed_pf": round(gross / loss, 2) if loss > 0 else (None if not nets else 99.0),
        "closed_by_book": {b: sum(1 for c in closed if c["book"] == b) for b in books},
        "closed_recent": closed[-12:],
        "equity_at_cost": round(equity, 2),
        "realized_pct": round(100.0 * (equity / capital - 1.0), 2),
        "cash": round(sum(cash.values()), 2),
        "invested_at_cost": round(sum(invested.values()), 2),
        "utilization_pct": round(100.0 * sum(invested.values()) / max(equity, 1e-9), 1),
        "open_positions": sum(len(v) for v in open_pos.values()),
        # Names the ACCOUNT holds, and the ones it sells today. The Today tab
        # sizes positions off this account model, so it has to count slots and
        # exits off the same model - mixing in the skip-free ledger's open
        # count (which ignores slots entirely) pins every book at zero free
        # slots and silently kills the buy list.
        "open_names": [{"book": b, "sym": s, "cost": round(h["cost"], 2)}
                       for b in books for s, h in sorted(open_pos[b].items())],
        "exits_today": exits_today,
        "taken": taken, "skipped": len(skipped),
        "skipped_recent": skipped[-12:],
        "by_book": {b: {"sleeve_cash": round(cash[b], 2),
                        "invested": round(invested[b], 2),
                        "open": len(open_pos[b]),
                        "skipped": sum(1 for s in skipped if s["book"] == b),
                        "closed": sum(1 for c in closed if c["book"] == b)}
                    for b in books},
        "note": ("Replay of the same ledger through one shared $100k account: "
                 "equal sleeves per book, each book's own slot count inside its "
                 "sleeve, position = sleeve equity / slots. Open positions are "
                 "carried AT COST (unrealized P&L is not marked here), so "
                 "'realized' moves only when trades close. Signals that arrive "
                 "with no free slot or no cash are skipped and counted - that "
                 "gap between the per-trade ledger and this account is the real "
                 "cost of finite capital. THIS is the basis of the binding "
                 "real-money gate: 20 closed trades HERE, program-wide, decided "
                 "2026-08-03 before any trade closed. The skip-free per-book "
                 "ledger is still published, but it counts trades this account "
                 "could not have taken, so it does not open the gate.")}


def solo_accounts(led, books):
    """One $100k account per book, at the validated 3-concurrent / equity-3
    mechanics, so books never compete for capital.

    Returns a compact summary per book - the full portfolio dict five times over
    would bloat the page for no reader benefit. The gate fields are the point:
    real money now needs BOTH the program-wide shared count AND this book's own
    count to reach GATE_CLOSED_TRADES (owner decision 2026-08-04)."""
    out = {}
    for b in books:
        p = portfolio(led, [b], capital=SOLO_CAPITAL,
                      slots={b: SOLO_SLOTS}, divisor={b: SOLO_DIVISOR})
        sig = p["taken"] + p["skipped"]
        out[b] = {
            "capital": SOLO_CAPITAL, "slots": SOLO_SLOTS, "divisor": SOLO_DIVISOR,
            "closed": p["gate_closed"],
            "gate_target": GATE_CLOSED_TRADES,
            "gate_remaining": max(GATE_CLOSED_TRADES - p["gate_closed"], 0),
            "gate_met": p["gate_closed"] >= GATE_CLOSED_TRADES,
            "win_pct": p["closed_win_pct"], "avg_pct": p["closed_avg_pct"],
            "pf": p["closed_pf"],
            "open": p["open_positions"],
            "open_names": [o["sym"] for o in p["open_names"]],
            "taken": p["taken"], "skipped": p["skipped"],
            "capture_pct": round(100.0 * p["taken"] / sig, 1) if sig else None,
            "cash": p["cash"], "invested": p["invested_at_cost"],
            "equity_at_cost": p["equity_at_cost"], "realized_pct": p["realized_pct"],
        }
    tot_t = sum(v["taken"] for v in out.values())
    tot_s = sum(v["skipped"] for v in out.values())
    return {"books": out,
            "capital_each": SOLO_CAPITAL, "slots": SOLO_SLOTS,
            "divisor": SOLO_DIVISOR,
            "closed_total": sum(v["closed"] for v in out.values()),
            "capture_pct": round(100.0 * tot_t / (tot_t + tot_s), 1)
                           if (tot_t + tot_s) else None,
            "note": (
                "Each book also trades its OWN separate $100k, so no book can "
                "crowd out another - owner decision 2026-08-04. Mechanics are "
                "the VALIDATED ones (3 concurrent, position = equity/3), not "
                "the shared account's 1-slot choice, which makes a solo account "
                "the closest forward analogue of that book's own backtest. "
                "This does NOT eliminate skipped trades and was never going to: "
                "with sizing held at equity/3, three positions consume the whole "
                "$100k, so CAPITAL binds rather than slots and raising "
                "concurrency changes nothing. Taking every signal would require "
                "~1/23 position sizing on MFI, which is a different strategy "
                "from the validated one - the take-everything measurement is the "
                "skip-free ledger, which stays published. REAL MONEY NEEDS BOTH: "
                "20 closed trades in the shared program account AND 20 in that "
                "book's own account. Strictly more conservative than the "
                "pre-registered gate, which is unchanged.")}


def ema(closes, n):
    a = 2.0 / (n + 1)
    e = closes[0]
    for c in closes[1:]:
        e = a * c + (1 - a) * e
    return e


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def rsi(closes, n):
    if len(closes) < n + 1:
        return None
    a = 1.0 / n
    g = l = None
    for prev, cur in zip(closes, closes[1:]):
        ch = cur - prev
        gain, loss = max(ch, 0.0), max(-ch, 0.0)
        if g is None:
            g, l = gain, loss
        else:
            g = a * gain + (1 - a) * g
            l = a * loss + (1 - a) * l
    return 100.0 if l == 0 else 100.0 - 100.0 / (1.0 + g / l)


def exit_hit(book, closes):
    """Book exit rule evaluated on the newest bar (close basis)."""
    c = closes[-1]
    if book == "GAPW_RSI2":
        r = rsi(closes, 2); return r is not None and r > 80 and "rsi2>80"
    if book == "GAPW_RSI14":
        r = rsi(closes, 14); return r is not None and r > 60 and "rsi14>60"
    if book == "ZSCORE":
        e = ema(closes, 5); return c > e and "close>ema5"
    if book == "RSI2":
        s = sma(closes, 5); return s is not None and c > s and "close>sma5"
    if book == "MFI":
        e = ema(closes, 7); return c > e and "close>ema7"
    return False


def blob(html, name):
    m = re.search(r"const %s = (.*?);\n" % name, html, re.S)
    return json.loads(m.group(1)) if m else None


def next_session_earnings(nxt, as_of):
    if not nxt:
        return False
    d0 = datetime.date.fromisoformat(as_of)
    nx = d0 + datetime.timedelta(days=1)
    while nx.weekday() >= 5:
        nx += datetime.timedelta(days=1)
    return as_of <= nxt <= nx.isoformat()


def main():
    args = sys.argv[1:]
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    bars_path, page_path = opt("--bars"), opt("--page")
    if not bars_path or not page_path:
        sys.exit("--bars bars.json --page index.html required")
    ledger_path = opt("--ledger", os.path.join(
        os.path.dirname(os.path.abspath(page_path)), "data", "shadow_book.json"))
    bars = json.load(open(bars_path))
    earnings = json.load(open(opt("--earnings"))) if opt("--earnings") else {}
    page = open(page_path).read()
    booksig = blob(page, "BOOKSIG") or {"rows": []}
    signals = blob(page, "SIGNALS") or {"signals": []}
    scan = blob(page, "SCAN") or {"tickers": {}}
    led = (json.load(open(ledger_path)) if os.path.exists(ledger_path)
           else {"positions": [], "closed": [], "as_of": None})

    as_of = max((v[-1][0] for v in bars.values() if v), default=None)
    if not as_of:
        sys.exit("no bars")
    if led.get("as_of") == as_of:
        print("shadow: already processed %s - idempotent no-op" % as_of, file=sys.stderr)
    dates = {s: [r[0] for r in v] for s, v in bars.items()}
    closes = {s: [float(r[4] if len(r) >= 6 else r[1]) for r in v] for s, v in bars.items()}
    opens = {s: [float(r[1]) if len(r) >= 6 else None for r in v] for s, v in bars.items()}

    def series_upto(sym, date):
        ds = dates.get(sym) or []
        if date in ds:
            return closes[sym][:ds.index(date) + 1]
        return None

    # Corporate-action guard (2026-08-15, after MNST's 2:1 split landed mid-hold
    # and booked a -51.6% phantom loss): the provider back-adjusts history, so
    # the stored entry_px silently changes basis the day a split lands. Re-anchor
    # every open position against the CURRENT series at its entry date and
    # rebase when the deviation is corporate-action sized, logging the repair on
    # the row. Sub-2% drift (dividend adjustments) is deliberately left alone.
    for p in led["positions"]:
        if p.get("state") != "open" or not p.get("entry_px") or not p.get("entry_date"):
            continue
        ds = dates.get(p["sym"]) or []
        if p["entry_date"] not in ds:
            continue
        i = ds.index(p["entry_date"])
        ref = (opens[p["sym"]][i] if p.get("basis") == "moo"
               else closes[p["sym"]][i])
        if not ref:
            # 2-field bars carry no open: a moo row can't be re-anchored, and a
            # silent skip would re-create the exact bug class this guard exists
            # for. Say so loudly; the fetch should always run with --ohlcv.
            print("shadow: WARNING corp-action guard cannot check %s %s - no "
                  "open in bars (fetch without --ohlcv?)"
                  % (p["book"], p["sym"]), file=sys.stderr)
            continue
        if abs(ref / p["entry_px"] - 1.0) <= 0.02:
            continue
        old_e, ratio = p["entry_px"], ref / p["entry_px"]
        p["entry_px"] = round(ref, 4)
        if p.get("signal_close"):
            p["signal_close"] = round(p["signal_close"] * ratio, 4)
        p["note"] = ((p.get("note") + " ") if p.get("note") else "") + (
            "corp-action rebase %s: entry_px %s -> %s (x%.4f vs current adjusted series)"
            % (as_of, old_e, p["entry_px"], ratio))
        print("shadow: corp-action rebase %s %s entry %s -> %s"
              % (p["book"], p["sym"], old_e, p["entry_px"]), file=sys.stderr)

    # Names whose exit could not be evaluated this run (see the loop below).
    unchecked = []
    first_pass = led.get("as_of") != as_of
    if first_pass:
        # 1) fill queued MOO entries at the first bar AFTER the signal date
        for p in led["positions"]:
            if p["state"] != "pending_open":
                continue
            ds = dates.get(p["sym"]) or []
            nxt = next((i for i, d in enumerate(ds) if d > p["signal_date"]), None)
            if nxt is not None and opens[p["sym"]][nxt] is not None:
                p["state"] = "open"
                p["entry_date"] = ds[nxt]
                p["entry_px"] = round(opens[p["sym"]][nxt], 4)
            elif (datetime.date.fromisoformat(as_of)
                  - datetime.date.fromisoformat(p["signal_date"])).days > 7:
                p["state"] = "closed"; p["exit_reason"] = "never_filled"; p["net"] = None

        # 2) exits on the newest bar
        for p in led["positions"]:
            if p["state"] != "open":
                continue
            ds = dates.get(p["sym"]) or []
            if as_of not in ds or p["entry_date"] not in ds:
                # NOT a silent continue. This skip sits before bars_held, before
                # the rule test and before the 10-bar time stop, and the whole
                # loop runs only when first_pass is true - led["as_of"] is
                # stamped unconditionally below, so a bar skipped for want of
                # data is skipped PERMANENTLY and never re-evaluated. The
                # position then holds its book's only slot and its cash
                # forever: freeSlots() stays 0 and every later buy in that book
                # is deferred to the "no capital, no decision" list with no
                # explanation. portfolio() names this exact class already - "a
                # phantom open position holding the book's only slot forever".
                #
                # Not hypothetical: track_snapshot_reference.py records that EA
                # sat at its 08-04 take-private close, volume 0, for ten days,
                # and 20 of the currently-open ledger names are absent from
                # SCAN entirely - they depend on the static BOOKS list, so
                # dropping a name from either list drops its bars. The
                # corp-action guard forty lines up refuses to be quiet in the
                # same situation ("a silent skip would re-create the exact bug
                # class this guard exists for. Say so loudly"). So: say so,
                # flag the row for the page, and do not let the as_of stamp
                # bury it - unchecked rows are recorded and retried.
                why = ("no bar for %s" % as_of if as_of not in ds
                       else "entry bar %s missing" % p["entry_date"])
                print("WARNING: exit UNCHECKED %s %s - %s (%d bars on file). "
                      "Position holds its slot; will retry next run."
                      % (p["book"], p["sym"], why, len(ds)))
                p["exit_unchecked"] = as_of
                p["exit_unchecked_why"] = why
                unchecked.append("%s/%s" % (p["book"], p["sym"]))
                continue
            # Cleared on any bar the check actually runs, so a transient gap
            # does not leave a permanent mark on the row.
            p.pop("exit_unchecked", None)
            p.pop("exit_unchecked_why", None)
            held = ds.index(as_of) - ds.index(p["entry_date"])
            p["bars_held"] = held
            cs = series_upto(p["sym"], as_of)
            reason = None
            hit = exit_hit(p["book"], cs)
            if hit:
                reason = hit
            elif p["book"] == "ZSCORE" and next_session_earnings(earnings.get(p["sym"]), as_of):
                reason = "pre-earnings"
            elif held >= 10:
                reason = "time-stop"
            if reason:
                px = cs[-1]
                p.update(state="closed", exit_date=as_of, exit_px=round(px, 4),
                         exit_reason=reason,
                         net=round(px / p["entry_px"] - 1.0 - FRICTION_RT[p["book"]], 5))

        led["closed"] += [p for p in led["positions"] if p["state"] == "closed"]
        led["positions"] = [p for p in led["positions"] if p["state"] != "closed"]

    # 3) today's signals - on EVERY build for this bar, not only the first pass.
    # 2026-08-14 lesson: the 20:57Z scheduled build advanced as_of with a
    # numpy-broken signals_cloud.py (SIGNALS stale at 08-11), and the as_of
    # idempotency lock then refused the fixed evening reruns their queue pass -
    # 11 vetted RSI2/MFI TAKEs were silently lost from the forward record.
    # Requeuing is safe outside the first pass: queue() dedupes on (book, sym)
    # against current positions, both feeds are row-filtered to as_of, and a
    # same-bar entry can never carry outcome information (exits only run on the
    # first pass of a NEWER bar).
    have = {(p["book"], p["sym"]) for p in led["positions"]}
    def queue(book, sym, sig_close, slot_rank=None):
        if (book, sym) in have:
            return
        have.add((book, sym))
        basis = BASIS[book]
        p = {"book": book, "sym": sym, "signal_date": as_of,
             "basis": basis, "bars_held": 0, "signal_close": sig_close,
             # The book's OWN rank for this signal on the day it fired - by
             # rs252/rsi3 for the book scanners, by shrunk expectancy for the
             # generator arms. Persisted because the account replay has to
             # decide which of several same-day signals gets the book's one
             # slot, and it MUST decide that on information available that
             # morning. See the ordering comment in portfolio().
             "slot_rank": slot_rank,
             "entry_date": None, "entry_px": None,
             "exit_date": None, "exit_px": None, "exit_reason": None, "net": None,
             "state": "pending_open"}
        if basis == "close":
            p.update(state="open", entry_date=as_of, entry_px=sig_close)
        led["positions"].append(p)
        if not first_pass:
            p["note"] = ("late-queued %s: feed was stale when this bar was first "
                         "processed; fills at the next session open, same as a "
                         "first-pass queue" % as_of)
            print("shadow: late-queue %s %s (feed fresh on rerun)"
                  % (book, sym), file=sys.stderr)

    if (booksig.get("as_of") == as_of):
        for r in booksig.get("rows", []):
            if r.get("state") == "TAKE" and r.get("strat") in BASIS:
                queue(r["strat"], r["sym"], r.get("close"), r.get("book_rank"))
    # Rank the generator's qualifying signals the way the Signals tab ranks
    # them - shrunk expectancy, avg x n/(n+10), highest first - BEFORE queueing,
    # so a same-day slot fight is settled on the morning's evidence and not on
    # iteration order. Per book, since slots are per book.
    gen = []
    for x in signals.get("signals", []):
        if (x.get("state") == "TAKE" and x.get("new_today")
                and x.get("as_of") == as_of
                # RSI2 kept live 2026-08-02 by owner decision (brain evidence);
                # x47's contrary fold is recorded on the dashboard, not enforced.
                and x.get("strat") in ("RSI2", "MFI")):
            st = (scan["tickers"].get(x["sym"], {}).get("strats", {})
                  .get(x["strat"]))
            if st and st.get("vetted") and (st.get("n") or 0) >= 30:
                n, avg = st.get("n") or 0, st.get("avg_pct")
                score = (avg * (n / (n + 10.0))) if avg is not None else None
                gen.append((x["strat"], x["sym"], x.get("close"), score))
    by_book = {}
    for strat, sym, close, score in gen:
        by_book.setdefault(strat, []).append((score, sym, close))
    for strat, rows in by_book.items():
        # -score for descending; sym as the exit-independent tie-break
        rows.sort(key=lambda r: (-(r[0] if r[0] is not None else -1e9), r[1]))
        for i, (score, sym, close) in enumerate(rows, 1):
            queue(strat, sym, close, i)
    # Advance the run stamp ONLY when every open position was actually
    # evaluated. Stamping unconditionally is what turned a one-day data gap
    # into a permanent skip: first_pass goes false on the next run and the exit
    # loop never looks at that row again. Holding the stamp back costs one
    # repeated pass (the fill and queue steps are idempotent - queue() dedupes
    # on (book, sym) and fills only touch state=="pending_open"); burying an
    # unchecked exit costs a slot forever.
    if unchecked:
        print("WARNING: %d position(s) had no exit check this run (%s). "
              "Holding the ledger as_of at %s so the next run re-evaluates them."
              % (len(unchecked), ", ".join(sorted(unchecked)), led.get("as_of")))
        led["unchecked_as_of"] = as_of
        led["unchecked"] = sorted(unchecked)
    else:
        led.pop("unchecked_as_of", None)
        led.pop("unchecked", None)
        led["as_of"] = as_of

    # stats + blob
    books = ["RSI2", "MFI", "GAPW_RSI2", "GAPW_RSI14", "ZSCORE"]
    stats = {}
    for b in books:
        tr = [p for p in led["closed"] if p["book"] == b and p.get("net") is not None]
        stats[b] = {"n": len(tr),
                    "win": round(100.0 * sum(1 for t in tr if t["net"] > 0) / len(tr), 1) if tr else None,
                    "avg": round(100.0 * sum(t["net"] for t in tr) / len(tr), 2) if tr else None,
                    "open": sum(1 for p in led["positions"] if p["book"] == b and p["state"] == "open"),
                    "pending": sum(1 for p in led["positions"] if p["book"] == b and p["state"] == "pending_open")}
    exits_today = [{"sym": p["sym"], "book": p["book"], "why": p["exit_reason"],
                    "net": p.get("net")}
                   for p in led["closed"] if p.get("exit_date") == as_of]
    # "started" must be the record's inception, not today. The old expression
    # led.get("started") or as_of re-stamped the CURRENT bar every build while
    # the ledger's null persisted (setdefault never replaces a stored null), so
    # the book's inception silently drifted forward day by day. Derive it from
    # the ledger's own earliest event instead - a date the data proves, not one
    # chosen after the fact - and persist it so it never moves again.
    _first = min((d for p in (led.get("positions") or []) + (led.get("closed") or [])
                  for d in (p.get("signal_date"), p.get("entry_date"))
                  if d), default=None)
    shadow = {"as_of": led.get("as_of"), "started": led.get("started") or _first or as_of,
              "stats": stats,
              "open": [{k: p.get(k) for k in ["book", "sym", "state", "signal_date",
                        "entry_date", "entry_px", "bars_held"]} for p in led["positions"]],
              "exits_today": exits_today,
              "closed_total": len([p for p in led["closed"] if p.get("net") is not None]),
              "portfolio": portfolio(led, books),
              "solo": solo_accounts(led, books)}
    if not led.get("started"):          # setdefault keeps a stored null forever
        led["started"] = shadow["started"]

    os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
    json.dump(led, open(ledger_path, "w"), indent=1)
    line = "const SHADOW = " + json.dumps(shadow, separators=(",", ":")) + ";"
    assert "</" not in line
    if "--splice" in args:
        page2, n = re.subn(r"const SHADOW = .*?;\n", lambda _m: line + "\n", page, count=1, flags=re.S)
        if n != 1:
            sys.exit("no `const SHADOW = ...;` line in page")
        open(page_path, "w").write(page2)
        print("shadow: %s | open %d | pending %d | closed %d | exits today %d"
              % (as_of, sum(1 for p in led["positions"] if p["state"] == "open"),
                 sum(1 for p in led["positions"] if p["state"] == "pending_open"),
                 shadow["closed_total"], len(exits_today)), file=sys.stderr)
    else:
        print(line)


if __name__ == "__main__":
    main()
