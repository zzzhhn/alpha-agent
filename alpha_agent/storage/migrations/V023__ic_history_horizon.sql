-- V023: per-horizon IC history (council 2026-06-17 item #4).
-- signal_ic_history previously stored IC at an implicit 5d forward horizon.
-- Add an explicit horizon_days so each signal can be validated at its native
-- horizon (factor 60d, news 3d, ...) in addition to the 5d reference. Existing
-- rows were all computed at 5d, so backfill the new column to 5.
ALTER TABLE signal_ic_history
  ADD COLUMN IF NOT EXISTS horizon_days integer NOT NULL DEFAULT 5;

-- Re-key on (signal_name, window_days, horizon_days, computed_at) so the same
-- signal+window can hold IC at multiple horizons computed in one run.
ALTER TABLE signal_ic_history DROP CONSTRAINT IF EXISTS signal_ic_history_pkey;
ALTER TABLE signal_ic_history
  ADD CONSTRAINT signal_ic_history_pkey
  PRIMARY KEY (signal_name, window_days, horizon_days, computed_at);
