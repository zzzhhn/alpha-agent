-- P0: durable audit ledger for every expression generated for a BRAIN run.
--
-- ``brain_alphas`` remains the simulation-outcome table.  This table is written
-- before the optional LLM/evidence screen so withheld candidates are not lost,
-- and is updated as the candidate moves through screening and simulation.
CREATE TABLE IF NOT EXISTS brain_run_candidates (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES brain_runs(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    expression TEXT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    mechanism TEXT,
    evidence JSONB,
    evidence_score DOUBLE PRECISION,
    llm_score DOUBLE PRECISION,
    llm_status TEXT NOT NULL DEFAULT 'pending',
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    -- stage advances generated -> screened -> simulation; status keeps the
    -- screen decision (generated/selected/withheld) stable for API filters.
    stage TEXT NOT NULL DEFAULT 'generated',
    status TEXT NOT NULL DEFAULT 'generated',
    reason_code TEXT,
    reason_text TEXT,
    alpha_row_id BIGINT REFERENCES brain_alphas(id) ON DELETE SET NULL,
    alpha_id TEXT,
    simulation_outcome TEXT,
    simulation_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    screened_at TIMESTAMPTZ,
    simulated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, expression)
);

CREATE INDEX IF NOT EXISTS idx_brain_run_candidates_run_ordinal
    ON brain_run_candidates (run_id, ordinal, id);
CREATE INDEX IF NOT EXISTS idx_brain_run_candidates_run_selected
    ON brain_run_candidates (run_id, selected, ordinal);
CREATE INDEX IF NOT EXISTS idx_brain_run_candidates_run_status
    ON brain_run_candidates (run_id, status, ordinal);
