-- Phase 4 (M5): user-scoped tables for multi-user auth + server-side BYOK.
-- Purely additive: no existing table is altered. Cascade delete on user_id
-- gives account-deletion atomicity. Spec 2026-05-14-phase4 section 3.1.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    -- NextAuth.js v5 Email provider expects these column names verbatim.
    email_verified TIMESTAMPTZ,
    name TEXT,
    image TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    locale TEXT NOT NULL DEFAULT 'zh',
    theme TEXT NOT NULL DEFAULT 'dark',
    extras JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_watchlist (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_user_watchlist_user ON user_watchlist (user_id);

CREATE TABLE IF NOT EXISTS user_byok (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    last4 TEXT NOT NULL,
    model TEXT,
    base_url TEXT,
    encrypted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    encrypted_with_key_id INT NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_user_byok_user ON user_byok (user_id);

-- NextAuth.js v5 standard table for email magic-link tokens.
CREATE TABLE IF NOT EXISTS verification_tokens (
    identifier TEXT NOT NULL,
    token TEXT NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);
