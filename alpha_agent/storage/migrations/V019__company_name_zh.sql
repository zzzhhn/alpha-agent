-- alpha_agent/storage/migrations/V019__company_name_zh.sql (2026-05-31)
-- Chinese company name alongside the English `name`. Same offline-backfill
-- model as summary_zh: scripts/backfill_company_names_zh.py translates via the
-- local claude CLI and writes name_zh here. The /profile endpoint serves
-- name_zh when locale=zh and a value exists, else falls back to `name`.
--
-- Honest by design: companies with no established Chinese name keep their
-- English name (the backfill leaves name_zh NULL rather than inventing a
-- transliteration).

ALTER TABLE company_profiles
    ADD COLUMN IF NOT EXISTS name_zh text;
