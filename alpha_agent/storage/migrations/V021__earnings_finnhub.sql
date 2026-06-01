-- Precomputed earnings-surprise inputs per ticker (Finnhub), so the earnings
-- signal can compute its PEAD z without a live yfinance call (which returned
-- usable data for only ~21/557 tickers). Populated by a daily GitHub Actions
-- job (scripts/ingest_earnings_finnhub.py); the signal crons read this table.
--
-- recent_surprise: (actual - estimate) / |estimate| of the most recent reported
--   quarter (relative SUE numerator).
-- sigma: Foster-Olsen-Shevlin rolling std of the last 4 quarters' relative
--   surprise, floored at 0.05 (SUE denominator).
-- report_date: the most recent reported quarter's period (for proximity decay).
-- next_date / eps_estimate / revenue_estimate: upcoming earnings (UI card).
CREATE TABLE IF NOT EXISTS earnings_finnhub (
    ticker           TEXT PRIMARY KEY,
    recent_surprise  DOUBLE PRECISION,
    sigma            DOUBLE PRECISION,
    report_date      DATE,
    next_date        DATE,
    eps_estimate     DOUBLE PRECISION,
    revenue_estimate DOUBLE PRECISION,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
