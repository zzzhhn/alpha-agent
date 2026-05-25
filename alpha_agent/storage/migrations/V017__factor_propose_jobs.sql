-- alpha_agent/storage/migrations/V017__factor_propose_jobs.sql (2026-05-26)
-- Phase D: async propose job table to escape long-fetch fragility under
-- China-egress + local TUN proxy. POST /api/factor-lab/propose now writes
-- a queued row here and returns 202 with the job_id; a FastAPI background
-- task picks it up, runs the LLM + validation + scoring loop, and updates
-- the row in-place. Frontend polls GET /api/factor-lab/jobs/{id} every 3s.
--
-- State machine: queued -> running -> done | failed
--   result_json populated on done (the same shape the old sync POST
--   returned: {evaluated, proposed, dormant, _diag}).
--   error populated on failed (raw exception summary).
--
-- Retention: no auto-cleanup yet. If table grows, add a daily cron to
-- delete rows older than 7 days where status in ('done', 'failed').

CREATE TABLE IF NOT EXISTS factor_propose_jobs (
    id              text PRIMARY KEY,
    user_id         bigint NOT NULL,
    status          text NOT NULL DEFAULT 'queued'
                       CHECK (status IN ('queued', 'running', 'done', 'failed')),
    n               int NOT NULL DEFAULT 5,
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    result_json     jsonb,
    error           text
);

CREATE INDEX IF NOT EXISTS idx_factor_propose_jobs_user_created
    ON factor_propose_jobs (user_id, created_at DESC);
