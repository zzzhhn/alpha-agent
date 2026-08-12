-- Make an absent official self-correlation truthful.  NULL alone could not
-- distinguish a lazy BRAIN computation from a check skipped after another
-- submission prerequisite failed.
ALTER TABLE brain_alphas
    ADD COLUMN IF NOT EXISTS self_correlation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (self_correlation_status IN (
            'pending', 'ready', 'skipped_prerequisite', 'unavailable'
        ));

UPDATE brain_alphas
SET self_correlation_status = CASE
    WHEN self_correlation IS NOT NULL THEN 'ready'
    WHEN alpha_id IS NULL THEN 'unavailable'
    WHEN outcome = 'rejected' AND fail_checks IS NOT NULL
        THEN 'skipped_prerequisite'
    ELSE 'pending'
END;

CREATE INDEX IF NOT EXISTS idx_brain_alphas_self_corr_pending
    ON brain_alphas (user_id, created_at DESC)
    WHERE self_correlation IS NULL AND alpha_id IS NOT NULL;
