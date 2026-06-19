# Plan: L2 forward paper-trading (causal, no real money)

Status: proposed (2026-06-19). Roadmap step 6 (`docs/ROADMAP.md`); GATED on the
product ledger (step 1) existing first. Council call (`_council-consolidation-review/
FINAL_verdict.md`): GO WITH CHANGES, "make it boring" -- the value is an honest
forward equity curve, not a dashboard or brokerage cosplay.

## Purpose

IC says the ranking has signal; it does not prove investable user value. L2 takes
the engine's REAL daily picks and tracks a forward virtual portfolio vs a benchmark,
so we can answer "should the single user trust the emitted ratings" with a curve,
not a correlation. Forward, look-ahead-free, no broker, no real money, free data.

## Hard prerequisite

L2 reads ONLY from the append-only product ledger (`research_run` +
`rating_snapshot`, step 1), consuming only `complete`, health-gated runs before the
execution cutoff. It must never recompute the past from the mutable signal/price
tables (that would peek at revised data). Orders are generated from a PRIOR
immutable snapshot and persisted BEFORE any execution price is consumed.

## Minimal canonical user-facing book

```text
Universe:    eligible names from a completed, gated snapshot
Selection:   top 50 by rank, BUY/OW preferred, then fill by rank
Weighting:   equal weight
Max position:2%
Rebalance:   weekly
Execution:   signal after close D  ->  fill at D+1 close (default)
Costs:       10 bps per side (default); also report 5 / 20 bps sensitivity
Benchmark:   SPY adjusted return; secondary RSP
Cash policy: pre-registered (hold cash, or fill from next ranks) -- decided up front
```

Why D+1 close over D+1 open: with free yfinance-style data, next-day close is less
self-deceiving than next-day open unless open-price reliability is explicitly
validated. Rule: "signal after close D; fill at the first later price you trust."

This long-only top-50 book is the PRODUCT test ("trust the ratings?"). A separate
decile-spread / broad rank-weighted book is a RESEARCH diagnostic ("is there
cross-sectional ranking alpha?") and is backlog, explicitly labelled not the user
portfolio -- do not let a beta-hedged institutional book become the only truth layer.

## Persistence (minimum, then extend)

```sql
l2_strategy        -- the frozen ruleset (params above), versioned
l2_order           -- generated from a prior snapshot, persisted pre-execution
l2_equity_daily    -- daily marked equity + benchmark
-- extend when needed:
l2_fill
l2_position_daily
```

## Honesty controls (report every one)

Gross AND net returns; turnover; stale-price count; missing-price count;
BUY/OW/HOLD/UW/SELL counts; sector concentration; beta to SPY; confidence bands
(do not let ~6 months of noise look like proof). Expectation-setting: with
confidence ~50% and signal ICs ~0.04-0.09, a long-only top-50 book clearing costs
is NOT guaranteed; the honest output may be "no edge net of costs," and that is a
valid, valuable result.

## Stale / dead-feed handling (held positions never silently vanish)

```text
Missing 1 day:   carry last valid price, flag stale.
Missing > K days:force exit (or require corporate-action resolution).
Forced exit, unknown price: apply a conservative penalty.
Ticker change:   explicit symbol map or a manual correction run.
Never drop a held position without an explicit exit event.
```

This reuses the dead-feed detection already shipped in the picks guard.

## Verification

- A held position with a killed feed produces an exit event + penalty, never a
  silent disappearance (test on a synthetic dead-feed ticker).
- Orders for date D are persisted with `run_id` of the D-1 snapshot and timestamps
  proving they predate the execution price read (causal-ordering test).
- Equity curve reproduces from `l2_order` + `daily_prices` deterministically.

## Explicitly deferred

L3 real-money live execution (broker API). Gated on L2 showing a forward edge over
a meaningful window. Free data is not the blocker there; the broker / order-lifecycle
/ reconciliation surface is. Revisit only after L2.
