-- Phase F4: surface the full BRAIN in-sample metric set. brain_alphas stored
-- sharpe/fitness/turnover/drawdown; add the two WorldQuant IS Summary metrics
-- that were missing from the detail view — annual returns and margin (bps of
-- return per dollar traded). Additive, nullable (old rows stay valid).
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS returns DOUBLE PRECISION;
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS margin DOUBLE PRECISION;
