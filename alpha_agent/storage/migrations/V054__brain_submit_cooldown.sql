-- Durable Retry-After for new BRAIN submission attempts. Existing receipts
-- are deliberately not changed: old failures cannot be classified retroactively.
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS submit_retry_at TIMESTAMPTZ;
