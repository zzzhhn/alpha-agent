-- alpha_agent/storage/migrations/V014__engine_config.sql (2026-05-22)
--
-- Phase 2-pre: runtime-configurable engine knobs. One row per knob; value is
-- JSONB so a knob can hold a scalar (no_trade_band) or an object
-- (tier_thresholds). The live value lives here; the change history + rollback
-- journal stays in config_change_log (shared with the Phase 1b auto tier).
-- A missing key falls back to the hardcoded DEFAULTS in config_store.py.
CREATE TABLE IF NOT EXISTS engine_config (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by integer NOT NULL DEFAULT 0
);
