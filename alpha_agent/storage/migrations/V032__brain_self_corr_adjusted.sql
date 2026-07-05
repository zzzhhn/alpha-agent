-- Two self-correlations per mined alpha, side by side:
--   self_correlation      = BRAIN's OFFICIAL value (vs the user's ACTIVE alphas).
--   self_correlation_adj  = our recomputed value that ALSO counts the successful-
--                           but-not-yet-submitted mined factors (which BRAIN can't
--                           see). Reconciled after each round so an early passer
--                           reflects later ones. Additive, nullable (old rows valid).
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS self_correlation_adj DOUBLE PRECISION;
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS self_correlation_adj_with TEXT;
