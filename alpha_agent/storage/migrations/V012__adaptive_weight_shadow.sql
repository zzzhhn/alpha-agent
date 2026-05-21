-- alpha_agent/storage/migrations/V012__adaptive_weight_shadow.sql (2026-05-21)
--
-- Phase 1b shadow weighting. signal_weight_current must hold a 'live' row
-- (consumed by fusion.load_weights) AND a 'shadow' candidate row per signal,
-- so the PK widens from (signal_name) to (signal_name, status). Existing
-- rows default to status='live' so the Phase 1a writer and load_weights keep
-- working unchanged. consecutive_bad_windows drives the diversification
-- floor's hard-drop-after-N rule; shadow_streak drives the 5-day promotion.
ALTER TABLE signal_weight_current
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS consecutive_bad_windows integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS shadow_streak integer NOT NULL DEFAULT 0;

-- Widen the primary key to (signal_name, status). The old PK name is the
-- table-derived default; drop by that name then re-add the composite.
ALTER TABLE signal_weight_current
    DROP CONSTRAINT IF EXISTS signal_weight_current_pkey;
ALTER TABLE signal_weight_current
    ADD PRIMARY KEY (signal_name, status);
