-- Precomputed insider (SEC EDGAR Form 4) net trading value per ticker.
-- Populated by a separate ingestion job (scripts/ingest_insider_form4.py, run
-- daily on GitHub Actions) because parsing Form 4 XML for the whole universe
-- needs thousands of rate-limited SEC requests, which does not fit the Vercel
-- 300s cron budget. The slow/fast signal crons read this table (no SEC calls
-- on the signal path) and the insider signal grades from net_value.
CREATE TABLE IF NOT EXISTS insider_form4 (
    ticker      TEXT PRIMARY KEY,
    net_value   DOUBLE PRECISION NOT NULL,  -- sum(+buys -sells), open-market P/S, last 30d
    n_filings   INTEGER NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
