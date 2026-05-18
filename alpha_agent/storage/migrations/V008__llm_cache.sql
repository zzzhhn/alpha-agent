-- V008__llm_cache.sql (2026-05-19)
--
-- Per-user LLM response cache. BYOK trust model means cache rows are
-- strictly user-scoped: two users hashing identical inputs still get
-- isolated rows (different api_key implies different model wallet,
-- different rate-limit ceiling, and ethically the response must be
-- attributable to the user that paid for it).
--
-- Cache lookup keys on a sha256 of (model | message-list | caller-variant)
-- — variant lets the caller fold as_of_date, ticker, or any other dim
-- into the key so a Rich Brief regenerated tomorrow gets a fresh hash
-- without polluting today's hit-rate.
--
-- expires_at is set per-write (24h intraday default; 7d EOD reports);
-- a sweep job (or just lazy filter on read) discards stale rows.
CREATE TABLE IF NOT EXISTS llm_cache (
    hash text NOT NULL,
    user_id integer NOT NULL,
    model text NOT NULL,
    response text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (hash, user_id)
);

CREATE INDEX IF NOT EXISTS idx_llm_cache_user_created
    ON llm_cache (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_cache_expires
    ON llm_cache (expires_at);
