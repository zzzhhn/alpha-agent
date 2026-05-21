-- alpha_agent/storage/migrations/V011__daily_prices.sql (2026-05-21)
--
-- Daily-close price history for the universe. The forward-return leg of
-- the walk-forward IC engine reads this instead of minute_bars (which is
-- only a rolling 7-day cache and so cannot serve 30/60/90-day windows).
-- One row per ticker per trading day; the IC engine derives the forward
-- 5 trading-day return via LEAD(close, 5) over (ticker ordered by date).
-- The PRIMARY KEY (ticker, date) implicitly creates a unique B-tree index on
-- those columns, which already serves both the PK equality lookups and the
-- IC engine's LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) scan.
-- No separate index is needed.
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker text NOT NULL,
    date date NOT NULL,
    close double precision NOT NULL,
    PRIMARY KEY (ticker, date)
);
