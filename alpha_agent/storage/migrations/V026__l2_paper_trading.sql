-- alpha_agent/storage/migrations/V026__l2_paper_trading.sql (2026-06-20)
-- Minimal causal L2 forward paper-trading (roadmap step 6). Built ON TOP of the
-- product ledger (V024/V025): orders are generated from a PRIOR immutable
-- rating_snapshot and persisted BEFORE any execution price is consumed, so the
-- forward equity curve is look-ahead-free by construction. No real money.
--
-- Honesty (council): report gross AND net; orders carry the source_run_id +
-- generated_at proving they predate the fill; a held position with a killed
-- feed produces an explicit exit event, never a silent disappearance.

-- The frozen, versioned ruleset (top-N, weighting, costs, benchmark, ...).
CREATE TABLE IF NOT EXISTS l2_strategy (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    version     int  NOT NULL DEFAULT 1,
    params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);

-- One target holding, generated from a prior snapshot, persisted pre-execution.
CREATE TABLE IF NOT EXISTS l2_order (
    id            bigserial PRIMARY KEY,
    strategy_id   bigint NOT NULL REFERENCES l2_strategy (id),
    source_run_id bigint NOT NULL REFERENCES research_run (id),  -- the snapshot that produced it
    signal_date   date NOT NULL,        -- close D: when the signal was emitted
    ticker        text NOT NULL,
    target_weight double precision NOT NULL,
    rank          int,
    tier          text,
    generated_at  timestamptz NOT NULL, -- proves the order predates the fill read
    fill_date     date,                 -- D+1 (set at fill time)
    fill_price    double precision,     -- read at fill time, strictly after generated_at
    cost_bps      double precision,
    status        text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'filled', 'exited', 'unfilled')),
    exit_reason   text,                 -- e.g. 'dead_feed' for a forced exit
    UNIQUE (strategy_id, signal_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_l2_order_strategy_date
    ON l2_order (strategy_id, signal_date);

-- Daily marked equity + benchmark + honesty metrics. One row per mark date.
CREATE TABLE IF NOT EXISTS l2_equity_daily (
    id               bigserial PRIMARY KEY,
    strategy_id      bigint NOT NULL REFERENCES l2_strategy (id),
    as_of_date       date NOT NULL,      -- the fill / mark date
    gross_return     double precision,
    net_return       double precision,   -- after costs
    benchmark_return double precision,   -- SPY adjusted return
    turnover         double precision,
    n_positions      int,
    stale_count      int NOT NULL DEFAULT 0,
    missing_count    int NOT NULL DEFAULT 0,
    cost_bps         double precision,   -- the per-side cost used for net
    marked_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (strategy_id, as_of_date)
);
