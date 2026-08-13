-- P1/P2: persist the evidence used before a costly BRAIN simulation.
-- JSONB keeps the hypothesis registry, field mapping, posterior context, and
-- validated proxy output together without turning research features into a
-- wide, frequently changing table contract.
ALTER TABLE brain_alphas
    ADD COLUMN IF NOT EXISTS research_evidence JSONB;

CREATE INDEX IF NOT EXISTS idx_brain_alphas_research_context
    ON brain_alphas ((research_evidence->>'context_key'))
    WHERE research_evidence IS NOT NULL;
