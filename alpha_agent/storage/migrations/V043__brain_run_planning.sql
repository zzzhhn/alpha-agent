-- P1/P2 BRAIN planning metadata.  Keep the real simulation budget
-- (requested_n) separate from the cheap expression-generation pool, and retain
-- the source run when a researcher deliberately reuses a prior configuration.
ALTER TABLE brain_runs
    ADD COLUMN IF NOT EXISTS generation_target_n INTEGER NOT NULL DEFAULT 0
        CHECK (generation_target_n >= 0),
    ADD COLUMN IF NOT EXISTS parent_run_id BIGINT
        REFERENCES brain_runs(id) ON DELETE SET NULL;

UPDATE brain_runs
SET generation_target_n = GREATEST(generated_n, requested_n)
WHERE generation_target_n = 0;

CREATE INDEX IF NOT EXISTS idx_brain_runs_parent
    ON brain_runs (parent_run_id)
    WHERE parent_run_id IS NOT NULL;
