-- #5: tag each mined row with the round (batch) that produced it, so the review
-- UI can draw a divider between consecutive batches and show the batch's start
-- time on hover. Set once at round start (DB clock), same for every row of that
-- round. Additive, nullable — old rows form a single "legacy" group.
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS batch_started_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_brain_alphas_batch
  ON brain_alphas (user_id, batch_started_at DESC);
