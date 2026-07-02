-- alpha_agent/storage/migrations/V027__factor_lessons.sql (2026-07-02)
-- Phase A of the self-evolving factor miner: a persistent experiment journal
-- (the "memory layer" from Loop Engineering / the evolve_skill.py idea).
--
-- Every candidate the propose loop evaluates writes ONE distilled lesson here:
--   outcome='accepted'  a survivor worth extending  (KEEP ...)
--   outcome='weak'      evaluated but below the keep gate  (WEAK ...)
--   outcome='rejected'  failed validation / degenerate     (AVOID ...)
--
-- The proposer then reads back the recent lessons + the distinct set of
-- already-tried expressions and injects them into its prompt, so it stops
-- re-proposing the same structures and adjusts direction over time. Without
-- this table each propose run is stateless — a screenshot, not a trajectory.
--
-- Retention: no auto-cleanup yet. If it grows, a daily cron can trim rows
-- older than ~90 days (lessons are cheap; keep a long memory by default).

CREATE TABLE IF NOT EXISTS factor_lessons (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expression      text NOT NULL,
    outcome         text NOT NULL
                       CHECK (outcome IN ('accepted', 'weak', 'rejected')),
    test_sharpe     double precision,
    test_ic         double precision,
    deflated_sharpe double precision,
    reject_reason   text,
    operators_used  text[],
    lesson          text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_factor_lessons_created
    ON factor_lessons (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_factor_lessons_expression
    ON factor_lessons (expression);
