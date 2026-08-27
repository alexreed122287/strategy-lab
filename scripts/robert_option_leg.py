#!/usr/bin/env python3
"""ROBERT option leg - the DITM long call the shadow book's stock leg stands in for.

The shadow ledger (robert_shadow.py) records the STOCK leg because that is the
skip-free signal-evidence machine: it fills and exits mechanically, it cannot be
talked out of a trade, and 20 closed rows there is one leg of the go-live gate.
But ROBERT does not trade stock. It buys a deep-in-the-money call, and a +1.5%
stock move is not a +1.5% position - it is roughly +9% on the premium. This
module expresses each ledger row in the vehicle actually specced, so the forward
record reads in the units the account would feel.

WHAT THIS IS, STATED BEFORE THE NUMBERS. Two bases, tagged per row:

  CHAIN  a real Tradier quote for the selected contract - bid/ask captured at
         the time, mid taken as the mark. Real market data, still not a fill:
         no order has ever rested in a book. This is what the Paper-Fill Log
         exists to correct and what D11 gates on.
  MODEL  Black-Scholes at the underlying's rv-blend IV proxy - the SAME number
         the scan card prints in its "IV proxy" column and gates at <=60%.
         Used when no chain quote was captured (every row entered before this
         module existed, i.e. the backfill).

MODEL was validated against live chains on 2026-08-26 for the six names then in
the book: mean error -1.4%, mean ABSOLUTE error 4.5% against the real mid, with
no systematic bias. The RV->IV multiplier of 1.25 carried by rsi2_call_model
(which calibrates against expired-contract fills on a different, cheaper class)
over-prices this basket by 6-12% and is deliberately NOT applied here - the
names ROBERT trades have IV sitting close to their own realised vol.

Friction is the locked backtest's published assumption, and is the same pair of
numbers the Paper-Fill Log scores real fills against: 1.25% of premium on entry
(09:45 limit worked from mid), 2.5% on exit (MOC, limit worked from mid). Those
derive from f=0.16 of the quoted half-spread, the fraction real prints land at.
Nothing here measures realised friction - it cannot. That is D11's job.

Stdlib only: the daily build runs on a GitHub runner with no scientific stack.
"""
from __future__ import annotations

import datetime as dt
import math

# Risk-free rate, matching rsi2_call_model so premiums are comparable across
# the research line. A 50-DTE DITM call is not sensitive to this to any degree
# that survives the 4.5% pricing error above.
R = 0.03

# The locked spec's contract: first monthly with at least 30 days to run, the
# shallowest strike whose extrinsic is under a fifth of the premium. Delta lands
# 0.78-0.82 as an OUTCOME of that rule, not as the rule itself.
MIN_DTE = 30
MAX_EXTRINSIC = 0.20

# Published friction, as fractions of premium. See the module docstring.
FRICTION_ENTRY = 0.0125
FRICTION_EXIT = 0.0250

# Sleeve the dollar figures are expressed on. The spec sizes 6 slots x 15%;
# a slot that cannot afford even one contract still buys one, and the resulting
# over/under-deployment is reported rather than hidden.
SLEEVE = 100_000.0
SLOTS = 6
SLOT_FRAC = 0.15


def ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sig: float) -> float:
    """Black-Scholes call. Below expiry or vol, falls back to intrinsic."""
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0.0)
    v = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (R + sig * sig / 2.0) * T) / v
    return S * ncdf(d1) - K * math.exp(-R * T) * ncdf(d1 - v)


def call_delta(S: float, K: float, T: float, sig: float) -> float:
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 1.0 if S > K else 0.0
    v = sig * math.sqrt(T)
    return ncdf((math.log(S / K) + (R + sig * sig / 2.0) * T) / v)


def third_friday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7 + 14)


def first_monthly(after: dt.date, min_dte: int = MIN_DTE) -> dt.date:
    """First standard monthly expiry at least min_dte calendar days out.

    Matches robert_chain_gate.py's operational reading of the spec ("first
    monthly >=30 DTE"). The spec text says 30-50; on some entry dates no
    monthly lands inside that band at all - Sep 18 is 28 days from Aug 21 and
    Oct 16 is 56 - so the band cannot be a hard filter without silently
    dropping trades. Taking the first monthly past 30 is what the live chain
    sweep already does, so the two agree by construction.
    """
    y, m = after.year, after.month
    for _ in range(4):
        exp = third_friday(y, m)
        if (exp - after).days >= min_dte:
            return exp
        m += 1
        if m > 12:
            m = 1
            y += 1
    return third_friday(y, m)


def strike_step(S: float) -> float:
    """FALLBACK strike increment, used only when the real listed strikes could
    not be read. Measured 2026-08-26 on the Oct-16 chains: real grids are
    irregular and name-specific - PAAS mixes 1s and 5s, GOOGL/PANW/ATI/SNX mix
    5s and 10s, SOXX is all 5s at $515 while SPOT mixes 10s and 20s at $538 and
    PWR is all 10s at $617. No formula reproduces that, which is exactly why
    select_strike prefers the listed set and this exists only for the offline
    path."""
    if S < 25:
        return 0.5
    if S < 50:
        return 1.0
    if S < 500:
        return 5.0
    return 10.0


def select_strike(S: float, T: float, sig: float,
                  strikes: list | None = None) -> float | None:
    """Shallowest (highest) strike whose extrinsic is under MAX_EXTRINSIC of
    premium - the spec's contract, not the deepest one that happens to pass.

    `strikes` is the REAL listed set for the expiry when the build could read
    it. Selecting off a guessed grid was a live defect: the first cut of this
    module priced PWR at a 555 strike that the chain does not list, so the
    contract could never be quoted and its live-chain check silently blanked.
    """
    if strikes:
        cands = sorted(k for k in strikes if 0 < k < S)
    else:
        step = strike_step(S)
        k = math.floor(S * 0.65 / step) * step
        cands = []
        while k < S:
            if k > 0:
                cands.append(k)
            k += step
    best = None
    for k in cands:
        prem = bs_call(S, k, T, sig)
        intr = max(S - k, 0.0)
        if prem > 0.05 and intr > 0 and (prem - intr) / prem < MAX_EXTRINSIC:
            best = k
    return best


def contracts_for(premium: float, slot_dollars: float = SLEEVE * SLOT_FRAC) -> int:
    """Contracts a slot buys. Floor, but never zero: the spec's 15% slot cannot
    afford a single $9,300 PWR call at some sleeve sizes, and reporting that
    trade as 'not taken' would quietly drop the most expensive - and therefore
    most leveraged - names out of the forward record."""
    cost = max(premium, 0.01) * 100.0
    return max(1, int(slot_dollars // cost))


def price_leg(spot: float, entry_date: str, sig: float,
              exit_spot: float | None = None, exit_date: str | None = None,
              expiry: str | None = None, strike: float | None = None,
              strikes: list | None = None):
    """Model-mark one leg. Returns a dict, or None when no strike qualifies.

    entry_date/exit_date are ISO strings; the exit leg reprices the SAME
    contract at the later date with time decayed and vol left flat. Flat vol is
    the conservative reading for this strategy: the exit is a bounce completing
    into strength, where IV normally falls, so holding sigma constant slightly
    UNDER-states the win. rsi2_call_model applies a 0.90 crush here; that was
    fitted to a cheaper, higher-beta class and is not carried over.
    """
    ed = dt.date.fromisoformat(entry_date)
    exp = dt.date.fromisoformat(expiry) if expiry else first_monthly(ed)
    T_e = (exp - ed).days / 365.0
    K = strike if strike is not None else select_strike(spot, T_e, sig, strikes)
    if K is None:
        return None
    prem_e = bs_call(spot, K, T_e, sig)
    if prem_e <= 0.05:
        return None
    out = {
        "expiry": exp.isoformat(),
        "strike": round(K, 2),
        "dte": (exp - ed).days,
        "sigma": round(sig, 4),
        "delta": round(call_delta(spot, K, T_e, sig), 3),
        "prem_mid": round(prem_e, 4),
        "prem_paid": round(prem_e * (1 + FRICTION_ENTRY), 4),
        "basis": "MODEL",
        "strike_src": "chain" if strikes else "grid",
    }
    out["extrinsic_pct"] = round(100.0 * (prem_e - max(spot - K, 0.0)) / prem_e, 1)
    out["contracts"] = contracts_for(out["prem_paid"])
    out["cost"] = round(out["prem_paid"] * 100.0 * out["contracts"], 2)
    if exit_spot is not None and exit_date is not None:
        xd = dt.date.fromisoformat(exit_date)
        T_x = max((exp - xd).days / 365.0, 0.0)
        prem_x = max(bs_call(exit_spot, K, T_x, sig), max(exit_spot - K, 0.0))
        out["exit_mid"] = round(prem_x, 4)
        out["exit_recv"] = round(prem_x * (1 - FRICTION_EXIT), 4)
        out["ret"] = round(out["exit_recv"] / out["prem_paid"] - 1.0, 5)
        out["pnl"] = round((out["exit_recv"] - out["prem_paid"]) * 100.0
                           * out["contracts"], 2)
    return out


def mark_leg(leg: dict, spot: float, as_of: str,
             chain_mid: float | None = None) -> dict:
    """Mark an OPEN leg to the newest bar. Uses a real chain mid when the build
    captured one, else reprices the frozen contract. Returns the marks only -
    it never mutates the frozen entry, which is the whole point of freezing."""
    exp = dt.date.fromisoformat(leg["expiry"])
    T = max((exp - dt.date.fromisoformat(as_of)).days / 365.0, 0.0)
    if chain_mid is not None and chain_mid > 0:
        mid, basis = float(chain_mid), "CHAIN"
    else:
        mid = max(bs_call(spot, leg["strike"], T, leg["sigma"]),
                  max(spot - leg["strike"], 0.0))
        basis = "MODEL"
    recv = mid * (1 - FRICTION_EXIT)
    return {
        "mark_mid": round(mid, 4),
        "mark_recv": round(recv, 4),
        "mark_basis": basis,
        "mark_dte": (exp - dt.date.fromisoformat(as_of)).days,
        "ret": round(recv / leg["prem_paid"] - 1.0, 5),
        "pnl": round((recv - leg["prem_paid"]) * 100.0 * leg["contracts"], 2),
    }
