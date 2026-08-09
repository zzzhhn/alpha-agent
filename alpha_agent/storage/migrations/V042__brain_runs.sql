-- BRAIN mining runs are first-class objects.  A run is the stable parent for
-- every candidate persisted by one manual or scheduled mining invocation.
CREATE TABLE IF NOT EXISTS brain_runs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'schedule', 'legacy')),
    family_focus TEXT,
    requested_n INTEGER NOT NULL DEFAULT 0 CHECK (requested_n >= 0),
    generated_n INTEGER NOT NULL DEFAULT 0 CHECK (generated_n >= 0),
    screened_n INTEGER NOT NULL DEFAULT 0 CHECK (screened_n >= 0),
    simulated_n INTEGER NOT NULL DEFAULT 0 CHECK (simulated_n >= 0),
    persisted_n INTEGER NOT NULL DEFAULT 0 CHECK (persisted_n >= 0),
    passed_n INTEGER NOT NULL DEFAULT 0 CHECK (passed_n >= 0),
    flagged_n INTEGER NOT NULL DEFAULT 0 CHECK (flagged_n >= 0),
    rejected_n INTEGER NOT NULL DEFAULT 0 CHECK (rejected_n >= 0),
    sim_error_n INTEGER NOT NULL DEFAULT 0 CHECK (sim_error_n >= 0),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    screen_status TEXT NOT NULL DEFAULT 'pending',
    screen_detail TEXT,
    seed BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_detail TEXT,
    github_run_id TEXT,
    -- Kept only for compatibility/backfill lookup.  New callers also set this
    -- to their round anchor so old batch_started_at tooling still works.
    batch_started_at TIMESTAMPTZ,
    legacy_batch_started_at TIMESTAMPTZ,
    UNIQUE (user_id, source, legacy_batch_started_at)
);

CREATE INDEX IF NOT EXISTS idx_brain_runs_user_created
    ON brain_runs (user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_brain_runs_user_status
    ON brain_runs (user_id, status, created_at DESC);

ALTER TABLE brain_alphas
    ADD COLUMN IF NOT EXISTS run_id BIGINT
        REFERENCES brain_runs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_brain_alphas_user_run
    ON brain_alphas (user_id, run_id, created_at DESC, id DESC);

-- Rows written before the run ledger were grouped by batch_started_at.  Preserve
-- those groups as completed legacy runs and attach each row to its parent.  The
-- unique legacy key makes this block safe if a migration is re-applied manually.
INSERT INTO brain_runs (
    user_id, source, requested_n, generated_n, screened_n, simulated_n,
    persisted_n, passed_n, flagged_n, rejected_n, sim_error_n,
    status, screen_status, screen_detail, created_at, queued_at, started_at,
    completed_at, updated_at, batch_started_at, legacy_batch_started_at
)
SELECT
    a.user_id,
    'legacy',
    count(*)::integer,
    count(*)::integer,
    count(*)::integer,
    count(*)::integer,
    count(*)::integer,
    count(*) FILTER (WHERE a.outcome = 'passed')::integer,
    count(*) FILTER (WHERE a.outcome = 'flagged')::integer,
    count(*) FILTER (WHERE a.outcome = 'rejected')::integer,
    count(*) FILTER (WHERE a.outcome = 'sim_error')::integer,
    'completed',
    'legacy',
    'Backfilled from brain_alphas.batch_started_at',
    min(a.batch_started_at),
    min(a.batch_started_at),
    min(a.batch_started_at),
    max(a.created_at),
    max(a.created_at),
    min(a.batch_started_at),
    a.batch_started_at
FROM brain_alphas AS a
WHERE a.batch_started_at IS NOT NULL
GROUP BY a.user_id, a.batch_started_at
ON CONFLICT (user_id, source, legacy_batch_started_at) DO NOTHING;

UPDATE brain_alphas AS a
SET run_id = r.id
FROM brain_runs AS r
WHERE a.run_id IS NULL
  AND a.batch_started_at IS NOT NULL
  AND r.user_id = a.user_id
  AND r.source = 'legacy'
  AND r.legacy_batch_started_at = a.batch_started_at;
