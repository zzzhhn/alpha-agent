-- alpha_agent/storage/migrations/V006__impact_direction_buckets.sql
--
-- Phase 6a Task 5 schema gap: news_items and macro_events need discrete
-- LLM-as-Judge bucket columns so the news + political_impact signals can
-- run Tetlock-style impact * direction aggregation instead of averaging a
-- continuous sentiment_score (which conflates magnitude and direction).
--
-- impact_bucket  text in {none, low, medium, high}  (NULL = not LLM-tagged yet)
-- direction_bucket text in {bullish, bearish, neutral} (NULL = not LLM-tagged yet)
--
-- Both nullable so the LM dictionary fallback (Loughran-McDonald) can
-- still produce a signal for rows the LLM enrichment cron has not yet
-- processed. Tier transitions to LLM tags as the cron catches up.

ALTER TABLE news_items
    ADD COLUMN IF NOT EXISTS impact_bucket text,
    ADD COLUMN IF NOT EXISTS direction_bucket text;

ALTER TABLE macro_events
    ADD COLUMN IF NOT EXISTS impact_bucket text,
    ADD COLUMN IF NOT EXISTS direction_bucket text;
