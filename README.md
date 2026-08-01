# Strategy Lab

Static research dashboard: multi-strategy ticker rankings (vetted arms only),
daily-optimal pick backtests, latest-bar signals, options-expression evidence,
and timeframe verdicts. Built from end-of-day data; see the as-of stamps and
the Method tab for methodology and known biases.

Research and education only. Not financial advice.

## Position tracking & the TRACK snapshot

The Positions tab tracks manual buys (browser localStorage — device-local;
export/import JSON lives on the tab) and flags sells by evaluating each book's
exact exit rule (rsi2>80, rsi14>60, close>ema5/sma5/ema7, 10-bar time stop,
z-score earnings force-exit) against an indicator snapshot embedded in the page:

    const TRACK = {"as_of":"YYYY-MM-DD","source":"...","tickers":{"SYM":{
      "close":0,"rsi2":0,"rsi3":0,"rsi14":0,"sma5":0,"ema5":0,"ema7":0,
      "next_earnings":null}}};

This build ships `const TRACK = null;` — until the local generator emits the
line each build, the tab tracks 10-bar time stops only (weekday-approximate).
`scripts/track_snapshot_reference.py` is a dependency-free reference
implementation with the exact indicator math from the strategy specs; it reads
a closes JSON and splices the TRACK line into index.html (`--splice`). Wire it
into the daily build after the normal blob refresh.
