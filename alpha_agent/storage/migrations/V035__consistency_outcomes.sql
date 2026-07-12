-- Durable per-(ticker, date) directional outcomes for the picks consistency
-- metric. Each row = one REALIZED, DIRECTIONAL prediction (HOLD / not-yet-
-- realized are simply absent), so window hit-rates = SUM(hit)/COUNT over the
-- trailing window. This makes 历史一致性 immune to raw-signal pruning: 90% of
-- historical consistency currently depends on daily_signals_slow, which has no
-- retention and is the prime target of the next manual disk cleanup. Storing the
-- verdict (not the signals) lets slow/fast be pruned without losing history.
-- Sizing: ~558 tickers x ~252 trading days/yr ~= 8-10 MB/yr incl. index —
-- trivial against the 512 MB budget.
CREATE TABLE IF NOT EXISTS consistency_outcomes (
    ticker text  NOT NULL,
    date   date  NOT NULL,
    hit    boolean NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_consistency_outcomes_date
    ON consistency_outcomes (date);
