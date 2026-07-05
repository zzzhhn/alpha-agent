-- BRAIN grades every alpha with a performance tier (SPECTACULAR / EXCELLENT /
-- GOOD / AVERAGE / INFERIOR / POOR). Store it so a mined factor's grade shows on
-- the review UI without re-fetching. Additive, nullable (old rows stay valid).
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS grade TEXT;
