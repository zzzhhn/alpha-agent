-- Spec §7.1: alpha-agent v4 Phase 1 initial schema.

CREATE TABLE IF NOT EXISTS daily_signals_slow (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    composite_partial DOUBLE PRECISION,
    breakdown JSONB,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS daily_signals_fast (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    composite DOUBLE PRECISION,
    rating TEXT,
    confidence DOUBLE PRECISION,
    breakdown JSONB,
    partial BOOLEAN DEFAULT false,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS alert_queue (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    dedup_bucket BIGINT NOT NULL,
    dispatched BOOLEAN DEFAULT false,
    UNIQUE (ticker, type, dedup_bucket)
);
CREATE INDEX IF NOT EXISTS idx_alert_queue_pending
    ON alert_queue (dispatched, created_at) WHERE dispatched = false;

CREATE TABLE IF NOT EXISTS cron_runs (
    id BIGSERIAL PRIMARY KEY,
    cron_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    ok BOOLEAN,
    error_count INT DEFAULT 0,
    details JSONB
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_recent
    ON cron_runs (cron_name, started_at DESC);

CREATE TABLE IF NOT EXISTS error_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT now(),
    layer TEXT NOT NULL,
    component TEXT NOT NULL,
    ticker TEXT,
    err_type TEXT,
    err_message TEXT,
    context JSONB
);
CREATE INDEX IF NOT EXISTS idx_error_log_recent ON error_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_log_component ON error_log (component, ts DESC);

-- Schema version tracker (so runner can be idempotent across re-runs)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now()
);
