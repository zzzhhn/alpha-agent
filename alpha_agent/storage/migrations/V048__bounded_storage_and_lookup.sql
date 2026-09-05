-- For WHERE ticker = ? ORDER BY ts DESC, minute_bars_pkey supports an
-- index scan backwards. The second B-tree duplicates it and its write cost.
-- No price rows are removed. Rollback: CREATE INDEX idx_minute_bars_ticker_ts
-- ON minute_bars(ticker, ts DESC).
DROP INDEX IF EXISTS idx_minute_bars_ticker_ts;

-- New invalid daily closes must not poison JSON snapshots or return ratios.
-- NOT VALID preserves historical rows for a separately reviewed repair;
-- PostgreSQL still checks all newly inserted/updated rows immediately.
ALTER TABLE daily_prices ADD CONSTRAINT daily_prices_close_valid
    CHECK (close > 0 AND close < 'Infinity'::double precision) NOT VALID;
