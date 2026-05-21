-- alpha_agent/storage/migrations/V013__confidence_calibration.sql (2026-05-21)
--
-- Phase 1c: stores the fitted confidence->realized-hit-rate isotonic map plus
-- the reliability/Brier diagnostics, one row per calibration run (the daily
-- cron appends a fresh row). The live read path loads the most recent row and
-- passes displayed confidence through isotonic_map (suppress-overconfidence
-- only). applied=false rows are diagnostics-only (e.g. below the min-sample
-- threshold) and must NOT be used to recalibrate.
CREATE TABLE IF NOT EXISTS confidence_calibration (
    id bigserial PRIMARY KEY,
    as_of timestamptz NOT NULL DEFAULT now(),
    isotonic_map jsonb NOT NULL,
    buckets jsonb NOT NULL,
    n_pairs integer NOT NULL,
    applied boolean NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_confidence_calibration_as_of
    ON confidence_calibration (as_of DESC);
