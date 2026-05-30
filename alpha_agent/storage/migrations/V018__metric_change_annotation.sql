-- alpha_agent/storage/migrations/V018__metric_change_annotation.sql (2026-05-31)
-- Traceability (UI/UX principle 11): record WHY a tracked metric changed
-- day-over-day, grounded in real co-occurring events rather than speculation.
-- P0 covers signal IC; metric_type leaves room for 'calibration' / 'weight'.
--
-- Stores STRUCTURED facts (prev/curr/delta/sign_flip + co_occurring jsonb),
-- not prose — the frontend templates the sentence in the user's locale, so
-- annotations are bilingual for free and never carry a fabricated causal
-- claim (only what actually co-occurred).
--
-- co_occurring is a list of typed events, e.g.
--   [{"type": "weight_change", "source": "auto_rollback", "change_id": 42}]
-- An empty list is meaningful: the change had no recorded system cause
-- (market-driven), which is itself worth surfacing.

CREATE TABLE IF NOT EXISTS metric_change_annotation (
    id            bigserial PRIMARY KEY,
    metric_type   text NOT NULL,          -- 'signal_ic' (P0)
    metric_key    text NOT NULL,          -- signal_name for signal_ic
    window_days   int,                    -- IC rolling window this belongs to
    as_of         timestamptz NOT NULL,   -- computed_at of the changed point
    prev_value    numeric(10, 5),
    curr_value    numeric(10, 5),
    delta         numeric(10, 5),
    sign_flip     boolean NOT NULL DEFAULT false,
    co_occurring  jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (metric_type, metric_key, window_days, as_of)
);

CREATE INDEX IF NOT EXISTS idx_metric_change_annotation_lookup
    ON metric_change_annotation (metric_type, window_days, as_of DESC);
