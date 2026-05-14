# Phase 4b: Multi-Method Auth Design

**Date:** 2026-05-14
**Status:** Approved (brainstorm complete, ready for writing-plans)
**Builds on:** `2026-05-14-phase4-auth-and-server-byok.md` (M5, shipped)

## Goal

Add two login methods to the alpha-agent frontend, alongside the existing
NextAuth.js v5 setup: email + password (NextAuth Credentials provider) and
Google OAuth. The email magic-link method is removed as a login path. A
self-serve password-reset flow (6-digit emailed code) is included. The
separate FastAPI backend's auth contract (`require_user`, `jwt_verify`, the
middleware HS256 re-mint) stays unchanged.

## Context

M5 shipped NextAuth.js v5 with email magic-link only: `auth.ts` (full config,
pg-adapter) + `auth.config.ts` (edge-safe, used by middleware), JWT session
strategy, `@auth/pg-adapter` on Neon Postgres. The Next.js middleware decrypts
the NextAuth session JWE and re-mints a short-lived HS256 JWS injected as
`Authorization: Bearer`, which the FastAPI backend verifies. Magic-link
delivery proved unreliable for the primary audience (`.edu.cn` addresses
silently quarantine mail from a new domain). Account + password matches
mainstream user habits; Google OAuth removes the email dependency from login
entirely.

## Locked decisions (brainstorm Q1 to Q5 + research)

1. **Login methods:** email+password and Google OAuth. Magic-link is removed
   from login. Resend SMTP is retained only for password-reset emails (a low
   frequency path, not every login).
2. **Password reset:** implemented in this phase. 6-digit code emailed via
   Resend, our own flow (not NextAuth's verification-token mechanism).
3. **Registration:** open (anyone can register), no email verification on
   signup. Abuse is mitigated by rate limiting, not by a mandatory email
   round-trip (which would re-introduce the `.edu.cn` delivery problem at the
   registration step).
4. **Account linking:** same email auto-links across password and Google
   (`allowDangerousEmailAccountLinking: true` on the Google provider). A Google
   sign-in proves email ownership, which also compensates for skipping email
   verification at signup.
5. **Auth library:** stay on NextAuth.js v5. Add the Credentials provider.
   Research confirmed Auth.js v5's "discouragement" of Credentials is a soft
   warning, not a ban, and the docs give the careful pattern. Switching to
   Better Auth would force a rewrite of the edge-split config + middleware
   re-mint + FastAPI JWT contract: a net loss for a working setup. Lucia is
   deprecated (2025-03). Managed providers conflict with the
   FastAPI-verifies-the-JWT architecture.

## Non-goals

- 2FA / passkeys / WebAuthn (future phase if needed).
- Changing the backend `require_user` / `jwt_verify` / middleware re-mint.
  All three login methods produce the same NextAuth session JWE; the middleware
  does not care how the session was created.
- Migrating off NextAuth.js v5 (revisit Better Auth only if 2FA/org features
  are later required).
- OAuth providers other than Google (GitHub etc. are out of scope).
- Email verification on signup.
- Database-backed sessions (JWT strategy stays; it is required by the
  Credentials provider anyway).

## Architecture

The change is frontend-heavy plus one backend migration.

**Backend:** a single `V003` migration. No route, dependency, or middleware
code changes. `require_user`, `jwt_verify`, and the middleware HS256 re-mint
all stay exactly as M5 / G1 left them.

**Frontend:** NextAuth config changes (`auth.ts` only, not `auth.config.ts`),
a reworked `/signin` page, new `/register` + `/forgot-password` +
`/reset-password` pages and their Server Actions, a Postgres-backed rate-limit
helper, and i18n keys.

### Why the backend contract is untouched

The Credentials provider and the Google provider both produce the same
NextAuth session JWE that magic-link produced. The `authorize()` callback (for
Credentials) and the OAuth callback (for Google) each return a user object
whose `id` flows into the JWT via the existing `jwt` callback
(`if (user?.id) token.sub = String(user.id)`). The middleware still decrypts
that JWE and re-mints the HS256 JWS with `sub = user.id`. FastAPI verification
is identical. `auth.config.ts` (edge-safe, `providers: []`) does not change.

### Edge-runtime safety

The Credentials `authorize()` callback runs only in the Node route handler
(`/api/auth/[...nextauth]`), never in middleware/edge. Password hashing
therefore never reaches the edge runtime. We still use `bcryptjs` (pure JS,
not native `bcrypt`/`argon2`) so that if a hashing helper is ever imported
into an edge-reachable module the build does not break. Keep the import graph
clean: hashing helpers live in a Node-only `lib/` module, never imported by
`auth.config.ts` or `middleware.ts`.

## Data model: V003 migration

`alpha_agent/storage/migrations/V003__phase4b_multi_auth.sql`, additive only.

### 1. `users.password_hash`
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
```
Nullable: Google-only users have no password; password-only users have no
linked OAuth account. This is the one `ALTER TABLE` in V003 and it is safe
(adds a nullable column, no rewrite).

### 2. `accounts` table (NextAuth pg-adapter standard schema)
Adding an OAuth provider means the adapter's `linkAccount` /
`getUserByAccount` are now called at runtime. V002 deliberately skipped this
table because email-only did not need it.

The implementer MUST verify the exact column names and types against
`frontend/node_modules/@auth/pg-adapter` source (the same audit G2 did for
`users`). The adapter uses double-quoted camelCase identifiers. From the G2
audit the `accounts` columns are: `id`, `"userId"`, `type`, `provider`,
`"providerAccountId"`, `refresh_token`, `access_token`, `expires_at`,
`token_type`, `scope`, `id_token`, `session_state`. `"userId"` is a FK to
`users(id)` with `ON DELETE CASCADE`. PK is `id`; there is also a unique
constraint on `(provider, "providerAccountId")`.

### 3. `password_reset_codes` table
```sql
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
```
The 6-digit code is stored hashed (bcryptjs), never in plaintext. TTL 15
minutes (`expires_at`). Single-use (`used` flag flipped on consumption). Not
FK'd to `users` because a reset can be requested for an email before we
confirm a user row exists (and we must not leak user existence).

### 4. `auth_rate_limit` table
```sql
CREATE TABLE IF NOT EXISTS auth_rate_limit (
    bucket_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_key, window_start)
);
```
Postgres-backed sliding-window rate limiting, chosen over Upstash Redis to
avoid adding a new service for a personal-scale tool. `bucket_key` is
`<action>:<ip>` (and/or `<action>:<email>`). A helper upserts the row for the
current window and rejects when `hit_count` exceeds the per-action limit.

### V002 leftovers
`verification_token` (V002) becomes unused once the Nodemailer provider is
removed. Leave it in place: dropping an empty table is a migration with no
benefit. Note it as "unused as of V003" in a SQL comment.

## Backend code changes

None beyond V003. Explicitly confirmed unchanged: `alpha_agent/auth/*`,
`alpha_agent/api/byok.py`, `alpha_agent/api/routes/*`, the middleware re-mint.

## Frontend code changes

### `frontend/src/auth.ts`
- Add the **Credentials provider**: `authorize(credentials)` does Zod parse of
  `{ email, password }`, looks up the user by email in Neon, runs
  `bcryptjs.compare(password, user.password_hash)`, returns
  `{ id, email, name }` on success or `null` on failure (never throws a
  message that distinguishes "no such user" from "wrong password").
- Add the **Google provider** with `allowDangerousEmailAccountLinking: true`.
  Reads `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` (Auth.js v5 auto-detect
  convention) so the provider can be written as `Google` with no explicit
  args, or pass them explicitly.
- **Remove the Nodemailer provider** entirely. Magic-link login is gone.
  Resend stays only as the SMTP transport our own password-reset Server
  Action calls directly (not via a NextAuth provider).

### `frontend/src/auth.config.ts`
Unchanged. `providers: []` stays empty (edge-safe). The `jwt` and `session`
callbacks already stamp `user.id` into `token.sub` / `session.user.id`.

### New: `frontend/src/lib/auth/password.ts` (Node-only)
`hashPassword(plain)` and `verifyPassword(plain, hash)` wrapping `bcryptjs`
(cost factor 12). Node-only module; never imported by edge-reachable code.

### New: `frontend/src/lib/auth/rate-limit.ts` (Node-only)
`checkRateLimit(action, key)` against the `auth_rate_limit` table. Per-action
limits, e.g. login 5/min/IP, register 3/min/IP, reset-request 3/min/email.
Returns allowed/denied; the caller surfaces a 429-style error on denial.

### New: `/register` page + Server Action
`frontend/src/app/(auth)/register/page.tsx` (email + password + confirm
fields) and a Server Action that: rate-limits, Zod-validates (email format,
password 8 to 32 chars, confirm matches), checks the email is not already
registered, `hashPassword`es, `INSERT`s into `users` (the same table the
adapter uses, so a later Google sign-in links to one row), then calls
`signIn("credentials", ...)` to log the user straight in.

### New: password-reset flow
- `frontend/src/app/(auth)/forgot-password/page.tsx` + Server Action:
  rate-limits, generates a random 6-digit code, stores `bcryptjs`-hashed code
  + 15-min expiry in `password_reset_codes`, emails the plaintext code via
  Resend. ALWAYS returns the same "if that email exists, a code was sent"
  response (no user enumeration).
- `frontend/src/app/(auth)/reset-password/page.tsx` + Server Action: takes
  email + 6-digit code + new password, looks up the newest unused unexpired
  code row for that email, `bcryptjs.compare`s the code, on match updates
  `users.password_hash` and flips `used = true`. Clear errors for
  wrong/expired/used code.

### `frontend/src/app/(auth)/signin/page.tsx` rework
Replace the magic-link email form with: an email+password form (submits via
`signIn("credentials", ...)`), a "Sign in with Google" button (`signIn("google")`),
a link to `/register`, and a link to `/forgot-password`. Keep the existing
`tm-*` token styling and locale handling.

### `frontend/src/app/(auth)/signin/error/page.tsx`
Read the `?error=` query param NextAuth passes (`CredentialsSignin`,
`OAuthAccountNotLinked`, `Configuration`, etc.) and show the real reason
instead of the current generic "link invalid" message. This fixes the
misdiagnosis trap from M5 (a config error showed as "link expired").

### i18n
Add `register.*`, `forgot.*`, `reset.*` keys and password/Google related
`signin.*` keys, plus per-`?error=` messages for the error page. Both zh + en.

### Frontend deps
Add `bcryptjs` + `@types/bcryptjs`. Confirm `zod` is present (add if not).

## Data flow

**Password login:** `/signin` form -> `signIn("credentials", {email, password})`
-> NextAuth route handler -> `authorize()` (Zod + DB lookup + `bcryptjs.compare`)
-> session JWE issued -> middleware decrypts + re-mints HS256 -> FastAPI.

**Google login:** `/signin` "Sign in with Google" -> `signIn("google")` ->
Google OAuth -> NextAuth callback -> pg-adapter `getUserByAccount` /
`linkAccount` (auto-links to an existing same-email user row) -> session JWE
-> same downstream.

**Registration:** `/register` form -> Server Action -> rate-limit -> Zod ->
duplicate-email check -> `hashPassword` -> `INSERT users` -> `signIn("credentials")`.

**Password reset:** `/forgot-password` -> Server Action -> rate-limit ->
generate + hash + store code -> Resend email -> `/reset-password` -> Server
Action -> verify code -> update `password_hash` + mark code used.

## Error handling

- `authorize()` failure: generic "invalid email or password" to the client.
  No distinction between unknown email and wrong password (no user
  enumeration).
- Registration: duplicate email returns a clear "email already registered"
  (this one IS a deliberate disclosure: the user needs to know to sign in
  instead; the rate limit caps enumeration abuse).
- Rate-limit exceeded: a clear "too many attempts, try again shortly" message.
- Reset code wrong/expired/used: distinct, clear messages so the user knows
  whether to re-request.
- Google OAuth errors: surfaced on `/signin/error` with the real `?error=`
  reason.
- `forgot-password` always returns the same response regardless of whether
  the email exists.

## Security

- `bcryptjs` cost factor 12 for both passwords and reset codes.
- Reset codes: 6 random digits, stored hashed, 15-min TTL, single-use.
- No user enumeration on login or forgot-password.
- Rate limiting on register / login / reset-request (Postgres sliding window).
- Password hashing is Node-only; never reaches the edge runtime.
- `allowDangerousEmailAccountLinking` is acceptable here: a Google sign-in
  proves email ownership, and open registration without email verification
  means the alternative (orphaned duplicate accounts) is worse.
- The backend JWT contract is unchanged: no new trust surface server-side.

## Testing

- **Backend:** V003 migration test (the `ALTER` applied, `accounts` +
  `password_reset_codes` + `auth_rate_limit` tables exist, `accounts` columns
  match the adapter).
- **Frontend:** unit tests for `hashPassword`/`verifyPassword` round-trip,
  the registration Server Action (hash + insert + duplicate rejection), the
  `authorize()` callback (success + wrong-password + unknown-email all behave
  correctly), the reset-code generate/verify (match, expired, used, wrong),
  and `checkRateLimit` (allows under limit, denies over). `tsc --noEmit` +
  `next lint` + `next build` clean.
- **Acceptance:** a `make` target running the backend migration test + the
  frontend checks, plus a manual UAT: register -> password login -> sign out
  -> Google login with the same email links to one account -> forgot-password
  -> reset -> login with the new password.

## USER SETUP

1. **Google OAuth client** (DONE): client created in Google Cloud Console.
   Remaining: add `AUTH_GOOGLE_ID` + `AUTH_GOOGLE_SECRET` to the frontend
   Vercel project env (Production). Ensure the consent screen is Published (or
   the tester's Gmail is on the test-users list).
2. **V003 migration:** apply to Neon after the migration file is written
   (the orchestrator can run it the same way V002 was applied).

## Risks

| Risk | Mitigation |
|------|-----------|
| `accounts` table column casing mismatches `@auth/pg-adapter` (the G2 bug class) | The migration task MUST audit `node_modules/@auth/pg-adapter` source and match double-quoted camelCase exactly. A migration test asserts the column names. |
| `bcryptjs` accidentally pulled into the edge bundle | Hashing helpers live in a Node-only `lib/auth/password.ts`, never imported by `auth.config.ts` or `middleware.ts`. `next build` would surface an edge-runtime error. |
| `allowDangerousEmailAccountLinking` lets an attacker who controls a Google account hijack a password account with the same email | Accepted: the attacker would need to control the Google account for that exact email, which is itself proof of email ownership. Open + unverified registration makes the no-linking alternative strictly worse. |
| Auth.js v5 is in security-patch-only maintenance mode | Accepted for now. Long-term direction is Better Auth; revisit on a future phase if 2FA/org features are needed. |
| Resend `.edu.cn` delivery still fails for password-reset emails | Accepted and scoped: reset is a rare path, not every login. The user can use a mainstream email. DMARC was added to improve deliverability. |
| Postgres rate-limit table grows unbounded | A cleanup is cheap: a periodic `DELETE FROM auth_rate_limit WHERE window_start < now() - interval '1 day'`, or rely on the small row count at personal scale. The plan should include a note, not necessarily a cron. |

## Hand-off

After spec approval, invoke `superpowers:writing-plans` to produce the
implementation plan at
`docs/superpowers/plans/2026-05-14-phase4b-multi-method-auth.md`.
