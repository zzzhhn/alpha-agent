-- Phase 4b: multi-method auth (email+password Credentials provider + Google
-- OAuth) and self-serve password reset. Purely additive: one ADD COLUMN IF
-- NOT EXISTS (nullable, no table rewrite) plus three CREATE TABLE IF NOT
-- EXISTS. Zero-downtime, rollback-safe. Spec 2026-05-14-phase4b section
-- "Data model: V003 migration".

-- 1. users.password_hash: nullable. Google-only users have no password,
--    password-only users have no linked OAuth account. bcryptjs hash, cost 12.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- 2. accounts: NextAuth @auth/pg-adapter standard schema. V002 skipped this
--    table because email-only login never called linkAccount /
--    getUserByAccount. Adding the Google provider makes those adapter methods
--    live. Column names use the adapter's double-quoted camelCase identifiers
--    EXACTLY (audited against node_modules/@auth/pg-adapter, the G2 lesson).
--    Adapter INSERT order (from node_modules audit): userId, provider, type,
--    providerAccountId, access_token, expires_at, refresh_token, id_token,
--    scope, session_state, token_type.
CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    "userId" BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    provider TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    refresh_token TEXT,
    access_token TEXT,
    expires_at BIGINT,
    token_type TEXT,
    scope TEXT,
    id_token TEXT,
    session_state TEXT,
    UNIQUE (provider, "providerAccountId")
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts ("userId");

-- 3. password_reset_codes: 6-digit code stored bcryptjs-hashed (never
--    plaintext), 15-min TTL via expires_at, single-use via the used flag.
--    NOT FK'd to users: a reset can be requested for an email before we
--    confirm a user row exists, and we must not leak user existence.
CREATE TABLE IF NOT EXISTS password_reset_codes (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_password_reset_codes_email
    ON password_reset_codes (email);

-- 4. auth_rate_limit: Postgres-backed sliding-window rate limiting (chosen
--    over Upstash Redis to avoid a new service at personal scale). bucket_key
--    is "<action>:<ip>" or "<action>:<email>"; the checkRateLimit helper
--    upserts the current window row and rejects when hit_count exceeds the
--    per-action limit. Cleanup is cheap: a periodic
--    DELETE FROM auth_rate_limit WHERE window_start < now() - interval '1 day'
--    (no cron in this phase, the row count is tiny at personal scale).
CREATE TABLE IF NOT EXISTS auth_rate_limit (
    bucket_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_key, window_start)
);

-- V002 leftover: verification_token (the magic-link table) is unused as of
-- V003 once the Nodemailer provider is removed from auth.ts. Left in place,
-- dropping an empty table is a migration with no benefit.
