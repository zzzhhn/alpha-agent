-- alpha_agent/storage/migrations/V005__signal_ic_and_minute_bars.sql
--
-- Phase 6a foundation: minute-level price storage for event-study CAR
-- calculation, plus IC history + current weight registry for the dynamic
-- weight engine that decides which signals contribute to picks composite.

CREATE TABLE IF NOT EXISTS minute_bars (
  ticker text NOT NULL,
  ts timestamptz NOT NULL,
  open numeric(12, 4),
  high numeric(12, 4),
  low numeric(12, 4),
  close numeric(12, 4),
  volume bigint,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_ticker_ts
  ON minute_bars (ticker, ts DESC);

CREATE TABLE IF NOT EXISTS signal_ic_history (
  signal_name text NOT NULL,
  window_days integer NOT NULL,
  ic numeric(8, 5) NOT NULL,
  n_observations integer NOT NULL,
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (signal_name, window_days, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_signal_ic_history_signal_computed
  ON signal_ic_history (signal_name, computed_at DESC);

CREATE TABLE IF NOT EXISTS signal_weight_current (
  signal_name text PRIMARY KEY,
  weight numeric(6, 4) NOT NULL,
  last_updated timestamptz NOT NULL,
  reason text
);
