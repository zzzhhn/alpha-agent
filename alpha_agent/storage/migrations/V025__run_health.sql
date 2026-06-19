-- alpha_agent/storage/migrations/V025__run_health.sql (2026-06-19)
-- Run-health / abstention gates (roadmap step 2). Persist the gate verdict +
-- metrics alongside each run so "why was this run (non-)tradable" is auditable.
-- Tradability itself is encoded in research_run.status: a run that finished but
-- failed a hard gate is recorded as 'partial' (excluded by get_canonical_run),
-- so consumers (L2, forward-IC) automatically ignore it. health_json holds the
-- machine-readable detail: {passed, reasons[], metrics{eligible_count,
-- tier_counts, benchmark_fresh, ...}}. Empty default keeps V024 rows valid.
ALTER TABLE research_run
    ADD COLUMN IF NOT EXISTS health_json jsonb NOT NULL DEFAULT '{}'::jsonb;
