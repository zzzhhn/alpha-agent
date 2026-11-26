-- Keep dated comparison evidence separate from the options research payload.
-- Legacy rows are NULL until a dated comparison is recorded.
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS diversity_evidence JSONB;
