-- Candidate list for the human daily-close valuation audit.
-- Legacy NAV has no per-position price provenance, even when its SPY close matches.
BEGIN READ ONLY;

SELECT e.account_id, e.cohort_id, e.as_of_date,
       e.portfolio_value IS NOT NULL AS nav_present,
       e.benchmark_close IS NOT NULL AS benchmark_present,
       e.valuation_quality IS NULL AS legacy_nav_unverified,
       CASE WHEN e.benchmark_close IS NOT NULL THEN
           CASE WHEN exact.close IS NULL THEN 'no_same_day_close'
                WHEN e.benchmark_close IS DISTINCT FROM exact.close THEN 'differs_from_same_day_close'
                WHEN e.benchmark_close_at IS NULL THEN 'no_recorded_provenance'
           END
       END AS benchmark_evidence_gap
FROM sim_equity_daily e
JOIN sim_account a ON a.id = e.account_id AND a.kind = 'human'
LEFT JOIN daily_prices exact ON exact.ticker = 'SPY' AND exact.date = e.as_of_date
    AND exact.close > 0 AND exact.close < 'Infinity'::double precision
WHERE e.valuation_quality IS NULL OR (
    e.benchmark_close IS NOT NULL AND (
        e.benchmark_close_at IS NULL OR e.benchmark_close IS DISTINCT FROM exact.close
    )
)
ORDER BY e.as_of_date, e.account_id, e.cohort_id;

ROLLBACK;
