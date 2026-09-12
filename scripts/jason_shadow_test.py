#!/usr/bin/env python3
"""Fail-closed checks for the JASON paper ledger's pure rules. Run before the
build; a non-zero exit blocks the splice."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jason_shadow as J

def bars(closes, vol=1_000_000, spread=1.0):
    out = []
    d = 20250101
    for i, c in enumerate(closes):
        day = f"2025-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}"
        out.append([day, c, c + spread, c - spread, c, vol])
    return out

def check(cond, msg):
    if not cond:
        print("FAIL:", msg); sys.exit(1)

# ATR and VAP on a flat series
b = bars([100.0] * 60)
check(abs(J.atr14(b) - 2.0) < 1e-9, "atr14 on a flat series with a 2-point range is 2")
check(abs(J.vap(b) - 100.0) < 1e-9, "vap of a flat series is the price")
check(J.vap(b[:10]) is None, "vap needs 50 bars")

# A dislocated leader takes; each failing rule names itself
seq = bars([100.0 + 0.1 * i for i in range(300)])      # rising, so > SMA200
as_of = seq[-1][0]
seq[-1][4] = seq[-1][4] - 6.0                            # last close pushed below VAP - 1.5 ATR
take, why, det = J.signal(seq, spy_r=-0.30, earn_dates=[], as_of=as_of)
check(take and why == "take", f"dislocated leader should take, got {why} {det}")
check(det["close"] <= det["threshold"], "detail shows the dislocation")

take, why, _ = J.signal(seq, spy_r=0.10, earn_dates=[], as_of=as_of)
check(not take and why == "rs_weak", f"RS gate: {why}")
take, why, _ = J.signal(seq, spy_r=-0.30, earn_dates=[as_of], as_of=as_of)
check(not take and why == "earnings_in_hold", f"earnings gate: {why}")
take, why, _ = J.signal(seq, spy_r=-0.30, earn_dates=[], as_of=as_of, last_signal_date=seq[-3][0])
check(not take and why == "too_soon", f"5-bar spacing: {why}")
take, why, _ = J.signal(seq, spy_r=-0.30, earn_dates=[], as_of="2099-01-01")
check(not take and why == "stale", f"stale bar refused: {why}")
thin = [r[:5] + [100] for r in seq]
take, why, _ = J.signal(thin, spy_r=-0.30, earn_dates=[], as_of=as_of)
check(not take and why == "thin_volume", f"volume gate: {why}")

# Exit: VAP reversion wins, expiry otherwise
s2 = bars([100.0] * 60)
s2[-1][4] = 90.0                                        # dislocated entry bar
tail = bars([90.0, 92.0, 101.0, 102.0])
for i, r in enumerate(tail):
    r[0] = f"2026-02-{i + 1:02d}"
s2 += tail
hit = J.exit_test(s2, 59, expiry="2026-12-31")
check(hit and hit[1] == "VAP" and s2[hit[0]][4] >= 100.0, f"VAP reversion exit: {hit}")
hit = J.exit_test(s2[:62], 59, expiry="2026-02-02")
check(hit and hit[1] == "EXPIRY", f"expiry exit: {hit}")
check(J.exit_test(s2[:61], 59, expiry="2026-12-31") is None, "still open")

# Sizing on JASON's slot, never ROBERT's
leg = {"prem_paid": 40.0, "contracts": 3, "cost": 12000.0, "exit_recv": 50.0, "pnl": 3000.0,
       "prem_mid": 39.0, "band": {"0.16": {"ret": 0.25, "pnl": 1.0}}}
J.resize_leg(leg)
check(leg["contracts"] == 3 and leg["cost"] == 12000.0 and leg["pnl"] == 3000.0, "12,500 / 4,000 = 3 contracts")
check(abs(leg["band"]["0.16"]["pnl"] - 0.25 * 40.0 * 100 * 3) < 1e-6, "band pnl rebuilt at the slot")
leg = {"prem_paid": 200.0, "contracts": 1, "cost": 20000.0}
J.resize_leg(leg)
check(leg["contracts"] == 1, "a slot that cannot afford one contract still buys one")
print("jason_shadow_test: all checks passed")
