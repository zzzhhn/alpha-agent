# Plan: append-only product ledger + run-health gates

Status: proposed (2026-06-19), elevated to the #1 move by the llm-council review
(`docs/_council-consolidation-review/FINAL_verdict.md`). This is the prerequisite
for honest L2, forward IC, drift detection, adaptive-weight validation, and tier
monotonicity. Everything else can silently recompute the past without it.

## Problem

The engine has no causal memory of what it believed when. `daily_signals_fast` is
UPSERTed (overwritten) by the cron, and `daily_prices` is auto-adjusted, so any
"backtest" or "paper-trade" done later marks against a revised past. The picks a
user actually saw on day D are not immutably recorded with the inputs and policy
that produced them. We cannot currently answer "what exactly did the engine emit on
2026-06-10, and would acting on it have worked" without recomputation that peeks.

## Design

### Two append-only tables (no overwrites; corrections create new run IDs)

```sql
research_run(
  id,
  scheduled_for_date,        -- the market date this run is FOR
  run_type,                  -- e.g. daily_close
  status,                    -- started | partial | complete | failed | corrected
  started_at, finished_at,
  data_asof,                 -- latest input data timestamp
  input_data_cutoff,         -- the point-in-time cutoff used
  code_version,              -- git sha
  registry_hash,             -- hash of the signal registry (step 3)
  weight_policy_id,          -- which WeightPolicy was live
  tier_threshold_version
)

rating_snapshot(
  run_id,                    -- FK research_run.id
  ticker,
  in_universe, eligible, eligibility_reason,
  composite_z, rank, tier, coverage,
  effective_weight_json,     -- the weights actually applied
  user_visible_payload_json, -- WHAT THE USER SAW, not what we'd recompute
  price_source, price_downloaded_at, adjustment_mode, feed_status
)
```

Rules: one canonical `complete` run per market date; partial runs are not tradable;
a correction is a NEW run id (the old one is never mutated).

### Run-health + abstention gates (roadmap step 2)

Each run is scored and gated before it can be consumed as tradable truth:
eligible-count, stale-feed count, missing-price count, failed-signal count,
benchmark availability, BUY/SELL counts, sector concentration. A run failing any
hard gate is marked non-tradable (status stays `partial`/`failed`); L2 and forward
IC consume only `complete`, gated runs.

## Implementation sketch

- New migration: the two tables above.
- Writer: the daily/full `fast_intraday` (or a thin post-step) writes ONE
  `research_run` + its `rating_snapshot` rows after the run completes, copying the
  exact emitted payload (do not recompute downstream).
- The picks API can keep serving from the live tables; the ledger is the immutable
  record alongside, not a replacement for the read path.
- Persist `registry_hash` / `weight_policy_id` / `tier_threshold_version` so a
  snapshot is fully reproducible and drift is detectable.

## Verification

- Re-running the writer for the same date does NOT mutate an existing `complete`
  run (append-only invariant test).
- A snapshot's `user_visible_payload_json` round-trips to what the picks endpoint
  served that day (golden check on a seeded run).
- Gated runs: a synthetic bad run (e.g. half the universe missing prices) is marked
  non-tradable and excluded from the L2 / forward-IC consumers.

## Non-goals

- Not a dashboard (that is L2, step 6). The first deliverable is the ledger + gates.
- Not changing the live read path or any signal's numeric output.
