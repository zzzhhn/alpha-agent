-- Phase E4: results of a WorldQuant BRAIN mining round. Each row is one
-- generated FASTEXPR alpha that was simulated on BRAIN, with its real in-sample
-- metrics + self-correlation and a bucket outcome. The UI (E5) surfaces
-- outcome='passed'/'flagged' for the user to review and submit; submit is
-- user-driven, so submitted_at/brain_status stay null until they act.
CREATE TABLE IF NOT EXISTS brain_alphas (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    expression TEXT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    alpha_id TEXT,                          -- BRAIN's alpha id (null if sim failed)
    sharpe DOUBLE PRECISION,
    fitness DOUBLE PRECISION,
    turnover DOUBLE PRECISION,
    drawdown DOUBLE PRECISION,
    self_correlation DOUBLE PRECISION,
    self_correlation_with TEXT,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('passed', 'flagged', 'rejected', 'sim_error')
    ),
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at TIMESTAMPTZ,
    brain_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_brain_alphas_user
    ON brain_alphas (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_brain_alphas_outcome
    ON brain_alphas (user_id, outcome);
