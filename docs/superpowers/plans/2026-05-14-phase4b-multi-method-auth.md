# Alpha-Agent v4 · Phase 4b · Multi-Method Auth (Password + Google OAuth) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two login methods to the alpha-agent frontend alongside the existing NextAuth.js v5 setup: email + password (NextAuth Credentials provider) and Google OAuth. Remove the email magic-link login path. Add a self-serve password-reset flow (6-digit emailed code). The FastAPI backend auth contract stays completely unchanged.

**Architecture:** The change is frontend-heavy plus a single backend migration (`V003`). NextAuth.js v5 in `auth.ts` gains a Credentials provider (with a Node-only `authorize()` callback that does a Postgres user lookup + bcryptjs compare) and a Google OAuth provider (`allowDangerousEmailAccountLinking: true`); the Nodemailer magic-link provider is removed. New `/register`, `/forgot-password`, and `/reset-password` pages each get a `"use server"` Server Action. All three login methods produce the same NextAuth session JWE the existing middleware re-mints into an HS256 JWS, so `auth.config.ts`, `middleware.ts`, and the entire FastAPI backend are untouched.

**Tech Stack:** Backend: Python 3.12, the existing migration runner (`alpha_agent/storage/migrations/runner.py`), pytest. Frontend: Next.js 16 App Router, `next-auth ^5.0.0-beta.31`, `@auth/pg-adapter ^1.11.2`, `pg`, `bcryptjs` (new), `zod ^4.3.6` (present), `nodemailer` (already a transitive dep, used directly for reset email), Tailwind `tm-*` tokens, `vitest` + `@vitejs/plugin-react` (new, first frontend test runner).

**Spec reference:** `docs/superpowers/specs/2026-05-14-phase4-multi-method-auth.md` - read it first; it is the authoritative design. This plan implements it task-by-task.

**Migration numbering note:** M5 shipped `V002__phase4_users.sql`. The correct next migration is therefore **`V003__phase4b_multi_auth.sql`**. The runner (`runner.py`) auto-discovers `V*.sql` files, tracks applied versions in a `schema_migrations` table, and is idempotent, so V003 only needs to be a correctly-named file in `alpha_agent/storage/migrations/`.

---

## DO NOT MODIFY - hard boundary

The following are explicitly **out of bounds** for every task in this plan. All three login methods produce the same NextAuth session JWE; the existing middleware re-mints it into the HS256 JWS the backend already verifies. No task may touch:

| File / area | Why it stays unchanged |
|-------------|------------------------|
| `frontend/src/auth.config.ts` | Edge-safe config. `providers: []` stays empty. The `jwt` callback (`if (user?.id) token.sub = String(user.id)`) and `session` callback (`(session.user as { id?: string }).id = token.sub`) already stamp the user id correctly for all three login methods. |
| `frontend/src/middleware.ts` | Reads `(req.auth?.user as { id?: string } \| undefined)?.id` and re-mints the HS256 JWS. The session JWE shape is identical no matter how the session was created. |
| `alpha_agent/auth/*` (`crypto_box.py`, `jwt_verify.py`, `dependencies.py`, `__init__.py`) | The backend JWT verification contract is unchanged. `require_user` / `jwt_verify` are untouched. |
| `alpha_agent/api/byok.py`, `alpha_agent/api/routes/*` | No new trust surface server-side. No route, dependency, or middleware code changes. |
| `frontend/src/app/api/auth/[...nextauth]/route.ts` | The route handler already re-exports `handlers` from `@/auth`; the provider change in `auth.ts` flows through automatically. |

Any task that finds itself "needing" to edit one of these has misread the plan - stop and report `NEEDS_CONTEXT`.

---

## Scope

| In Phase 4b | Out of scope (future phases) |
|-------------|------------------------------|
| `V003__phase4b_multi_auth.sql` - `users.password_hash` + `accounts` + `password_reset_codes` + `auth_rate_limit` | 2FA / passkeys / WebAuthn |
| `frontend/vitest.config.ts` + first frontend test runner | Migrating off NextAuth.js v5 (Better Auth) |
| `frontend/src/lib/auth/password.ts` - bcryptjs hash/verify (Node-only) | OAuth providers other than Google (GitHub etc.) |
| `frontend/src/lib/auth/rate-limit.ts` - Postgres sliding-window limiter | Email verification on signup |
| `auth.ts` provider rewrite - add Credentials + Google, remove Nodemailer | Database-backed sessions (JWT strategy stays) |
| `/register` page + Server Action | Backend `require_user` / `jwt_verify` / middleware re-mint changes |
| `/forgot-password` + `/reset-password` pages + Server Actions | `auth_rate_limit` cleanup cron (note only, no cron) |
| `/signin` page rework (password form + Google button) | |
| `/signin/error` page rework (`?error=` code mapping) | |
| `register.*` / `forgot.*` / `reset.*` / new `signin.*` i18n keys (zh + en) | |
| `make phase4b-acceptance` (pytest + vitest + frontend build + curl smokes) | |

---

## File Structure

**New files - backend:**

```
alpha_agent/storage/migrations/
└── V003__phase4b_multi_auth.sql        # A1 - password_hash ALTER + 3 new tables, additive only

tests/auth/
└── test_migration_v003.py             # A1 - mirrors test_migration_v002.py
```

**New files - frontend:**

```
frontend/
├── vitest.config.ts                   # B1 - first frontend test runner config
└── src/
    ├── lib/
    │   ├── __tests__/
    │   │   └── smoke.test.ts           # B1 - trivial test proving the runner works
    │   └── auth/
    │       ├── password.ts             # B2 - bcryptjs hashPassword / verifyPassword (Node-only)
    │       ├── rate-limit.ts           # B2 - checkRateLimit Postgres sliding window (Node-only)
    │       └── __tests__/
    │           ├── password.test.ts    # B2 - hash/verify round-trip unit test
    │           └── rate-limit.test.ts  # B2 - under/over limit, pg Pool mocked
    └── app/(auth)/
        ├── register/
        │   ├── actions.ts              # C1 - "use server" registration action
        │   ├── page.tsx                # C2 - email + password + confirm form
        │   └── __tests__/
        │       └── actions.test.ts     # C1 - duplicate reject, hash-before-insert, zod
        ├── forgot-password/
        │   ├── actions.ts              # D1 - "use server" send-reset-code action
        │   ├── page.tsx                # D1 - email-only form
        │   └── __tests__/
        │       └── actions.test.ts     # D1 - identical response, code stored hashed
        └── reset-password/
            ├── actions.ts              # D2 - "use server" verify-code + update-password action
            ├── page.tsx                # D2 - email + code + new password form
            └── __tests__/
                └── actions.test.ts     # D2 - wrong/expired/used rejected, success path
```

**Modified files - frontend:**

```
frontend/package.json                          # B1/B2 - vitest devDeps + test script + bcryptjs deps
frontend/src/auth.ts                           # B3 - Credentials + Google providers, remove Nodemailer
frontend/src/app/(auth)/signin/page.tsx        # E2 - password form + Google button + register/forgot links
frontend/src/app/(auth)/signin/error/page.tsx  # E2 - ?error= code mapping, Suspense wrapper
frontend/src/lib/i18n.ts                       # E1 - register.* / forgot.* / reset.* / signin.* keys (zh+en)
Makefile                                       # F1 - phase4b-acceptance target
```

**Unmodified by design (see "DO NOT MODIFY" above):** `frontend/src/auth.config.ts`, `frontend/src/middleware.ts`, `frontend/src/app/api/auth/[...nextauth]/route.ts`, all of `alpha_agent/auth/` and `alpha_agent/api/`.

Backend net: ~95 LOC (V003 migration 55 + test_migration_v003.py 40).
Frontend net: ~840 LOC (vitest config 15 + smoke test 5 + password.ts 25 + rate-limit.ts 70 + password/rate-limit tests 90 + auth.ts rewrite 55 + register action 75 + register page 95 + forgot action 70 + forgot page 70 + reset action 85 + reset page 95 + 3 action tests 165 + i18n keys 60 + signin page 110 + signin error page 75).

---

## Phase Order & Dependency Tiers

```
Tier 1 (foundation):        A1
Tier 2 (frontend auth core): B1 -> B2 -> B3   (B2 needs B1's test runner; B3 needs B2's password.ts)
Tier 3 (registration):      C1 -> C2          (C1 needs B2 helpers + B3 wired; C2 needs C1)
Tier 4 (password reset):    D1 -> D2          (both need B2 helpers + A1's password_reset_codes table)
Tier 5 (signin UI):         E1 -> E2          (E2 needs E1's i18n keys; E2 calls credentials/google providers from B3)
Tier 6 (acceptance):        F1                (needs everything)
```

Execution is **strictly sequential**: A1 -> B1 -> B2 -> B3 -> C1 -> C2 -> D1 -> D2 -> E1 -> E2 -> F1. **11 tasks.** The tier annotations are informational only - `superpowers:subagent-driven-development` never parallel-dispatches implementers, it runs one task at a time in this exact order regardless of tier grouping.

---

## USER SETUP - ops actions outside the plan's automation

The implementer subagents **must not** attempt to set these - they live in Vercel project settings and the Neon production DB and would fail from a subagent shell. Tests use fixture values and mocked pools. The user does these once, before F1 acceptance:

**Frontend Vercel project (`frontend`) env - Production:**
- `AUTH_GOOGLE_ID` = the Google OAuth client ID. The user has **already created** the OAuth client in Google Cloud Console; they only need to paste the two values here.
- `AUTH_GOOGLE_SECRET` = the Google OAuth client secret.
- Ensure the Google consent screen is **Published** (or the tester's Gmail is on the OAuth test-users list), otherwise Google sign-in returns `AccessDenied`.
- (Already set in M5, do not touch: `DATABASE_URL`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`.)

**Backend Vercel project (`alpha-agent`) env:** nothing new. Phase 4b adds no backend env var.

**V003 migration:** apply to the Neon production DB after `V003__phase4b_multi_auth.sql` is written. The orchestrator can run it the same way V002 was applied:

```bash
python3 -c "import asyncio; from alpha_agent.storage.migrations.runner import apply_migrations; asyncio.run(apply_migrations('<DATABASE_URL>'))"
```

The runner is idempotent and auto-discovers `V*.sql` files, so it applies only the not-yet-applied `V003`.

**Deploy:** both Vercel projects auto-deploy on `git push origin main` (backend `alpha-agent`; frontend `frontend` with `rootDirectory=frontend` + `frontend/.vercelignore`). `next.config.mjs` already excludes `/api/auth/*` from the FastAPI rewrite (the G3 fix). No manual `vercel` invocation is needed.

---

## Phase A - Foundation

### Task A1: V003 migration - password_hash + accounts + reset codes + rate limit

**Why:** Phase 4b needs four schema additions: a nullable `password_hash` column on `users` (password-login users have one, Google-only users do not), the NextAuth `accounts` table (the pg-adapter's `linkAccount` / `getUserByAccount` are called at runtime once a real OAuth provider exists - V002 deliberately skipped it for email-only), a `password_reset_codes` table for the 6-digit reset flow, and an `auth_rate_limit` table for the Postgres sliding-window limiter. The migration is **additive only**: one `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (adds a nullable column, no table rewrite) plus three `CREATE TABLE IF NOT EXISTS`. Zero-downtime, rollback-safe.

**SECURITY callout:** the `accounts` table column casing must match `@auth/pg-adapter` exactly. M5's G2 lesson: the plan author's memory was wrong about `emailVerified` casing once already. The implementer MUST audit the installed adapter source, not trust this plan's column list.

**Files:**
- Create: `alpha_agent/storage/migrations/V003__phase4b_multi_auth.sql`
- Test: `tests/auth/test_migration_v003.py`

- [ ] **Step 1: Write the failing test**

Create `tests/auth/test_migration_v003.py` (mirrors the existing `tests/auth/test_migration_v002.py` structure - file-existence + content-fragment assertions, no live DB):

```python
# tests/auth/test_migration_v003.py
"""V003 migration adds password_hash + the accounts / password_reset_codes
/ auth_rate_limit tables. Phase 4b multi-method auth.

Mirrors tests/auth/test_migration_v002.py: pure file-content assertions,
no live database connection."""
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).parents[2]
    / "alpha_agent" / "storage" / "migrations" / "V003__phase4b_multi_auth.sql"
)


def test_v003_file_exists():
    assert _MIGRATION.exists(), "V003__phase4b_multi_auth.sql missing"


def test_v003_adds_password_hash_column():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT" in sql, (
        "V003 must add the nullable users.password_hash column"
    )


def test_v003_declares_three_new_tables():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for table in ("accounts", "password_reset_codes", "auth_rate_limit"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"missing table {table}"


def test_v003_accounts_has_camelcase_adapter_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # @auth/pg-adapter uses double-quoted camelCase identifiers. The G2 audit
    # found these; the implementer re-verified them against node_modules.
    for col in ('"userId"', '"providerAccountId"'):
        assert col in sql, f"accounts table missing camelCase column {col}"
    assert "REFERENCES users(id) ON DELETE CASCADE" in sql, (
        "accounts.userId must FK to users(id) ON DELETE CASCADE"
    )
    assert 'UNIQUE (provider, "providerAccountId")' in sql, (
        "accounts needs the (provider, providerAccountId) unique constraint"
    )


def test_v003_password_reset_codes_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for fragment in (
        "code_hash TEXT NOT NULL",
        "expires_at TIMESTAMPTZ NOT NULL",
        "used BOOLEAN NOT NULL DEFAULT false",
    ):
        assert fragment in sql, f"password_reset_codes missing: {fragment}"


def test_v003_auth_rate_limit_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for fragment in (
        "bucket_key TEXT NOT NULL",
        "window_start TIMESTAMPTZ NOT NULL",
        "hit_count INT NOT NULL DEFAULT 0",
        "PRIMARY KEY (bucket_key, window_start)",
    ):
        assert fragment in sql, f"auth_rate_limit missing: {fragment}"


def test_v003_is_additive_only():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # Exactly one ALTER TABLE (the additive ADD COLUMN). No DROP at all.
    assert sql.upper().count("ALTER TABLE") == 1, (
        "V003 must contain exactly one ALTER TABLE (the additive password_hash add)"
    )
    assert "DROP TABLE" not in sql.upper(), "V003 must not drop anything"
    assert "DROP COLUMN" not in sql.upper(), "V003 must not drop any column"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/auth/test_migration_v003.py -v
```

Expected: 7 FAIL - `test_v003_file_exists` fails because `V003__phase4b_multi_auth.sql` does not exist, and the other 6 fail on the same missing file (`FileNotFoundError` from `read_text`).

- [ ] **Step 3: Audit @auth/pg-adapter, then write the migration**

First, audit the installed adapter source to confirm the exact `accounts` column names (the G2 lesson - do not trust this plan's list blindly):

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
# The accounts SQL is in the adapter; grep for the INSERT or the column list.
grep -rn "providerAccountId\|INSERT INTO accounts\|accounts" node_modules/@auth/pg-adapter/ | head -30
```

Expected: the adapter source (likely `node_modules/@auth/pg-adapter/index.js` or `lib/index.js`) shows the `accounts` columns. The G2 audit found exactly: `id`, `"userId"`, `type`, `provider`, `"providerAccountId"`, `refresh_token`, `access_token`, `expires_at`, `token_type`, `scope`, `id_token`, `session_state`. `"userId"` FKs to `users(id)` ON DELETE CASCADE; PK is `id`; unique on `(provider, "providerAccountId")`. If the audit shows anything different from this list, **match the audit, not this plan**, and note the discrepancy in the commit message.

Create `alpha_agent/storage/migrations/V003__phase4b_multi_auth.sql`:

```sql
-- Phase 4b: multi-method auth (email+password Credentials provider + Google
-- OAuth) and self-serve password reset. Purely additive: one ADD COLUMN IF
-- NOT EXISTS (nullable, no table rewrite) plus three CREATE TABLE IF NOT
-- EXISTS. Zero-downtime, rollback-safe. Spec 2026-05-14-phase4b section
-- "Data model: V003 migration".

-- 1. users.password_hash - nullable: Google-only users have no password,
--    password-only users have no linked OAuth account. bcryptjs hash, cost 12.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- 2. accounts - NextAuth @auth/pg-adapter standard schema. V002 skipped this
--    table because email-only login never called linkAccount /
--    getUserByAccount. Adding the Google provider makes those adapter methods
--    live. Column names use the adapter's double-quoted camelCase identifiers
--    EXACTLY (audited against node_modules/@auth/pg-adapter - the G2 lesson).
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

-- 3. password_reset_codes - 6-digit code stored bcryptjs-hashed (never
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

-- 4. auth_rate_limit - Postgres-backed sliding-window rate limiting (chosen
--    over Upstash Redis to avoid a new service at personal scale). bucket_key
--    is "<action>:<ip>" or "<action>:<email>"; the checkRateLimit helper
--    upserts the current window row and rejects when hit_count exceeds the
--    per-action limit. Cleanup is cheap: a periodic
--    DELETE FROM auth_rate_limit WHERE window_start < now() - interval '1 day'
--    (no cron in this phase - the row count is tiny at personal scale).
CREATE TABLE IF NOT EXISTS auth_rate_limit (
    bucket_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_key, window_start)
);

-- V002 leftover: verification_token (the magic-link table) is unused as of
-- V003 once the Nodemailer provider is removed from auth.ts. Left in place --
-- dropping an empty table is a migration with no benefit.
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/auth/test_migration_v003.py -v
```

Expected: 7/7 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add alpha_agent/storage/migrations/V003__phase4b_multi_auth.sql tests/auth/test_migration_v003.py
git commit -m "feat(migration): V003 multi-method auth schema (phase4b A1)

Additive-only: one ADD COLUMN IF NOT EXISTS (nullable users.password_hash)
plus three CREATE TABLE IF NOT EXISTS. accounts uses the @auth/pg-adapter
double-quoted camelCase columns (userId, providerAccountId), audited
against node_modules to avoid the G2 casing-mismatch bug class.
password_reset_codes stores bcryptjs-hashed 6-digit codes with a 15-min
TTL and a single-use flag. auth_rate_limit backs the Postgres
sliding-window limiter. verification_token (V002) is left in place,
unused as of V003. Zero-downtime, drop-the-3-tables rollback."
```

---

## Phase B - Auth core

### Task B1: Set up vitest - first frontend test runner

**Why:** The frontend has **no test runner today** - no `vitest`/`jest` config, no `test` script. M5's frontend "testing" was only `tsc --noEmit` + `next lint` + `next build`. Phase 4b's security-critical units (the rate limiter, the password wrapper, the Server Actions) need real unit tests, so the first Phase B task is to stand up `vitest`. This task adds the config + devDeps + a `test` script + one trivial smoke test that proves the runner actually executes - nothing else. The real tests come in B2, C1, D1, D2.

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/lib/__tests__/smoke.test.ts`
- Modify: `frontend/package.json` (add `vitest` + `@vitejs/plugin-react` devDeps, add `"test"` script)

- [ ] **Step 1: Install the test-runner devDeps**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npm install --save-dev vitest @vitejs/plugin-react
```

Verify `package.json` `devDependencies` now lists `vitest` and `@vitejs/plugin-react`.

- [ ] **Step 2: Write vitest.config.ts**

Create `frontend/vitest.config.ts`:

```typescript
// frontend/vitest.config.ts
//
// First frontend test runner (Phase 4b). Node environment - every unit
// test here is for Node-only code (the password wrapper, the Postgres
// rate limiter, the "use server" Server Actions); none of them touch the
// DOM, so jsdom is not needed. The @ alias mirrors tsconfig.json's
// paths so test files can `import ... from "@/lib/auth/password"`.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
```

- [ ] **Step 3: Add the test script + write the smoke test**

Edit `frontend/package.json` - add a `"test"` entry to the `scripts` block. The block currently reads:

```json
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
```

Change it to:

```json
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "vitest run"
  },
```

Create `frontend/src/lib/__tests__/smoke.test.ts`:

```typescript
// frontend/src/lib/__tests__/smoke.test.ts
// Trivial smoke test - proves the vitest runner is wired and executing.
// Real unit tests arrive in tasks B2, C1, D1, D2.
import { describe, it, expect } from "vitest";

describe("vitest runner smoke", () => {
  it("executes a trivial assertion", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 4: Run the test runner - confirm it passes**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run
```

Expected: vitest discovers `src/lib/__tests__/smoke.test.ts`, runs 1 test, 1 passes. Output ends with something like `Test Files  1 passed (1)` / `Tests  1 passed (1)`.

Also confirm `npm test` works (same result), since F1's acceptance target invokes `npm test`.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/vitest.config.ts frontend/src/lib/__tests__/smoke.test.ts frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): set up vitest test runner (phase4b B1)

First frontend test runner - M5 had only tsc/lint/build. Node
environment (no DOM in any Phase 4b unit), @ alias mirrors tsconfig
paths. Adds vitest + @vitejs/plugin-react devDeps and a 'test' script.
One trivial smoke test proves the runner executes; the
security-critical units (rate-limit, password wrapper, Server Actions)
get real tests in B2 / C1 / D1 / D2."
```

---

### Task B2: password.ts + rate-limit.ts - Node-only auth helpers

**Why:** Two small Node-only modules every later task depends on. `password.ts` is a thin `bcryptjs` wrapper (`hashPassword` / `verifyPassword`, cost factor 12) used by registration, password reset, and the Credentials `authorize()` callback. `rate-limit.ts` is a Postgres sliding-window limiter (`checkRateLimit(action, key, pool)`) used by registration, forgot-password, and login.

**SECURITY callouts:**
- `bcryptjs` cost factor **12** for both passwords and reset codes.
- `password.ts` is **Node-only** - it must NEVER be imported by `auth.config.ts` or `middleware.ts` (both edge-reachable). `bcryptjs` is pure JS (not native `bcrypt`/`argon2`) so a stray import would not break the build, but the import-graph discipline still holds: hashing helpers live in `lib/auth/` and are imported only by Node route handlers and `"use server"` actions.
- Use `bcryptjs` (pure JS), not `bcrypt` (native) - the spec's edge-runtime-safety decision.

**Files:**
- Create: `frontend/src/lib/auth/password.ts`
- Create: `frontend/src/lib/auth/rate-limit.ts`
- Create: `frontend/src/lib/auth/__tests__/password.test.ts`
- Create: `frontend/src/lib/auth/__tests__/rate-limit.test.ts`
- Modify: `frontend/package.json` (add `bcryptjs` dep + `@types/bcryptjs` devDep)

- [ ] **Step 1: Write the failing tests**

First install the deps so the imports can resolve when the test runs (the test still fails RED because the modules under test do not exist yet):

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npm install bcryptjs
npm install --save-dev @types/bcryptjs
```

Create `frontend/src/lib/auth/__tests__/password.test.ts`:

```typescript
// frontend/src/lib/auth/__tests__/password.test.ts
import { describe, it, expect } from "vitest";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

describe("password.ts - bcryptjs wrapper", () => {
  it("hashPassword produces a hash that differs from the plaintext", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(hash).not.toBe("hunter2-correct-horse");
    expect(hash.length).toBeGreaterThan(20);
    // bcrypt hashes start with $2 (the algorithm identifier).
    expect(hash.startsWith("$2")).toBe(true);
  });

  it("verifyPassword round-trips: the original plaintext verifies true", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(await verifyPassword("hunter2-correct-horse", hash)).toBe(true);
  });

  it("verifyPassword returns false for a wrong password", async () => {
    const hash = await hashPassword("hunter2-correct-horse");
    expect(await verifyPassword("wrong-password", hash)).toBe(false);
  });

  it("two hashes of the same plaintext differ (per-hash salt)", async () => {
    const a = await hashPassword("same-input");
    const b = await hashPassword("same-input");
    expect(a).not.toBe(b);
    // ...but both still verify.
    expect(await verifyPassword("same-input", a)).toBe(true);
    expect(await verifyPassword("same-input", b)).toBe(true);
  });
});
```

Create `frontend/src/lib/auth/__tests__/rate-limit.test.ts`:

```typescript
// frontend/src/lib/auth/__tests__/rate-limit.test.ts
//
// rate-limit.ts talks to Postgres. The unit test mocks the pg Pool the
// same way the backend tests mock asyncpg in tests/api/: a fake pool whose
// query() returns a controlled rows payload, so we exercise the
// allow/deny branching without a live database.
import { describe, it, expect, vi } from "vitest";
import { checkRateLimit, RATE_LIMITS } from "@/lib/auth/rate-limit";

// A fake pg Pool: query() returns whatever the test queues up.
function fakePool(hitCountAfterUpsert: number) {
  return {
    query: vi.fn(async () => ({
      rows: [{ hit_count: hitCountAfterUpsert }],
      rowCount: 1,
    })),
  };
}

describe("rate-limit.ts - checkRateLimit", () => {
  it("exposes per-action limits as consts", () => {
    expect(RATE_LIMITS.login).toBe(5);
    expect(RATE_LIMITS.register).toBe(3);
    expect(RATE_LIMITS.reset_request).toBe(3);
  });

  it("allows when the post-upsert hit_count is at or under the limit", async () => {
    // login limit is 5; a hit_count of 5 is the 5th attempt - still allowed.
    const pool = fakePool(5);
    const result = await checkRateLimit("login", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(true);
    expect(pool.query).toHaveBeenCalledOnce();
  });

  it("denies when the post-upsert hit_count exceeds the limit", async () => {
    // login limit is 5; a hit_count of 6 means this attempt is over.
    const pool = fakePool(6);
    const result = await checkRateLimit("login", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(false);
  });

  it("denies a register attempt over the register limit of 3", async () => {
    const pool = fakePool(4);
    const result = await checkRateLimit("register", "1.2.3.4", pool as never);
    expect(result.allowed).toBe(false);
  });

  it("builds the bucket_key as <action>:<key>", async () => {
    const pool = fakePool(1);
    await checkRateLimit("reset_request", "user@example.com", pool as never);
    const [, params] = pool.query.mock.calls[0];
    expect(params[0]).toBe("reset_request:user@example.com");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run src/lib/auth/__tests__/
```

Expected: both files FAIL to even load - `Failed to resolve import "@/lib/auth/password"` and `"@/lib/auth/rate-limit"` because the modules do not exist yet.

- [ ] **Step 3: Write the two modules**

Create `frontend/src/lib/auth/password.ts`:

```typescript
// frontend/src/lib/auth/password.ts
//
// Node-only bcryptjs wrapper. The single place the app hashes or verifies
// a secret (user passwords AND 6-digit reset codes). bcryptjs is pure JS
// (not native bcrypt/argon2) per the spec's edge-runtime-safety decision.
//
// IMPORT-GRAPH RULE: this module is Node-only. It must NEVER be imported by
// auth.config.ts or middleware.ts (both edge-reachable). It is imported only
// by the Credentials authorize() callback in auth.ts (Node route handler)
// and by the "use server" Server Actions.
import bcrypt from "bcryptjs";

// Cost factor 12: the spec's chosen work factor for both passwords and codes.
const BCRYPT_COST = 12;

/** Hash a plaintext secret (password or reset code) with bcryptjs cost 12. */
export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, BCRYPT_COST);
}

/** Verify a plaintext secret against a bcryptjs hash. Returns false on mismatch
 *  (never throws on a wrong password - a thrown error would be a different
 *  signal the caller must not have to distinguish). */
export async function verifyPassword(
  plain: string,
  hash: string,
): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}
```

Create `frontend/src/lib/auth/rate-limit.ts`:

```typescript
// frontend/src/lib/auth/rate-limit.ts
//
// Node-only Postgres sliding-window rate limiter, backed by the
// auth_rate_limit table (V003). Chosen over Upstash Redis to avoid adding
// a new service at personal scale.
//
// The window is 1 minute, truncated to the minute boundary so concurrent
// requests in the same minute share one row. checkRateLimit() upserts the
// current-window row (incrementing hit_count) and returns allowed=false
// when the post-upsert count exceeds the per-action limit.
import type { Pool } from "pg";

/** Per-action limits, attempts per 1-minute window. */
export const RATE_LIMITS = {
  login: 5,
  register: 3,
  reset_request: 3,
} as const;

export type RateLimitAction = keyof typeof RATE_LIMITS;

export interface RateLimitResult {
  allowed: boolean;
  /** The per-action limit, surfaced so the caller can build a clear message. */
  limit: number;
}

/**
 * Upsert the current-minute window row for `<action>:<key>` and decide
 * whether this attempt is within the per-action limit.
 *
 * @param action  one of RATE_LIMITS' keys (login / register / reset_request)
 * @param key     the IP address or email this bucket is keyed on
 * @param pool    a pg Pool (passed in so tests can mock it)
 */
export async function checkRateLimit(
  action: RateLimitAction,
  key: string,
  pool: Pool,
): Promise<RateLimitResult> {
  const limit = RATE_LIMITS[action];
  const bucketKey = `${action}:${key}`;
  // Truncate "now" to the minute so all requests in the same minute hit one row.
  const result = await pool.query(
    `INSERT INTO auth_rate_limit (bucket_key, window_start, hit_count)
       VALUES ($1, date_trunc('minute', now()), 1)
     ON CONFLICT (bucket_key, window_start)
       DO UPDATE SET hit_count = auth_rate_limit.hit_count + 1
     RETURNING hit_count`,
    [bucketKey],
  );
  const hitCount = Number(result.rows[0]?.hit_count ?? 0);
  return { allowed: hitCount <= limit, limit };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run src/lib/auth/__tests__/
```

Expected: `password.test.ts` 4/4 PASS, `rate-limit.test.ts` 5/5 PASS. Also run `npx tsc --noEmit` - silent.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/auth/password.ts frontend/src/lib/auth/rate-limit.ts \
  frontend/src/lib/auth/__tests__/password.test.ts \
  frontend/src/lib/auth/__tests__/rate-limit.test.ts \
  frontend/package.json frontend/package-lock.json
git commit -m "feat(auth): bcryptjs password wrapper + Postgres rate limiter (phase4b B2)

password.ts: hashPassword/verifyPassword, bcryptjs cost 12, Node-only --
never imported by auth.config.ts or middleware.ts (edge-reachable).
rate-limit.ts: checkRateLimit(action, key, pool) - 1-minute sliding
window upsert against auth_rate_limit, per-action limits as consts
(login 5, register 3, reset_request 3). Unit tests mock the pg Pool the
same way the backend tests mock asyncpg. Adds bcryptjs + @types/bcryptjs."
```

---

### Task B3: auth.ts provider rewrite - Credentials + Google, remove Nodemailer

**Why:** This is the core wiring change. `auth.ts` keeps everything else (the `pool` const, `...authConfig`, `PostgresAdapter(pool)`) and only rewrites the `providers` array: add a `Credentials` provider whose `authorize()` callback does a Node-context Postgres lookup + bcryptjs compare, add a `Google` provider with `allowDangerousEmailAccountLinking: true`, and remove the `Nodemailer` provider entirely (magic-link login is gone). The `pool` const stays because the pg-adapter still needs it AND the `authorize()` callback reuses it for the user lookup.

**DO NOT MODIFY reminder:** `auth.config.ts` and `middleware.ts` are **NOT touched** by this task. The Credentials `authorize()` returns a user object whose `id` flows into `token.sub` via the *existing* `jwt` callback in `auth.config.ts` - that callback already handles it (`if (user?.id) token.sub = String(user.id)`). Same for the Google OAuth callback. No callback change is needed anywhere.

**SECURITY callout:** the `authorize()` callback must return `null` on **any** failure (no such user, wrong password, malformed input) - never a message that distinguishes "unknown email" from "wrong password". NextAuth surfaces a generic `CredentialsSignin` error to the client either way; user enumeration is prevented by returning the same `null`.

**Edge-runtime note:** `authorize()` runs only inside the Node `/api/auth/[...nextauth]` route handler, never in middleware/edge. It imports `verifyPassword` from `lib/auth/password.ts` (Node-only) - that is fine, the route handler is Node context.

**Files:**
- Modify: `frontend/src/auth.ts`

There is no vitest test for this task directly: `authorize()` is wired into NextAuth and is verified end-to-end by `tsc --noEmit` + `next build` here and by the F1 acceptance UAT. The `authorize()` body is small and the DB-lookup + `verifyPassword` pieces are each already independently exercised (B2's `password.test.ts`); extracting it to a separately-tested helper would add indirection for no real coverage gain, so it stays inline.

- [ ] **Step 1: Read the current auth.ts**

```bash
cat /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend/src/auth.ts
```

Confirm it currently matches (verbatim, from the recon):

```typescript
// frontend/src/auth.ts
import NextAuth from "next-auth";
import Nodemailer from "next-auth/providers/nodemailer";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";
import { authConfig } from "./auth.config";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PostgresAdapter(pool),
  providers: [
    Nodemailer({
      server: { host: "smtp.resend.com", port: 465, auth: { user: "resend", pass: process.env.RESEND_API_KEY! } },
      from: process.env.EMAIL_FROM!,
      maxAge: 24 * 60 * 60,
    }),
  ],
});
```

If it differs, stop and report `NEEDS_CONTEXT` - the rewrite below assumes this exact starting point.

- [ ] **Step 2: Rewrite auth.ts**

Replace the entire file contents of `frontend/src/auth.ts` with:

```typescript
// frontend/src/auth.ts
//
// NextAuth.js v5 config (Node route-handler context). Phase 4b: two login
// methods - email+password via the Credentials provider, and Google OAuth.
// The Nodemailer magic-link provider is REMOVED (magic-link login is gone;
// Resend stays only as the SMTP transport the password-reset Server Action
// calls directly, not via a NextAuth provider).
//
// auth.config.ts and middleware.ts are NOT modified by Phase 4b. The
// Credentials authorize() callback and the Google OAuth callback each
// return a user object whose id flows into token.sub via the existing
// jwt callback in auth.config.ts. The middleware decrypts the same session
// JWE and re-mints the HS256 JWS exactly as before.
import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";
import { z } from "zod";
import { authConfig } from "./auth.config";
import { verifyPassword } from "./lib/auth/password";

// Reused by BOTH the pg-adapter (linkAccount / getUserByAccount for Google)
// and the Credentials authorize() callback's user lookup.
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// authorize() input contract. Parsing here means a malformed submission
// returns null (generic failure) instead of throwing.
const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PostgresAdapter(pool),
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      // Runs only in the Node /api/auth/[...nextauth] route handler, never
      // in middleware/edge. Returns null on ANY failure - no message that
      // distinguishes "unknown email" from "wrong password" (no user
      // enumeration). NextAuth surfaces a generic CredentialsSignin error.
      authorize: async (raw) => {
        const parsed = credentialsSchema.safeParse(raw);
        if (!parsed.success) return null;
        const { email, password } = parsed.data;

        const result = await pool.query(
          `SELECT id, email, name, password_hash
             FROM users
            WHERE email = $1`,
          [email],
        );
        const row = result.rows[0];
        // No such user, or a Google-only user with no password set.
        if (!row || !row.password_hash) return null;

        const ok = await verifyPassword(password, row.password_hash);
        if (!ok) return null;

        // The id flows into token.sub via auth.config.ts's jwt callback.
        return {
          id: String(row.id),
          email: row.email as string,
          name: (row.name as string | null) ?? null,
        };
      },
    }),
    // allowDangerousEmailAccountLinking: a Google sign-in proves email
    // ownership, so auto-linking to an existing same-email password account
    // is acceptable (and the no-linking alternative - orphaned duplicate
    // accounts - is strictly worse with open, unverified registration).
    // AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET are auto-detected from env by
    // Auth.js v5, so Google needs no explicit args here.
    Google({ allowDangerousEmailAccountLinking: true }),
  ],
});
```

- [ ] **Step 3: Verify tsc + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -10
```

Expected: `tsc` silent, `next lint` clean, `next build` succeeds. The build exercises the new provider wiring. If `next-auth/providers/credentials` or `next-auth/providers/google` is not found at the installed `next-auth ^5.0.0-beta.31`, stop and report `NEEDS_CONTEXT` with the exact import error - do not guess at the v5 beta export paths; the controller can fetch the current Auth.js v5 docs via context7 and re-dispatch.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/auth.ts
git commit -m "feat(auth): swap magic-link for Credentials + Google providers (phase4b B3)

auth.ts providers array rewritten: add Credentials (authorize() does a
Node-context Postgres user lookup + bcryptjs verifyPassword, returns null
on ANY failure -> no user enumeration), add Google with
allowDangerousEmailAccountLinking, REMOVE Nodemailer (magic-link login is
gone). The pool const stays - reused by the pg-adapter AND the
authorize() lookup. authorize() runs only in the Node route handler, never
edge. auth.config.ts and middleware.ts deliberately untouched: the
existing jwt callback already stamps user.id into token.sub for all three
login methods."
```

---

## Phase C - Registration

### Task C1: registration Server Action

**Why:** The `/register` page needs a `"use server"` action that validates the form, rate-limits, checks the email is not already registered, hashes the password, and inserts the new `users` row. There are **no existing Server Actions** in the project (`grep "use server"` returns nothing), so this task establishes the full `"use server"` file pattern that C1/D1/D2 all follow.

**Pattern decision (NextAuth v5):** the action does the DB work and returns a structured result; the **client page** then calls `signIn("credentials", ...)`. This is the cleaner v5 pattern: `signIn` from `next-auth/react` belongs in a client component (it triggers a client-side navigation/redirect), and keeping the action a pure data mutation makes it unit-testable without mocking NextAuth's `signIn`. So C1's action returns `{ ok: true }` / `{ ok: false, error }` and C2's page calls `signIn` on `ok: true`.

**SECURITY callouts:**
- The password is hashed with `hashPassword` (bcryptjs cost 12) **before** the `INSERT` - the INSERT parameters contain a bcrypt hash, never the plaintext.
- Duplicate-email returns a clear "email already registered" - this is a *deliberate* disclosure (the user needs to know to sign in instead). The `register` rate limit (3/min) caps enumeration abuse.
- Rate-limit is checked *before* the duplicate-email DB lookup so a flood of attempts is cheap to reject.

**Files:**
- Create: `frontend/src/app/(auth)/register/actions.ts`
- Create: `frontend/src/app/(auth)/register/__tests__/actions.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/(auth)/register/__tests__/actions.test.ts`:

```typescript
// frontend/src/app/(auth)/register/__tests__/actions.test.ts
//
// The registration action talks to Postgres via a module-level pg Pool.
// We mock the "pg" module so Pool() returns a controllable fake, and mock
// rate-limit.ts so the limiter never blocks unless a test wants it to.
import { describe, it, expect, vi, beforeEach } from "vitest";

// --- mock the pg Pool ---------------------------------------------------
const mockQuery = vi.fn();
vi.mock("pg", () => ({
  Pool: vi.fn(() => ({ query: mockQuery })),
}));

// --- mock the rate limiter (default: allow) -----------------------------
const mockCheckRateLimit = vi.fn(async () => ({ allowed: true, limit: 3 }));
vi.mock("@/lib/auth/rate-limit", () => ({
  checkRateLimit: mockCheckRateLimit,
  RATE_LIMITS: { login: 5, register: 3, reset_request: 3 },
}));

// password.ts is NOT mocked - we want the real bcryptjs so the test can
// assert the INSERT received a real hash, not the plaintext.
import { registerAction } from "@/app/(auth)/register/actions";
import { verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

beforeEach(() => {
  mockQuery.mockReset();
  mockCheckRateLimit.mockReset();
  mockCheckRateLimit.mockResolvedValue({ allowed: true, limit: 3 });
});

describe("registerAction", () => {
  it("rejects a password shorter than 8 chars (zod)", async () => {
    const result = await registerAction(
      formDataOf({ email: "a@b.com", password: "short", confirmPassword: "short" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
    // zod rejected before any DB call.
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("rejects when confirmPassword does not match", async () => {
    const result = await registerAction(
      formDataOf({
        email: "a@b.com",
        password: "longenough1",
        confirmPassword: "different123",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
  });

  it("rejects a duplicate email", async () => {
    // First query is the existing-email lookup - return a row.
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 7 }], rowCount: 1 });
    const result = await registerAction(
      formDataOf({
        email: "taken@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("email_taken");
    // Only the lookup ran; no INSERT.
    expect(mockQuery).toHaveBeenCalledOnce();
  });

  it("denies when the rate limit is exceeded", async () => {
    mockCheckRateLimit.mockResolvedValueOnce({ allowed: false, limit: 3 });
    const result = await registerAction(
      formDataOf({
        email: "a@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("rate_limited");
    // Rate-limited before any DB call.
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("hashes the password before the INSERT and succeeds", async () => {
    // Query 1: email lookup -> no existing row. Query 2: the INSERT.
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [{ id: 99 }], rowCount: 1 });

    const result = await registerAction(
      formDataOf({
        email: "new@b.com",
        password: "longenough1",
        confirmPassword: "longenough1",
      }),
    );
    expect(result.ok).toBe(true);

    // The INSERT is the 2nd query call. Its params must contain a bcrypt
    // hash of the password, NOT the plaintext.
    const insertCall = mockQuery.mock.calls[1];
    const insertParams = insertCall[1] as string[];
    expect(insertParams).not.toContain("longenough1");
    // exactly one param is a bcrypt hash that verifies the plaintext.
    const hashParam = insertParams.find((p) => p.startsWith("$2"));
    expect(hashParam).toBeDefined();
    expect(await verifyPassword("longenough1", hashParam as string)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/register/__tests__/actions.test.ts"
```

Expected: FAIL to load - `Failed to resolve import "@/app/(auth)/register/actions"` (the action file does not exist yet).

- [ ] **Step 3: Write the registration action**

Create `frontend/src/app/(auth)/register/actions.ts`:

```typescript
// frontend/src/app/(auth)/register/actions.ts
"use server";
//
// Open registration: rate-limit -> zod validate -> duplicate-email check ->
// bcryptjs hash -> INSERT into users. Returns a structured result; the
// /register client page calls signIn("credentials", ...) on ok:true (the
// cleaner NextAuth v5 split - signIn belongs in a client component).
//
// This is the project's first "use server" file; D1 and D2 follow the same
// shape (a module-level pg Pool, zod parse, structured RegisterResult-style
// return, no thrown errors crossing the action boundary).
import { Pool } from "pg";
import { z } from "zod";
import { hashPassword } from "@/lib/auth/password";
import { checkRateLimit } from "@/lib/auth/rate-limit";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

// password 8-32 chars; confirmPassword must match. The .refine runs after
// the field checks so a short password reports "invalid" without a confusing
// double error.
const registerSchema = z
  .object({
    email: z.string().email(),
    password: z.string().min(8).max(32),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ["confirmPassword"],
  });

export type RegisterError =
  | "invalid"
  | "rate_limited"
  | "email_taken"
  | "server_error";

export type RegisterResult =
  | { ok: true; email: string }
  | { ok: false; error: RegisterError };

export async function registerAction(formData: FormData): Promise<RegisterResult> {
  // Rate-limit FIRST so a flood is cheap to reject (keyed on email here --
  // no reliable client IP inside a Server Action without extra plumbing;
  // email keying still caps per-target abuse and pairs with zod limits).
  const emailRaw = String(formData.get("email") ?? "");
  const rate = await checkRateLimit("register", emailRaw || "unknown", pool);
  if (!rate.allowed) return { ok: false, error: "rate_limited" };

  const parsed = registerSchema.safeParse({
    email: emailRaw,
    password: String(formData.get("password") ?? ""),
    confirmPassword: String(formData.get("confirmPassword") ?? ""),
  });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email, password } = parsed.data;

  try {
    const existing = await pool.query(`SELECT id FROM users WHERE email = $1`, [
      email,
    ]);
    if (existing.rows.length > 0) {
      return { ok: false, error: "email_taken" };
    }

    // Hash BEFORE the INSERT - the INSERT params carry a bcrypt hash, never
    // the plaintext.
    const passwordHash = await hashPassword(password);
    await pool.query(
      `INSERT INTO users (email, name, password_hash, created_at)
         VALUES ($1, $2, $3, now())`,
      [email, null, passwordHash],
    );
    return { ok: true, email };
  } catch {
    // Never let a DB error leak as a thrown exception across the action
    // boundary - return a generic structured error the page can render.
    return { ok: false, error: "server_error" };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/register/__tests__/actions.test.ts"
```

Expected: 5/5 PASS. Also `npx tsc --noEmit` - silent.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(auth)/register/actions.ts" \
  "frontend/src/app/(auth)/register/__tests__/actions.test.ts"
git commit -m "feat(auth): registration Server Action (phase4b C1)

First 'use server' file in the project - establishes the pattern D1/D2
follow. registerAction: rate-limit (register 3/min) -> zod (email,
password 8-32, confirm matches) -> duplicate-email check -> bcryptjs hash
-> INSERT users. Password is hashed BEFORE the INSERT (params carry a
bcrypt hash, never plaintext). Returns a structured RegisterResult; the
client page calls signIn('credentials') on ok:true. Duplicate-email is a
deliberate disclosure, capped by the rate limit. Unit test mocks the pg
Pool + rate limiter, asserts hash-before-insert with the real bcryptjs."
```

---

### Task C2: /register page

**Why:** The client-facing registration form. A client component with email + password + confirm fields that calls C1's `registerAction`, and on `ok: true` calls `signIn("credentials", ...)` to log the new user straight in and redirect. Mirrors the `tm-*` token styling and the `getLocaleFromStorage()` locale pattern of the existing `signin/page.tsx`.

**Non-TDD task** (a UI page - there is no frontend DOM test harness; verification is `tsc` + `lint` + `build`). The action it calls (`registerAction`) is already unit-tested in C1.

**Suspense note:** this page does **not** read `useSearchParams` or `usePathname`, so it does **not** need a `<Suspense>` wrapper. (Contrast with E2's error page, which does.)

**Files:**
- Create: `frontend/src/app/(auth)/register/page.tsx`

- [ ] **Step 1: Write the page**

Create `frontend/src/app/(auth)/register/page.tsx`:

```tsx
// frontend/src/app/(auth)/register/page.tsx
"use client";
//
// Open registration form: email + password + confirm. Calls the C1
// registerAction (a "use server" action); on ok:true it signs the new
// user straight in via signIn("credentials", ...) and redirects. tm-*
// token styling + getLocaleFromStorage() locale pattern mirror
// signin/page.tsx. No useSearchParams here, so no Suspense wrapper needed.
import { useState, useEffect } from "react";
import Link from "next/link";
import { signIn } from "next-auth/react";
import { registerAction, type RegisterError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

// Map a RegisterError code to an i18n key (keys defined in E1).
const ERROR_KEY: Record<RegisterError, Parameters<typeof t>[1]> = {
  invalid: "register.error_invalid",
  rate_limited: "register.error_rate_limited",
  email_taken: "register.error_email_taken",
  server_error: "register.error_server",
};

export default function RegisterPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorKey, setErrorKey] = useState<Parameters<typeof t>[1] | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);

    const fd = new FormData();
    fd.set("email", email);
    fd.set("password", password);
    fd.set("confirmPassword", confirmPassword);

    const result = await registerAction(fd);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      setSubmitting(false);
      return;
    }
    // Registered: log straight in. signIn handles the redirect to /picks.
    await signIn("credentials", { email, password, callbackUrl: "/picks" });
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "register.title")}
      </h1>
      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.email_label")}
        </label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t(locale, "register.email_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.password_label")}
        </label>
        <input
          type="password"
          required
          minLength={8}
          maxLength={32}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t(locale, "register.password_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <label className="block text-xs text-tm-muted">
          {t(locale, "register.confirm_label")}
        </label>
        <input
          type="password"
          required
          minLength={8}
          maxLength={32}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder={t(locale, "register.confirm_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        {errorKey && (
          <p className="text-xs text-tm-neg">{t(locale, errorKey)}</p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
        >
          {t(locale, submitting ? "register.submitting" : "register.submit_button")}
        </button>
      </form>
      <p className="mt-4 text-center text-xs text-tm-muted">
        {t(locale, "register.have_account")}{" "}
        <Link href="/signin" className="text-tm-accent hover:underline">
          {t(locale, "register.signin_link")}
        </Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -10
```

Expected: `tsc` silent, `next lint` clean, `next build` succeeds with a `/register` route in the route manifest. Note: `tsc` will flag the i18n keys (`register.*`) as not-yet-existing `TranslationKey`s - **E1 adds them**. If C2 is implemented before E1 in a strict sequence, the keys do not exist yet; the plan order is C2 -> D1 -> D2 -> **E1** -> E2, so C2's `tsc` *will* fail on the missing keys. To keep C2 self-verifying, **E1's i18n keys are a prerequisite** - see the note in Step 3.

- [ ] **Step 3: Sequencing note + commit**

Because the page references `register.*` i18n keys that E1 adds, and the strict execution order runs C2 before E1, the implementer has two clean options - pick one and note it in the commit:

  - **Option A (recommended):** add the `register.*` keys to `i18n.ts` *now* as part of C2 (a small additive edit - the same keys E1 would add, just the `register.*` subset), and have E1 add only the `forgot.*` / `reset.*` / `signin.*` keys. This keeps every task self-verifying.
  - **Option B:** leave C2's `tsc` showing the missing-key errors, commit anyway, and let E1 resolve them. Only acceptable if the subagent harness tolerates a known-failing `tsc` mid-plan.

Option A is strongly preferred (every task should be green on its own). If Option A is taken, copy the `register.*` block verbatim from **E1 Step 1** into both the zh and en objects of `frontend/src/lib/i18n.ts` as part of this task, then `tsc` is clean.

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
# If Option A: also add frontend/src/lib/i18n.ts to this commit.
git add "frontend/src/app/(auth)/register/page.tsx"
git commit -m "feat(auth): /register page (phase4b C2)

Client component: email + password + confirm form -> C1 registerAction
-> signIn('credentials') on success -> redirect to /picks. tm-* token
styling + getLocaleFromStorage() locale pattern mirror signin/page.tsx.
No useSearchParams, so no Suspense wrapper. RegisterError codes map to
register.error_* i18n keys. (Option A: register.* i18n keys added here
so the page is self-verifying; E1 adds the remaining key groups.)"
```

---

## Phase D - Password reset

### Task D1: forgot-password Server Action + page

**Why:** Step one of the self-serve reset flow. The `"use server"` action rate-limits, generates a random 6-digit code, stores the **hashed** code (bcryptjs) with a 15-minute expiry in `password_reset_codes`, and emails the **plaintext** code via Resend SMTP. The page is an email-only form. The 6-digit code is then consumed by D2's reset-password flow.

**SECURITY callouts:**
- The reset code is stored **hashed** (via `hashPassword` - bcryptjs cost 12), **never** in plaintext. Only the email carries the plaintext code.
- The action **always returns the same response** - `{ ok: true }` with the "if that email exists, a code was sent" message - whether or not the email belongs to a real user. No user enumeration. (It still inserts a code row for a non-existent email; that is fine and is what keeps the timing/response identical.)
- Rate-limited (`reset_request` 3/min, keyed on email) before any other work.

**Resend transport:** the action sends mail directly via `nodemailer` using the Resend SMTP creds already in env (the same creds `auth.ts` previously fed to its Nodemailer provider, now removed): host `smtp.resend.com`, port `465`, user `resend`, pass `process.env.RESEND_API_KEY`, from `process.env.EMAIL_FROM`. `nodemailer` is already an installed dependency.

**Files:**
- Create: `frontend/src/app/(auth)/forgot-password/actions.ts`
- Create: `frontend/src/app/(auth)/forgot-password/page.tsx`
- Create: `frontend/src/app/(auth)/forgot-password/__tests__/actions.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/(auth)/forgot-password/__tests__/actions.test.ts`:

```typescript
// frontend/src/app/(auth)/forgot-password/__tests__/actions.test.ts
//
// forgotPasswordAction talks to Postgres (pg Pool) and sends mail
// (nodemailer). Both are mocked. password.ts is NOT mocked - the test
// asserts the stored code is a real bcrypt hash, not the plaintext.
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockQuery = vi.fn();
vi.mock("pg", () => ({
  Pool: vi.fn(() => ({ query: mockQuery })),
}));

const mockSendMail = vi.fn(async () => ({ messageId: "fake" }));
vi.mock("nodemailer", () => ({
  default: { createTransport: vi.fn(() => ({ sendMail: mockSendMail })) },
  createTransport: vi.fn(() => ({ sendMail: mockSendMail })),
}));

const mockCheckRateLimit = vi.fn(async () => ({ allowed: true, limit: 3 }));
vi.mock("@/lib/auth/rate-limit", () => ({
  checkRateLimit: mockCheckRateLimit,
  RATE_LIMITS: { login: 5, register: 3, reset_request: 3 },
}));

import { forgotPasswordAction } from "@/app/(auth)/forgot-password/actions";
import { verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

beforeEach(() => {
  mockQuery.mockReset();
  mockSendMail.mockReset();
  mockSendMail.mockResolvedValue({ messageId: "fake" });
  mockCheckRateLimit.mockReset();
  mockCheckRateLimit.mockResolvedValue({ allowed: true, limit: 3 });
});

describe("forgotPasswordAction", () => {
  it("returns the same ok:true response when the email exists", async () => {
    // user lookup -> a row exists; then the INSERT into password_reset_codes.
    mockQuery
      .mockResolvedValueOnce({ rows: [{ id: 5 }], rowCount: 1 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    const result = await forgotPasswordAction(formDataOf({ email: "real@b.com" }));
    expect(result.ok).toBe(true);
  });

  it("returns the SAME ok:true response when the email does NOT exist", async () => {
    // user lookup -> no row; the action still inserts a code row + sends mail
    // so the response and timing are indistinguishable (no enumeration).
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    const result = await forgotPasswordAction(formDataOf({ email: "ghost@b.com" }));
    expect(result.ok).toBe(true);
  });

  it("stores the code HASHED, never as plaintext", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [{ id: 5 }], rowCount: 1 })
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });
    await forgotPasswordAction(formDataOf({ email: "real@b.com" }));

    // The 2nd query is the INSERT into password_reset_codes.
    const insertCall = mockQuery.mock.calls[1];
    const insertParams = insertCall[1] as string[];
    const codeHashParam = insertParams.find((p) => p.startsWith("$2"));
    expect(codeHashParam).toBeDefined();

    // The plaintext code is whatever was emailed - pull it from sendMail.
    const mailArg = mockSendMail.mock.calls[0][0] as { text?: string };
    const plaintextCode = (mailArg.text ?? "").match(/\d{6}/)?.[0];
    expect(plaintextCode).toMatch(/^\d{6}$/);
    // No raw 6-digit code in the INSERT params.
    expect(insertParams).not.toContain(plaintextCode);
    // The stored hash verifies the emailed plaintext code.
    expect(await verifyPassword(plaintextCode as string, codeHashParam as string)).toBe(true);
  });

  it("denies when the reset_request rate limit is exceeded", async () => {
    mockCheckRateLimit.mockResolvedValueOnce({ allowed: false, limit: 3 });
    const result = await forgotPasswordAction(formDataOf({ email: "real@b.com" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("rate_limited");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("rejects a malformed email via zod", async () => {
    const result = await forgotPasswordAction(formDataOf({ email: "not-an-email" }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/forgot-password/__tests__/actions.test.ts"
```

Expected: FAIL to load - `Failed to resolve import "@/app/(auth)/forgot-password/actions"`.

- [ ] **Step 3: Write the action + the page**

Create `frontend/src/app/(auth)/forgot-password/actions.ts`:

```typescript
// frontend/src/app/(auth)/forgot-password/actions.ts
"use server";
//
// Step 1 of self-serve password reset. Rate-limit -> zod -> generate a
// random 6-digit code -> store the HASHED code (15-min TTL) -> email the
// PLAINTEXT code via Resend SMTP. ALWAYS returns the same ok:true response
// regardless of whether the email belongs to a real user (no enumeration).
import { randomInt } from "crypto";
import { Pool } from "pg";
import { z } from "zod";
import nodemailer from "nodemailer";
import { hashPassword } from "@/lib/auth/password";
import { checkRateLimit } from "@/lib/auth/rate-limit";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const forgotSchema = z.object({ email: z.string().email() });

// Resend SMTP transport - same creds auth.ts's removed Nodemailer provider
// used. nodemailer is already an installed dependency.
const mailer = nodemailer.createTransport({
  host: "smtp.resend.com",
  port: 465,
  auth: { user: "resend", pass: process.env.RESEND_API_KEY! },
});

const CODE_TTL_MINUTES = 15;

export type ForgotError = "invalid" | "rate_limited";
export type ForgotResult = { ok: true } | { ok: false; error: ForgotError };

/** Generate a zero-padded random 6-digit code (100000-999999). */
function generateCode(): string {
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}

export async function forgotPasswordAction(
  formData: FormData,
): Promise<ForgotResult> {
  const emailRaw = String(formData.get("email") ?? "");

  const rate = await checkRateLimit("reset_request", emailRaw || "unknown", pool);
  if (!rate.allowed) return { ok: false, error: "rate_limited" };

  const parsed = forgotSchema.safeParse({ email: emailRaw });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email } = parsed.data;

  // We look up the user but DO NOT branch the response on it - the row
  // insert + email send happen either way so the response is identical.
  // (A non-existent email still gets a code row; harmless, never consumed.)
  await pool.query(`SELECT id FROM users WHERE email = $1`, [email]);

  const code = generateCode();
  const codeHash = await hashPassword(code);
  const expiresAt = new Date(Date.now() + CODE_TTL_MINUTES * 60_000);

  await pool.query(
    `INSERT INTO password_reset_codes (email, code_hash, expires_at)
       VALUES ($1, $2, $3)`,
    [email, codeHash, expiresAt.toISOString()],
  );

  // Send the PLAINTEXT code. A delivery failure must not change the
  // response (still ok:true) - the user is told to check their email.
  try {
    await mailer.sendMail({
      from: process.env.EMAIL_FROM!,
      to: email,
      subject: "Alpha Agent password reset code",
      text:
        `Your Alpha Agent password reset code is ${code}.\n` +
        `It expires in ${CODE_TTL_MINUTES} minutes. ` +
        `If you did not request this, you can ignore this email.`,
    });
  } catch {
    // Swallow: the response stays identical whether mail sent or not.
  }

  return { ok: true };
}
```

Create `frontend/src/app/(auth)/forgot-password/page.tsx`:

```tsx
// frontend/src/app/(auth)/forgot-password/page.tsx
"use client";
//
// Email-only form -> D1 forgotPasswordAction. Always shows the same
// "if that email exists, a code was sent" confirmation (no enumeration).
// No useSearchParams, so no Suspense wrapper. tm-* token styling.
import { useState, useEffect } from "react";
import Link from "next/link";
import { forgotPasswordAction, type ForgotError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

const ERROR_KEY: Record<ForgotError, Parameters<typeof t>[1]> = {
  invalid: "forgot.error_invalid",
  rate_limited: "forgot.error_rate_limited",
};

export default function ForgotPasswordPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [errorKey, setErrorKey] = useState<Parameters<typeof t>[1] | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    const fd = new FormData();
    fd.set("email", email);
    const result = await forgotPasswordAction(fd);
    setSubmitting(false);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      return;
    }
    setSent(true);
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "forgot.title")}
      </h1>
      {sent ? (
        <p className="text-sm text-tm-muted">{t(locale, "forgot.sent_body")}</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs text-tm-muted">
            {t(locale, "forgot.email_label")}
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(locale, "forgot.email_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          {errorKey && (
            <p className="text-xs text-tm-neg">{t(locale, errorKey)}</p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
          >
            {t(locale, submitting ? "forgot.submitting" : "forgot.submit_button")}
          </button>
        </form>
      )}
      <p className="mt-4 text-center text-xs text-tm-muted">
        <Link href="/reset-password" className="text-tm-accent hover:underline">
          {t(locale, "forgot.have_code_link")}
        </Link>
        {" · "}
        <Link href="/signin" className="text-tm-accent hover:underline">
          {t(locale, "forgot.back_to_signin")}
        </Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/forgot-password/__tests__/actions.test.ts"
```

Expected: 5/5 PASS. Also `npx tsc --noEmit` (the `forgot.*` i18n keys are added in E1 - same Option-A note as C2; the implementer may add the `forgot.*` key block from E1 Step 1 here to keep this task self-verifying).

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(auth)/forgot-password/actions.ts" \
  "frontend/src/app/(auth)/forgot-password/page.tsx" \
  "frontend/src/app/(auth)/forgot-password/__tests__/actions.test.ts"
git commit -m "feat(auth): forgot-password Server Action + page (phase4b D1)

forgotPasswordAction: rate-limit (reset_request 3/min) -> zod -> generate
a random 6-digit code -> store it bcryptjs-HASHED with a 15-min TTL ->
email the PLAINTEXT code via Resend SMTP (nodemailer, already a dep).
ALWAYS returns the same ok:true response whether or not the email is a
real user - no enumeration. /forgot-password is an email-only form.
Unit test mocks the pg Pool + nodemailer, asserts identical response for
real vs ghost email and that the code is stored hashed."
```

---

### Task D2: reset-password Server Action + page

**Why:** Step two of the reset flow. The `"use server"` action takes `{email, code, newPassword}`, looks up the newest unused unexpired `password_reset_codes` row for that email, verifies the code with `verifyPassword` (the code is stored hashed), and on a match updates `users.password_hash` and flips `used = true` on the code row. Distinct errors for wrong / expired / used code so the user knows whether to re-request. The page is an email + code + new-password form.

**SECURITY callouts:**
- The code is compared via `verifyPassword` against the stored `code_hash` - the plaintext code never sits in the DB.
- Distinct error codes (`wrong_code` / `expired_code` / `used_code`) here are an *intentional* UX choice: the user must know whether to re-request a code. This is not user enumeration (the email is already supplied by the user; nothing about *account existence* leaks - a wrong-but-existent email simply finds no code row and returns `wrong_code`, same as a real email with a wrong code).
- The new password is re-validated by zod (8-32 chars) and hashed with `hashPassword` before the `UPDATE`.
- The code row is marked `used = true` in the same flow so a code is strictly single-use.

**Files:**
- Create: `frontend/src/app/(auth)/reset-password/actions.ts`
- Create: `frontend/src/app/(auth)/reset-password/page.tsx`
- Create: `frontend/src/app/(auth)/reset-password/__tests__/actions.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/(auth)/reset-password/__tests__/actions.test.ts`:

```typescript
// frontend/src/app/(auth)/reset-password/__tests__/actions.test.ts
//
// resetPasswordAction talks to Postgres (pg Pool). Mocked. password.ts is
// NOT mocked - the test seeds a real bcrypt hash of the code into the
// fake "code row" so verifyPassword exercises the real comparison.
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockQuery = vi.fn();
vi.mock("pg", () => ({
  Pool: vi.fn(() => ({ query: mockQuery })),
}));

import { resetPasswordAction } from "@/app/(auth)/reset-password/actions";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

function formDataOf(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
}

const FUTURE = new Date(Date.now() + 10 * 60_000).toISOString();
const PAST = new Date(Date.now() - 10 * 60_000).toISOString();

beforeEach(() => {
  mockQuery.mockReset();
});

describe("resetPasswordAction", () => {
  it("rejects a wrong code (no matching unused unexpired row found)", async () => {
    // The lookup query returns no row (a wrong code finds nothing, OR a
    // real row exists but the code does not verify - this test: no row).
    mockQuery.mockResolvedValueOnce({ rows: [], rowCount: 0 });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "000000", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("wrong_code");
  });

  it("rejects a code whose hash does not verify (wrong code, row exists)", async () => {
    // A row exists but its code_hash is for a DIFFERENT code.
    const otherHash = await hashPassword("999999");
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: 1, code_hash: otherHash, expires_at: FUTURE, used: false }],
      rowCount: 1,
    });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("wrong_code");
  });

  it("rejects an expired code", async () => {
    const codeHash = await hashPassword("123456");
    // The action's lookup filters expires_at > now(), so an expired code
    // yields no row - but to give a DISTINCT expired error the action does
    // a second lookup ignoring expiry. Seed: first lookup empty, second
    // lookup returns the expired row.
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: PAST, used: false }],
        rowCount: 1,
      });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("expired_code");
  });

  it("rejects an already-used code", async () => {
    const codeHash = await hashPassword("123456");
    mockQuery
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: FUTURE, used: true }],
        rowCount: 1,
      });
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("used_code");
  });

  it("rejects a short new password via zod", async () => {
    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "short" }),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toBe("invalid");
    expect(mockQuery).not.toHaveBeenCalled();
  });

  it("succeeds: updates users.password_hash and marks the code used", async () => {
    const codeHash = await hashPassword("123456");
    mockQuery
      // 1: lookup the newest unused unexpired row -> match.
      .mockResolvedValueOnce({
        rows: [{ id: 1, code_hash: codeHash, expires_at: FUTURE, used: false }],
        rowCount: 1,
      })
      // 2: UPDATE users SET password_hash.
      .mockResolvedValueOnce({ rows: [], rowCount: 1 })
      // 3: UPDATE password_reset_codes SET used = true.
      .mockResolvedValueOnce({ rows: [], rowCount: 1 });

    const result = await resetPasswordAction(
      formDataOf({ email: "a@b.com", code: "123456", newPassword: "longenough1" }),
    );
    expect(result.ok).toBe(true);

    // Query 2 is the password UPDATE; its params carry a real bcrypt hash
    // of the new password, not the plaintext.
    const updateParams = mockQuery.mock.calls[1][1] as string[];
    expect(updateParams).not.toContain("longenough1");
    const newHash = updateParams.find((p) => p.startsWith("$2"));
    expect(await verifyPassword("longenough1", newHash as string)).toBe(true);

    // Query 3 marks the code used.
    const usedSql = mockQuery.mock.calls[2][0] as string;
    expect(usedSql).toMatch(/UPDATE password_reset_codes/i);
    expect(usedSql).toMatch(/used = true/i);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/reset-password/__tests__/actions.test.ts"
```

Expected: FAIL to load - `Failed to resolve import "@/app/(auth)/reset-password/actions"`.

- [ ] **Step 3: Write the action + the page**

Create `frontend/src/app/(auth)/reset-password/actions.ts`:

```typescript
// frontend/src/app/(auth)/reset-password/actions.ts
"use server";
//
// Step 2 of self-serve password reset. Takes {email, code, newPassword}:
// zod-validate -> look up the newest unused unexpired password_reset_codes
// row for the email -> verifyPassword(code, row.code_hash) -> on match,
// UPDATE users.password_hash + flip used=true. Distinct errors for
// wrong / expired / used so the user knows whether to re-request.
import { Pool } from "pg";
import { z } from "zod";
import { hashPassword, verifyPassword } from "@/lib/auth/password";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

const resetSchema = z.object({
  email: z.string().email(),
  code: z.string().regex(/^\d{6}$/),
  newPassword: z.string().min(8).max(32),
});

export type ResetError =
  | "invalid"
  | "wrong_code"
  | "expired_code"
  | "used_code"
  | "server_error";

export type ResetResult = { ok: true } | { ok: false; error: ResetError };

interface CodeRow {
  id: number;
  code_hash: string;
  expires_at: string;
  used: boolean;
}

export async function resetPasswordAction(
  formData: FormData,
): Promise<ResetResult> {
  const parsed = resetSchema.safeParse({
    email: String(formData.get("email") ?? ""),
    code: String(formData.get("code") ?? ""),
    newPassword: String(formData.get("newPassword") ?? ""),
  });
  if (!parsed.success) return { ok: false, error: "invalid" };
  const { email, code, newPassword } = parsed.data;

  try {
    // Newest unused unexpired code row for this email.
    const fresh = await pool.query(
      `SELECT id, code_hash, expires_at, used
         FROM password_reset_codes
        WHERE email = $1 AND used = false AND expires_at > now()
        ORDER BY created_at DESC
        LIMIT 1`,
      [email],
    );
    const freshRow = fresh.rows[0] as CodeRow | undefined;

    if (!freshRow) {
      // No fresh row. Distinguish "expired/used code that DID exist" from
      // "no code at all / wrong email" by a second lookup ignoring the
      // freshness filters.
      const any = await pool.query(
        `SELECT id, code_hash, expires_at, used
           FROM password_reset_codes
          WHERE email = $1
          ORDER BY created_at DESC
          LIMIT 1`,
        [email],
      );
      const anyRow = any.rows[0] as CodeRow | undefined;
      if (anyRow && (await verifyPassword(code, anyRow.code_hash))) {
        if (anyRow.used) return { ok: false, error: "used_code" };
        return { ok: false, error: "expired_code" };
      }
      return { ok: false, error: "wrong_code" };
    }

    // A fresh row exists - the supplied code must verify against its hash.
    const codeOk = await verifyPassword(code, freshRow.code_hash);
    if (!codeOk) return { ok: false, error: "wrong_code" };

    // Match. Hash the new password, update the user, single-use the code.
    const newHash = await hashPassword(newPassword);
    await pool.query(`UPDATE users SET password_hash = $1 WHERE email = $2`, [
      newHash,
      email,
    ]);
    await pool.query(
      `UPDATE password_reset_codes SET used = true WHERE id = $1`,
      [freshRow.id],
    );
    return { ok: true };
  } catch {
    return { ok: false, error: "server_error" };
  }
}
```

Create `frontend/src/app/(auth)/reset-password/page.tsx`:

```tsx
// frontend/src/app/(auth)/reset-password/page.tsx
"use client";
//
// email + 6-digit code + new password form -> D2 resetPasswordAction.
// On success, links the user to /signin to log in with the new password.
// No useSearchParams, so no Suspense wrapper. tm-* token styling.
import { useState, useEffect } from "react";
import Link from "next/link";
import { resetPasswordAction, type ResetError } from "./actions";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

const ERROR_KEY: Record<ResetError, Parameters<typeof t>[1]> = {
  invalid: "reset.error_invalid",
  wrong_code: "reset.error_wrong_code",
  expired_code: "reset.error_expired_code",
  used_code: "reset.error_used_code",
  server_error: "reset.error_server",
};

export default function ResetPasswordPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [errorKey, setErrorKey] = useState<Parameters<typeof t>[1] | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorKey(null);
    const fd = new FormData();
    fd.set("email", email);
    fd.set("code", code);
    fd.set("newPassword", newPassword);
    const result = await resetPasswordAction(fd);
    setSubmitting(false);
    if (!result.ok) {
      setErrorKey(ERROR_KEY[result.error]);
      return;
    }
    setDone(true);
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "reset.title")}
      </h1>
      {done ? (
        <p className="text-sm text-tm-muted">
          {t(locale, "reset.done_body")}{" "}
          <Link href="/signin" className="text-tm-accent hover:underline">
            {t(locale, "reset.done_signin_link")}
          </Link>
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.email_label")}
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t(locale, "reset.email_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.code_label")}
          </label>
          <input
            type="text"
            required
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t(locale, "reset.code_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          <label className="block text-xs text-tm-muted">
            {t(locale, "reset.new_password_label")}
          </label>
          <input
            type="password"
            required
            minLength={8}
            maxLength={32}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={t(locale, "reset.new_password_placeholder")}
            className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
          />
          {errorKey && (
            <p className="text-xs text-tm-neg">{t(locale, errorKey)}</p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
          >
            {t(locale, submitting ? "reset.submitting" : "reset.submit_button")}
          </button>
        </form>
      )}
      <p className="mt-4 text-center text-xs text-tm-muted">
        <Link href="/forgot-password" className="text-tm-accent hover:underline">
          {t(locale, "reset.need_code_link")}
        </Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx vitest run "src/app/(auth)/reset-password/__tests__/actions.test.ts"
```

Expected: 6/6 PASS. Also `npx tsc --noEmit` (the `reset.*` i18n keys are added in E1 - same Option-A note as C2/D1; the implementer may add the `reset.*` key block from E1 Step 1 here to keep this task self-verifying).

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(auth)/reset-password/actions.ts" \
  "frontend/src/app/(auth)/reset-password/page.tsx" \
  "frontend/src/app/(auth)/reset-password/__tests__/actions.test.ts"
git commit -m "feat(auth): reset-password Server Action + page (phase4b D2)

resetPasswordAction: zod {email, code, newPassword} -> look up the newest
unused unexpired password_reset_codes row -> verifyPassword(code,
code_hash) -> on match UPDATE users.password_hash + flip used=true.
Distinct wrong_code / expired_code / used_code errors so the user knows
whether to re-request. New password re-validated by zod and hashed before
the UPDATE; code is strictly single-use. Unit test mocks the pg Pool,
covers wrong / expired / used / short-password / success paths."
```

---

## Phase E - Signin UI

### Task E1: i18n keys - register / forgot / reset / signin / error mapping

**Why:** Every Phase 4b page (`/register`, `/forgot-password`, `/reset-password`, the reworked `/signin`, the reworked `/signin/error`) references new `TranslationKey`s. This task adds all of them, verbatim, to **both** the `zh` and `en` blocks of `frontend/src/lib/i18n.ts`. `i18n.ts` is ~1106 lines; `const translations = { zh: { ...keys... }, en: { ...keys... } }`, and `export type TranslationKey = keyof (typeof translations)["zh"]` - so a key added to `zh` but not `en` (or vice versa) is a type error. The zh block's last existing keys are around `"signin.*"` / `"auth.account"`; the en block mirrors.

**Sequencing note (matches C2 / D1 / D2 Option A):** because the strict execution order runs C2 / D1 / D2 *before* E1, those earlier page tasks each may add their own key subset (`register.*` in C2, `forgot.*` in D1, `reset.*` in D2) to stay self-verifying. If they did, E1 only adds whatever remains - in practice the `signin.*` additions and the `signin.error_*` mapping keys, plus any subset the earlier tasks chose to defer. **The key-by-key content below is the single source of truth** regardless of which task physically inserts each block: an implementer adding `register.*` early MUST copy the exact strings from this section.

**Non-TDD task** (i18n data only - verified by `tsc --noEmit`, which is what enforces the zh/en key parity).

**Files:**
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: The full verbatim key list (both locales)**

Add the following keys inside the `zh` object of `translations` (append after the existing `signin.*` / `auth.*` keys - exact placement does not matter, only that they are inside the `zh` object):

```typescript
  // --- Phase 4b: registration -------------------------------------------
  "register.title": "注册账户",
  "register.email_label": "邮箱",
  "register.email_placeholder": "you@example.com",
  "register.password_label": "密码",
  "register.password_placeholder": "8 到 32 个字符",
  "register.confirm_label": "确认密码",
  "register.confirm_placeholder": "再次输入密码",
  "register.submit_button": "注册",
  "register.submitting": "注册中...",
  "register.have_account": "已有账户？",
  "register.signin_link": "去登录",
  "register.error_invalid": "请检查邮箱格式，密码需 8 到 32 个字符且两次输入一致。",
  "register.error_rate_limited": "尝试过于频繁，请稍后再试。",
  "register.error_email_taken": "该邮箱已注册，请直接登录。",
  "register.error_server": "服务器出错，请稍后再试。",
  // --- Phase 4b: forgot password ----------------------------------------
  "forgot.title": "找回密码",
  "forgot.email_label": "邮箱",
  "forgot.email_placeholder": "you@example.com",
  "forgot.submit_button": "发送验证码",
  "forgot.submitting": "发送中...",
  "forgot.sent_body": "如果该邮箱已注册，我们已发送一个 6 位验证码，15 分钟内有效。",
  "forgot.have_code_link": "已有验证码？去重置密码",
  "forgot.back_to_signin": "返回登录",
  "forgot.error_invalid": "请输入有效的邮箱地址。",
  "forgot.error_rate_limited": "请求过于频繁，请稍后再试。",
  // --- Phase 4b: reset password -----------------------------------------
  "reset.title": "重置密码",
  "reset.email_label": "邮箱",
  "reset.email_placeholder": "you@example.com",
  "reset.code_label": "验证码",
  "reset.code_placeholder": "6 位数字验证码",
  "reset.new_password_label": "新密码",
  "reset.new_password_placeholder": "8 到 32 个字符",
  "reset.submit_button": "重置密码",
  "reset.submitting": "重置中...",
  "reset.done_body": "密码已重置。",
  "reset.done_signin_link": "去登录",
  "reset.need_code_link": "还没有验证码？去找回密码",
  "reset.error_invalid": "请检查邮箱、6 位验证码和新密码（8 到 32 个字符）。",
  "reset.error_wrong_code": "验证码不正确，请重新输入。",
  "reset.error_expired_code": "验证码已过期，请重新申请。",
  "reset.error_used_code": "验证码已被使用，请重新申请。",
  "reset.error_server": "服务器出错，请稍后再试。",
  // --- Phase 4b: signin reworked (password + Google) --------------------
  "signin.password_label": "密码",
  "signin.password_placeholder": "输入密码",
  "signin.signin_button": "登录",
  "signin.signing_in": "登录中...",
  "signin.google_button": "使用 Google 登录",
  "signin.register_link": "还没有账户？去注册",
  "signin.forgot_link": "忘记密码？",
  // --- Phase 4b: signin error page ?error= mapping ----------------------
  "signin.error_credentials": "邮箱或密码不正确。",
  "signin.error_oauth_not_linked": "该邮箱已用其他方式注册，请用原方式登录。",
  "signin.error_configuration": "登录服务配置有误，请联系管理员。",
  "signin.error_verification": "登录链接无效或已过期。",
  "signin.error_default": "登录时出现问题，请重试。",
```

Add the **matching** keys inside the `en` object of `translations`:

```typescript
  // --- Phase 4b: registration -------------------------------------------
  "register.title": "Create account",
  "register.email_label": "Email",
  "register.email_placeholder": "you@example.com",
  "register.password_label": "Password",
  "register.password_placeholder": "8 to 32 characters",
  "register.confirm_label": "Confirm password",
  "register.confirm_placeholder": "Re-enter your password",
  "register.submit_button": "Register",
  "register.submitting": "Registering...",
  "register.have_account": "Already have an account?",
  "register.signin_link": "Sign in",
  "register.error_invalid": "Check the email format; password must be 8 to 32 characters and both entries must match.",
  "register.error_rate_limited": "Too many attempts, please try again shortly.",
  "register.error_email_taken": "That email is already registered. Please sign in instead.",
  "register.error_server": "Server error, please try again later.",
  // --- Phase 4b: forgot password ----------------------------------------
  "forgot.title": "Reset your password",
  "forgot.email_label": "Email",
  "forgot.email_placeholder": "you@example.com",
  "forgot.submit_button": "Send code",
  "forgot.submitting": "Sending...",
  "forgot.sent_body": "If that email is registered, we sent a 6-digit code. It is valid for 15 minutes.",
  "forgot.have_code_link": "Already have a code? Reset your password",
  "forgot.back_to_signin": "Back to sign in",
  "forgot.error_invalid": "Please enter a valid email address.",
  "forgot.error_rate_limited": "Too many requests, please try again shortly.",
  // --- Phase 4b: reset password -----------------------------------------
  "reset.title": "Set a new password",
  "reset.email_label": "Email",
  "reset.email_placeholder": "you@example.com",
  "reset.code_label": "Code",
  "reset.code_placeholder": "6-digit code",
  "reset.new_password_label": "New password",
  "reset.new_password_placeholder": "8 to 32 characters",
  "reset.submit_button": "Reset password",
  "reset.submitting": "Resetting...",
  "reset.done_body": "Your password has been reset.",
  "reset.done_signin_link": "Sign in",
  "reset.need_code_link": "No code yet? Request a reset code",
  "reset.error_invalid": "Check the email, 6-digit code, and new password (8 to 32 characters).",
  "reset.error_wrong_code": "That code is not correct. Please re-enter it.",
  "reset.error_expired_code": "That code has expired. Please request a new one.",
  "reset.error_used_code": "That code was already used. Please request a new one.",
  "reset.error_server": "Server error, please try again later.",
  // --- Phase 4b: signin reworked (password + Google) --------------------
  "signin.password_label": "Password",
  "signin.password_placeholder": "Enter your password",
  "signin.signin_button": "Sign in",
  "signin.signing_in": "Signing in...",
  "signin.google_button": "Sign in with Google",
  "signin.register_link": "No account yet? Register",
  "signin.forgot_link": "Forgot your password?",
  // --- Phase 4b: signin error page ?error= mapping ----------------------
  "signin.error_credentials": "Incorrect email or password.",
  "signin.error_oauth_not_linked": "That email is already registered with a different method. Use the original method to sign in.",
  "signin.error_configuration": "The sign-in service is misconfigured. Please contact the administrator.",
  "signin.error_verification": "The sign-in link is invalid or has expired.",
  "signin.error_default": "Something went wrong while signing in. Please try again.",
```

Note on existing keys: the current `signin/page.tsx` and `signin/error/page.tsx` reference `signin.title`, `signin.email_label`, `signin.email_placeholder`, `signin.send_button`, `signin.sending`, `signin.error_title`, `signin.error_body`, `signin.back_to_signin`. **Do NOT delete those existing keys** - E2's reworked pages still use `signin.title`, `signin.email_label`, `signin.email_placeholder`, `signin.error_title`, and `signin.back_to_signin`. `signin.send_button` / `signin.sending` / `signin.error_body` become unused after E2 but leave them in place (deleting an unused i18n key is churn with no benefit, and `tsc` does not flag unused keys).

- [ ] **Step 2: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -8
```

Expected: `tsc` silent (this is the real check - it enforces zh/en key parity; a key in one block but not the other is a `TranslationKey` type error). `next lint` clean, `next build` succeeds. If C2/D1/D2 already added their `register.*`/`forgot.*`/`reset.*` subsets (Option A), E1 must NOT re-add them - a duplicate object key is a lint error; E1 then adds only the not-yet-present blocks.

- [ ] **Step 3: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/i18n.ts
git commit -m "feat(i18n): register / forgot / reset / signin keys, zh + en (phase4b E1)

Adds the Phase 4b TranslationKeys to both the zh and en blocks: register.*
(form labels + 4 error codes), forgot.* (email form + sent confirmation),
reset.* (code form + wrong/expired/used error codes), new signin.*
(password label, Google button, register/forgot links), and the
signin.error_* set the reworked /signin/error page maps NextAuth ?error=
codes onto. Existing signin.* keys kept (E2's pages still use several)."
```

---

### Task E2: /signin rework + /signin/error rework

**Why:** The two existing signin pages still assume magic-link. `signin/page.tsx`'s `SignInForm` needs to become a password form (`signIn("credentials", {email, password, callbackUrl})`) plus a "Sign in with Google" button (`signIn("google", {callbackUrl})`) plus links to `/register` and `/forgot-password`. `signin/error/page.tsx` needs to read `useSearchParams().get("error")` and map NextAuth's error codes to specific i18n messages instead of the current generic "link invalid" text.

**Suspense callout (the E1-of-M5 lesson):** `signin/page.tsx` already wraps `SignInForm` in `<Suspense>` because `SignInForm` uses `useSearchParams` - **keep that wrapper**. The reworked `signin/error/page.tsx` now *also* uses `useSearchParams` (to read `?error=`), so it **must also be wrapped in `<Suspense>`** - the current error page does not use `useSearchParams` and has no wrapper, so this task **adds** one. Without it, `next build` fails the static-prerender pass with a CSR-bailout error. This is the same class of bug as M5's E1 Suspense fix.

**Non-TDD task** (UI pages - verified by `tsc` + `lint` + `build`; `signIn` from `next-auth/react` is exercised by F1's UAT). The `credentials` and `google` provider ids it calls were wired in B3.

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx`
- Modify: `frontend/src/app/(auth)/signin/error/page.tsx`

- [ ] **Step 1: Rework signin/page.tsx**

Replace the entire contents of `frontend/src/app/(auth)/signin/page.tsx` with:

```tsx
// frontend/src/app/(auth)/signin/page.tsx
"use client";
//
// Phase 4b: password form + "Sign in with Google" + links to /register and
// /forgot-password. Replaces the magic-link email-only form. SignInForm
// uses useSearchParams (callbackUrl), so it stays wrapped in <Suspense> --
// removing the wrapper would fail the next build static-prerender pass.
import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function SignInForm() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") ?? "/picks";

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    // signIn handles the redirect: to callbackUrl on success, to
    // /signin/error?error=CredentialsSignin on a bad password.
    await signIn("credentials", { email, password, callbackUrl });
  };

  const onGoogle = async () => {
    await signIn("google", { callbackUrl });
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "signin.title")}
      </h1>
      <form onSubmit={onPasswordSubmit} className="space-y-3">
        <label className="block text-xs text-tm-muted">
          {t(locale, "signin.email_label")}
        </label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t(locale, "signin.email_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <label className="block text-xs text-tm-muted">
          {t(locale, "signin.password_label")}
        </label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t(locale, "signin.password_placeholder")}
          className="w-full rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-sm text-tm-fg"
        />
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
        >
          {t(locale, submitting ? "signin.signing_in" : "signin.signin_button")}
        </button>
      </form>
      <button
        type="button"
        onClick={onGoogle}
        className="mt-3 w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent"
      >
        {t(locale, "signin.google_button")}
      </button>
      <div className="mt-4 flex flex-col gap-1 text-center text-xs text-tm-muted">
        <Link href="/register" className="text-tm-accent hover:underline">
          {t(locale, "signin.register_link")}
        </Link>
        <Link href="/forgot-password" className="text-tm-accent hover:underline">
          {t(locale, "signin.forgot_link")}
        </Link>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}
```

- [ ] **Step 2: Rework signin/error/page.tsx**

Replace the entire contents of `frontend/src/app/(auth)/signin/error/page.tsx` with:

```tsx
// frontend/src/app/(auth)/signin/error/page.tsx
"use client";
//
// Phase 4b: read the NextAuth ?error= query param and show the real
// reason instead of a generic "link invalid" message. This page now uses
// useSearchParams, so the rendering component MUST be wrapped in
// <Suspense> - without it, next build fails the static-prerender pass
// (the same CSR-bailout class as the M5 E1 Suspense fix).
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { t, getLocaleFromStorage, type Locale, type TranslationKey } from "@/lib/i18n";

// NextAuth v5 error codes -> i18n keys (added in E1).
function errorKeyFor(code: string | null): TranslationKey {
  switch (code) {
    case "CredentialsSignin":
      return "signin.error_credentials";
    case "OAuthAccountNotLinked":
      return "signin.error_oauth_not_linked";
    case "Configuration":
      return "signin.error_configuration";
    case "Verification":
      return "signin.error_verification";
    default:
      return "signin.error_default";
  }
}

function SignInError() {
  const [locale, setLocale] = useState<Locale>("zh");
  const params = useSearchParams();
  const code = params.get("error");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-neg">
        {t(locale, "signin.error_title")}
      </h1>
      <p className="mb-4 text-sm text-tm-muted">
        {t(locale, errorKeyFor(code))}
      </p>
      <Link href="/signin" className="text-sm text-tm-accent hover:underline">
        {t(locale, "signin.back_to_signin")}
      </Link>
    </div>
  );
}

export default function SignInErrorPage() {
  return (
    <Suspense fallback={null}>
      <SignInError />
    </Suspense>
  );
}
```

- [ ] **Step 3: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -12
```

Expected: `tsc` silent, `next lint` clean, `next build` succeeds. Specifically confirm the build does **not** emit a "useSearchParams() should be wrapped in a suspense boundary" error for `/signin/error` - if it does, the `<Suspense>` wrapper in Step 2 was dropped.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(auth)/signin/page.tsx" \
  "frontend/src/app/(auth)/signin/error/page.tsx"
git commit -m "feat(auth): rework /signin to password + Google, map error codes (phase4b E2)

signin/page.tsx: SignInForm is now a password form
(signIn('credentials', {email, password, callbackUrl})) + a Google button
(signIn('google', {callbackUrl})) + links to /register and
/forgot-password. The <Suspense> wrapper stays (SignInForm uses
useSearchParams). signin/error/page.tsx now reads ?error= and maps
CredentialsSignin / OAuthAccountNotLinked / Configuration / Verification /
default to specific i18n messages - and gains a <Suspense> wrapper
because it now uses useSearchParams (the M5 E1 prerender lesson)."
```

---

## Phase F - Acceptance

### Task F1: phase4b-acceptance Makefile target + deploy + UAT + handoff

**Why:** A single reproducible target that runs the V003 migration test, the full frontend vitest suite, the frontend type/lint/build checks, and curl smokes against the deployed backend confirming the provider swap took effect. Plus the deploy verification, the manual UAT checklist from the spec, and the hand-off note.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append the phase4b-acceptance target**

Add to the end of `Makefile` (after `m5-acceptance`), mirroring the `m5-acceptance` target's style:

```makefile

phase4b-acceptance:
	@echo "==> Running Phase 4b acceptance suite"
	# Backend: the V003 migration test.
	pytest tests/auth/test_migration_v003.py -v
	# Frontend: deps clean, vitest suite, types clean, lint clean, builds.
	cd frontend && npm ci
	cd frontend && npm test
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: an unauthenticated backend route still rejects with 401
	# (Phase 4b must not have weakened the backend auth contract).
	@echo "==> Smoke: GET /api/user/me without auth -> 401"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  "https://alpha.bobbyzhong.com/api/user/me"); \
	  if [ "$$code" != "401" ]; then echo "expected 401 got $$code"; exit 1; fi
	# Smoke: the NextAuth providers endpoint lists credentials + google and
	# NOT nodemailer (proves the auth.ts provider swap deployed).
	@echo "==> Smoke: /api/auth/providers lists credentials + google, not nodemailer"
	@body=$$(curl -sS --max-time 10 "https://alpha.bobbyzhong.com/api/auth/providers"); \
	  echo "$$body" | grep -q '"credentials"' || (echo "providers missing credentials: $$body" && exit 1); \
	  echo "$$body" | grep -q '"google"' || (echo "providers missing google: $$body" && exit 1); \
	  if echo "$$body" | grep -q '"nodemailer"'; then echo "providers still lists nodemailer: $$body"; exit 1; fi
	# Smoke: /api/auth/session returns JSON (not the FastAPI 404 HTML) --
	# confirms next.config.mjs still excludes /api/auth/* from the rewrite.
	@echo "==> Smoke: /api/auth/session returns JSON"
	@ctype=$$(curl -sS -o /dev/null -w "%{content_type}" --max-time 10 \
	  "https://alpha.bobbyzhong.com/api/auth/session"); \
	  case "$$ctype" in application/json*) ;; *) echo "expected JSON, got $$ctype"; exit 1;; esac
	@echo "Phase 4b acceptance PASS"
```

- [ ] **Step 2: Run the pytest + frontend portion locally**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/auth/test_migration_v003.py -v 2>&1 | tail -10
cd frontend && npm test 2>&1 | tail -15
cd frontend && npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -10
```

Expected: migration test 7/7 PASS. `npm test` runs the full vitest suite - smoke (1) + password (4) + rate-limit (5) + register actions (5) + forgot actions (5) + reset actions (6) = **26 tests, all PASS**. `tsc` silent, `next lint` clean, `next build` succeeds with `/register`, `/forgot-password`, `/reset-password` in the route manifest.

- [ ] **Step 3: USER SETUP gate - env vars + migration**

> [!IMPORTANT]
> **USER SETUP - this step is the user's, not the implementer's.** The implementer prints these instructions and waits. The acceptance smokes will fail loudly until they are done.
>
> 1. **Add the Google OAuth env vars** to the frontend Vercel project (`frontend`), Production scope:
>    - `AUTH_GOOGLE_ID` = the Google OAuth client ID
>    - `AUTH_GOOGLE_SECRET` = the Google OAuth client secret
>
>    The user has **already created** the OAuth client in Google Cloud Console; this step is only pasting the two values into Vercel. Confirm the consent screen is **Published** (or the tester's Gmail is on the OAuth test-users list).
> 2. **Apply the V003 migration** to the Neon production DB. The orchestrator can run it the same way V002 was applied:
>    ```bash
>    python3 -c "import asyncio; from alpha_agent.storage.migrations.runner import apply_migrations; asyncio.run(apply_migrations('<DATABASE_URL>'))"
>    ```
>    The runner is idempotent - it applies only the not-yet-applied `V003`.
>
> No other env var changes. No backend env var is added by Phase 4b.

- [ ] **Step 4: Deploy (both projects auto-deploy on git push)**

Both the backend (`alpha-agent`) and the frontend (`frontend`, `rootDirectory=frontend`) Vercel projects auto-deploy on `git push origin main` - no manual `vercel` invocation needed. `next.config.mjs` already excludes `/api/auth/*` from the FastAPI rewrite (the G3 fix), so the reworked NextAuth routes are served by Next.js.

After the commits land, verify both deploys reach READY. If the Vercel API token is expired (403 / empty response - CLAUDE.md memory `feedback_vercel_authjson_token_expiry.md`), fall back to HTTP probes:

```bash
curl -I https://alpha.bobbyzhong.com/signin
curl -sS https://alpha.bobbyzhong.com/api/auth/providers | head -c 400
```

If a manual frontend deploy is ever needed, run it **from the repo root**, NOT from `frontend/` - with `rootDirectory=frontend` set, running from `frontend/` makes Vercel look for `frontend/frontend` (the doubled-path trap, memory `feedback_vercel_root_directory_doubled_path.md`).

- [ ] **Step 5: Run the full acceptance target**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
make phase4b-acceptance 2>&1 | tail -20
```

Expected: ends with `Phase 4b acceptance PASS`. If the `providers` smoke shows `nodemailer` still listed, the frontend deploy has not picked up the B3 `auth.ts` change yet - wait for the deploy to reach READY and re-run.

- [ ] **Step 6: Manual UAT**

Run the manual UAT checklist from the spec's Testing section:

1. Open `/register`, register a new account (email + password + matching confirm) -> redirected to `/picks`, signed in.
2. Sign out, open `/signin`, sign in with the same email + password -> back at `/picks`.
3. Sign out, open `/signin`, click "Sign in with Google", complete Google OAuth **with the same email** -> signed in, and the Google login links to the *same* `users` row (no duplicate account; check `accounts` has one row FK'd to that user).
4. Sign out, open `/forgot-password`, submit the account email -> "if that email exists, a code was sent" message; the 6-digit code arrives by email.
5. Open `/reset-password`, enter the email + the emailed code + a new password -> "password has been reset".
6. Open `/signin`, sign in with the **new** password -> signed in.
7. Negative: `/signin` with a wrong password -> redirected to `/signin/error` showing the "Incorrect email or password" message (mapped from `CredentialsSignin`).
8. Negative: `/reset-password` with a wrong 6-digit code -> "that code is not correct"; with an expired code -> "that code has expired"; re-using a consumed code -> "that code was already used".
9. Negative: submit `/register` 4 times in a minute with the same email -> the 4th is rate-limited.
10. Confirm `/forgot-password` returns the identical confirmation for a known email and a never-registered email.
11. Toggle locale zh <-> en on every new page - all `register.*` / `forgot.*` / `reset.*` / `signin.*` strings render in both.

Capture screenshots of the register flow, the password sign-in, the Google button, and the `/signin/error` mapped message into `docs/superpowers/screenshots/phase4b-*.png`.

- [ ] **Step 7: Commit + handoff**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
mkdir -p docs/superpowers/screenshots
git add Makefile docs/superpowers/screenshots/
git commit -m "ci(phase4b): phase4b-acceptance Makefile target + UAT screenshots

Encodes the V003 migration test + the full frontend vitest suite (26
tests) + tsc/lint/build + curl smokes: an unauthenticated backend route
still 401s (backend contract untouched), /api/auth/providers lists
credentials + google and NOT nodemailer (the auth.ts swap deployed), and
/api/auth/session returns JSON not the FastAPI 404. Acceptance
reproducible by 'make phase4b-acceptance'. Manual UAT covers register ->
password login -> Google same-email account-link -> forgot -> reset ->
login-with-new-password plus the rate-limit and error-mapping negatives.

Phase 4b SHIPS: email+password login + Google OAuth live; magic-link
login removed; self-serve password reset live."
git push origin main
```

> **Hand-off note for the orchestrator:** after the push, the user must hard-refresh any open tab (Cmd+Shift+R) - a cold rebuild re-signs the Server Action content hashes, so an old client bundle would otherwise hit `Failed to find Server Action "<hash>"` on the new `/register`, `/forgot-password`, `/reset-password` pages (CLAUDE.md memory `feedback_nextjs_server_action_stale_hash.md`).

---

## Hand-off

**After Phase 4b acceptance + visual approval, multi-method auth is complete.** The alpha-agent frontend now offers email+password login and Google OAuth, magic-link login is removed, and self-serve password reset is live. The FastAPI backend auth contract (`require_user`, `jwt_verify`, the middleware HS256 re-mint) was not touched - all three login methods produce the same session JWE.

**Phase 4b -> next-phase contract:**

| Phase 4b output | Downstream consumer |
|-----------------|---------------------|
| `users.password_hash` + the `accounts` table | Any future "linked accounts" UI reads `accounts` directly; no schema change needed to add a second OAuth provider (just a provider entry in `auth.ts`). |
| `lib/auth/rate-limit.ts` | Reusable for any future Server Action that needs throttling - just add a key to `RATE_LIMITS`. |
| `lib/auth/password.ts` | The single hash/verify audit point; a future password-change-while-signed-in flow reuses it. |
| `vitest` + the `test` script | The frontend now has a real test runner; future frontend work writes `*.test.ts` files instead of relying only on `tsc`/`lint`/`build`. |
| The `"use server"` action pattern (C1/D1/D2) | The first Server Actions in the project - the established shape (module-level pool, zod parse, structured result, no thrown errors crossing the boundary) is the template for all future actions. |

---

## Risk Matrix

Inherits the spec's Risks section in full. Implementation-specific additions:

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `accounts` table column casing mismatches `@auth/pg-adapter` (the G2 bug class - the plan author's memory was already wrong about `emailVerified` once) | Medium | A1 Step 3 makes the implementer `grep` the installed `node_modules/@auth/pg-adapter` source for the real column list **before** writing the SQL, and `test_migration_v003.py` asserts the double-quoted `"userId"` / `"providerAccountId"` columns + the FK + the unique constraint. If the audit disagrees with the plan's list, the implementer matches the audit and notes it in the commit. |
| `bcryptjs` reaches the edge bundle (imported into an edge-reachable module) | Low | `password.ts` is Node-only and is imported only by `auth.ts`'s `authorize()` (Node route handler) and the `"use server"` actions; never by `auth.config.ts` or `middleware.ts`. `bcryptjs` is pure JS so even an accidental import would not break the build, but the import-graph discipline is stated in `password.ts`'s header and in B2's SECURITY callout. `next build` would surface a true edge-runtime violation. |
| `/signin/error` (and `/register`, `/forgot-password`, `/reset-password`) fail `next build`'s static-prerender pass for missing `<Suspense>` | Medium | E2 explicitly **adds** a `<Suspense>` wrapper to `signin/error/page.tsx` (it newly uses `useSearchParams`) and keeps the existing wrapper on `signin/page.tsx`. `/register`, `/forgot-password`, `/reset-password` deliberately do NOT use `useSearchParams`, so they need no wrapper - stated in each page task. E2 Step 3 explicitly checks the build for the CSR-bailout error. Same class as the M5 E1 Suspense fix. |
| `next-auth ^5.0.0-beta.31` export paths for `providers/credentials` / `providers/google` differ from the plan | Medium | B3 Step 3 says: if the import fails, stop and report `NEEDS_CONTEXT` with the exact error - do not guess at the v5 beta surface. The controller fetches the current Auth.js v5 docs via context7 and re-dispatches. |
| C2 / D1 / D2 run before E1, so their pages reference i18n keys that do not exist yet -> mid-plan `tsc` failure | Medium | Each page task carries an explicit "Option A" instruction: add that task's own key subset (`register.*` / `forgot.*` / `reset.*`) to `i18n.ts` as part of the task, copying verbatim from E1 Step 1 (the single source of truth). E1 then adds only the remaining blocks and must not duplicate keys (a duplicate object key is a lint error). |
| `allowDangerousEmailAccountLinking` lets a Google-account holder link to a same-email password account | Accepted | Per the spec: controlling the Google account for that exact email is itself proof of email ownership; with open + unverified registration the no-linking alternative (orphaned duplicate accounts) is strictly worse. |
| `auth_rate_limit` table grows unbounded | Low | A cleanup is cheap (`DELETE FROM auth_rate_limit WHERE window_start < now() - interval '1 day'`); the V003 SQL comment notes it. No cron in this phase - the row count is tiny at personal scale. |
| The `forgot-password` action inserts a code row + sends mail even for a non-existent email | Accepted (intentional) | This is what keeps the response and timing indistinguishable between a real and a ghost email (no user enumeration). The orphan code row is harmless and is never consumable. |
| Resend `.edu.cn` delivery still fails for the password-reset email | Accepted and scoped | Reset is a rare path, not every login (that was the whole point of removing magic-link). The user can use a mainstream email for the reset. |

---

## LOC Estimate

- **Backend:** ~95 LOC (V003 migration ~55 + `test_migration_v003.py` ~40).
- **Frontend:** ~840 LOC (vitest config 15 + smoke test 5 + `password.ts` 25 + `rate-limit.ts` 70 + password/rate-limit tests 90 + `auth.ts` rewrite 55 + register action 75 + register page 95 + forgot action 70 + forgot page 70 + reset action 85 + reset page 95 + three action tests 165 + i18n keys 60 + signin page 110 + signin error page 75 - shared boilerplate).
- **Plan total: ~935 LOC of new+modified code across 11 tasks.**

---

## Execution Tip

The critical-path ordering is **A1 -> B1 -> B2 -> B3 -> C1 -> C2 -> D1 -> D2 -> E1 -> E2 -> F1**, strictly sequential.

Two things to get right early:

1. **B1 must come first in Phase B.** There is no frontend test runner today - every later frontend TDD task (`B2`, `C1`, `D1`, `D2`) assumes `vitest` exists. If `npx vitest run` does not pass at the end of B1, stop; nothing downstream can be RED-then-GREEN.
2. **The `i18n.ts` sequencing.** The strict order runs the page tasks (C2/D1/D2) before E1, but those pages reference keys E1 owns. Every page task carries the "Option A" instruction to add its own key subset inline so it stays self-verifying. The implementer must treat E1 Step 1 as the single source of truth for every key's text and never re-add a key E1 already placed (duplicate object keys fail lint).

The single biggest external-API risk is `next-auth ^5.0.0-beta.31`'s exact provider export paths (B3). If the implementer hits an import mismatch on `next-auth/providers/credentials` or `next-auth/providers/google`, the right move is `NEEDS_CONTEXT` with the specific error - the controller can fetch the current Auth.js v5 docs via context7 and re-dispatch. Do not guess at the v5 beta API.

And the hard boundary, restated: `auth.config.ts`, `middleware.ts`, and the entire backend are **never modified**. Any task that thinks it needs to touch them has misread the plan.

