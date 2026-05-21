-- alpha_agent/storage/migrations/V011__daily_prices.sql (2026-05-21)
--
-- Daily-close price history for the universe. The forward-return leg of
-- the walk-forward IC engine reads this instead of minute_bars (which is
-- only a rolling 7-day cache and so cannot serve 30/60/90-day windows).
-- One row per ticker per trading day; the IC engine derives the forward
-- 5 trading-day return via LEAD(close, 5) over (ticker ordered by date).
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker text NOT NULL,
    date date NOT NULL,
    close double precision NOT NULL,
    PRIMARY KEY (ticker, date)
);

-- The IC query windows by ticker ordered by date; this index serves both
-- the PK lookups and the window scan.
CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date
    ON daily_prices (ticker, date);
