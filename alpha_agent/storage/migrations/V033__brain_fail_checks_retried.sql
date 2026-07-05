-- Surface WHY a factor was rejected and whether settings-tuning was attempted:
--   fail_checks = comma-separated failing in-sample checks (LOW_SHARPE,
--                 HIGH_TURNOVER, ...) for rejected rows; NULL for passers.
--   retried     = a settings-adaptation retry sim was run for this candidate.
-- Additive, nullable (old rows valid).
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS fail_checks TEXT;
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS retried BOOLEAN NOT NULL DEFAULT FALSE;
