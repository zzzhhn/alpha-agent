-- alpha_agent/storage/migrations/V024__product_ledger.sql (2026-06-19)
-- Append-only product ledger: the engine's causal memory of what it believed
-- when. daily_signals_fast is UPSERTed (overwritten) and daily_prices is
-- auto-adjusted, so any later backtest / paper-trade marks against a revised
-- past. This ledger records, immutably, WHAT a run was (provenance) and WHAT
-- the user actually saw (the emitted picks), so honest forward IC, L2
-- paper-trading, drift detection, and tier monotonicity become possible.
--
-- APPEND-ONLY CONTRACT (enforced by the writer, alpha_agent/storage/
-- product_ledger.py, not by a destructive DB trigger): rows are only ever
-- INSERTed. A correction is a NEW run id; the old run is never mutated. There
-- is intentionally NO unique index on (scheduled_for_date, run_type) WHERE
-- status='complete' -- that would block corrections, which legitimately add a
-- second complete run for the same date. The "one canonical run per market
-- date" rule is resolved at read time: the latest finished_at among complete
-- runs (see product_ledger.get_canonical_run). The duplicate-complete guard
-- (refuse an accidental cron double-fire) lives in the writer with an explicit
-- allow_correction opt-in.

CREATE TABLE IF NOT EXISTS research_run (
    id                      bigserial PRIMARY KEY,
    scheduled_for_date      date NOT NULL,        -- the market date this run is FOR
    run_type                text NOT NULL DEFAULT 'daily_close',
    -- lifecycle: started -> partial|complete|failed; corrected = a later run
    -- that supersedes an earlier one for the same date (still a new id).
    status                  text NOT NULL
        CHECK (status IN ('started', 'partial', 'complete', 'failed', 'corrected')),
    started_at              timestamptz NOT NULL,
    finished_at             timestamptz,
    data_asof               timestamptz,          -- latest input data timestamp
    input_data_cutoff       timestamptz,          -- point-in-time cutoff used
    code_version            text,                 -- git sha that produced the run
    registry_hash           text,                 -- hash of the signal registry (step 3)
    weight_policy_id        text,                 -- which WeightPolicy was live
    tier_threshold_version  text,                 -- tier breakpoints version
    created_at              timestamptz NOT NULL DEFAULT now()
);

-- Canonical-run lookup: newest complete run per (date, run_type). Covers the
-- get_canonical_run query (filter by date+type+status, order by finished_at).
CREATE INDEX IF NOT EXISTS idx_research_run_canonical
    ON research_run (scheduled_for_date, run_type, status, finished_at DESC);

CREATE TABLE IF NOT EXISTS rating_snapshot (
    id                        bigserial PRIMARY KEY,
    run_id                    bigint NOT NULL REFERENCES research_run (id),
    ticker                    text NOT NULL,
    in_universe               boolean NOT NULL DEFAULT true,
    eligible                  boolean NOT NULL DEFAULT true,
    eligibility_reason        text,               -- why dropped, e.g. 'dead_price_feed'
    composite_z               double precision,
    rank                      int,                -- position in the emitted ranking
    tier                      text,               -- BUY/OW/HOLD/UW/SELL the user saw
    coverage                  double precision,   -- core-signal coverage at fusion
    effective_weight_json     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- weights actually applied
    user_visible_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the exact LeanCard the user saw
    price_source              text,               -- 'yfinance'
    price_downloaded_at       timestamptz,
    adjustment_mode           text,               -- 'adjusted'
    feed_status               text,               -- 'fresh' | 'stale' | 'dead'
    -- One snapshot per ticker per run. Within a run a ticker is unique; a
    -- correction reuses neither (it has its own run id), so this never blocks
    -- the append-only correction path.
    UNIQUE (run_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_rating_snapshot_run
    ON rating_snapshot (run_id);
-- forward-IC / per-ticker history reads scan by ticker across runs.
CREATE INDEX IF NOT EXISTS idx_rating_snapshot_ticker
    ON rating_snapshot (ticker, run_id);
