-- A populated benchmark_close alone did not distinguish a verified XNYS close
-- from an intraday quote. Track close provenance on future writes only.
ALTER TABLE sim_equity_daily ADD COLUMN IF NOT EXISTS benchmark_close_at timestamptz;
