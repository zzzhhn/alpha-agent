-- All times are UTC. These are feed records, not distinct economic events.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL TIME ZONE 'UTC';
WITH launch AS (SELECT min(started_at) AS at FROM cron_runs WHERE cron_name='tick_events_watch')
SELECT e.ticker,e.source,e.published_at,e.first_seen_at,r.observed_at AS last_evaluation,
       CASE WHEN at IS NULL THEN 'unknown_launch' WHEN e.published_at IS NULL THEN 'unknown_publication'
            WHEN e.published_at<at THEN 'prelaunch_publication' ELSE 'postlaunch_publication' END AS provenance,
       e.first_seen_at-e.published_at AS collection_lag,r.observed_at-e.first_seen_at AS time_to_last_evaluation,
       r.gap_reason,r.follow_reason
FROM official_event_reaction r JOIN official_event_watch e ON e.id=r.event_id CROSS JOIN launch
WHERE r.status='unavailable' ORDER BY e.first_seen_at;

-- A late observation may have a valid subsequent 30m relative move but no
-- contemporaneous overnight gap. Do not pool duplicate IR/SEC headlines.
SELECT e.id,e.ticker,e.source,e.title,e.published_at,e.first_seen_at,
       r.timing,r.status,r.gap->>'ticker_return' AS overnight_stock_return,
       r.gap->>'spy_return' AS overnight_spy_return,r.follow_through->>'anchor_at' AS anchor,
       r.follow_through->>'end_at' AS horizon,r.follow_through->>'excess_return' AS next_30m_vs_spy
FROM official_event_watch e LEFT JOIN official_event_reaction r ON e.id=r.event_id
WHERE e.kind='management_change' ORDER BY e.first_seen_at DESC,e.id DESC LIMIT 100;
COMMIT;
