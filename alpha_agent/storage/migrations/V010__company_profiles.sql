-- V010__company_profiles.sql (2026-05-20)
--
-- Persistent cache for the stock-detail "About" card so the company
-- profile is fetched from yfinance ONCE per ticker, then served from the
-- DB instead of re-scraping on every page view.
--
-- Bilingual: summary_en is the verbatim yfinance longBusinessSummary;
-- summary_zh is a Chinese translation backfilled offline (the platform
-- holds no global LLM key, so translation runs as a local script via the
-- claude CLI and writes summary_zh here). The /profile endpoint serves
-- summary_zh when present + locale=zh, else falls back to summary_en.
CREATE TABLE IF NOT EXISTS company_profiles (
    ticker text PRIMARY KEY,
    name text,
    sector text,
    industry text,
    summary_en text,
    summary_zh text,
    website text,
    country text,
    employees integer,
    -- when the yfinance pull last populated EN fields
    fetched_at timestamptz NOT NULL DEFAULT now(),
    -- when summary_zh was last backfilled (NULL = not yet translated)
    translated_at timestamptz
);
