# Alpha-Agent v4 · Phase 4 · Multi-User Auth + Server-side Encrypted BYOK · Design Spec

| Meta | Value |
|------|-------|
| Date | 2026-05-14 |
| Scope | NextAuth.js v5 auth + AES-256-GCM BYOK encryption + cross-service JWT handshake |
| Phase | 4 (post-Phase-1 completion 2026-05-14) |
| Status | Brainstormed + design approved 2026-05-14; spec ready for implementation plan |
| Dependencies | Phase 1 complete (M1-M4b shipped); existing Neon Postgres + Vercel deploy infra |
| Successor | Phase 3 (LLM-backed news sentiment), Phase 5 (OAuth + 2FA + teams) |

---

## 1. Background and Goals

### 1.1 Why now

Phase 1 shipped with the explicit assumption "single user, local-first" (Phase 1 spec §1.4). The product is now used by one person — me — through a BYOK localStorage key. Two pressures push toward multi-user:

- **Rich brief safety:** the M4b BYOK key lives in browser localStorage, vulnerable to any XSS that survives our CSP. Server-side encrypted storage with auth-gated access is the standard mitigation.
- **Friend-share readiness:** I want to share `alpha.bobbyzhong.com` with classmates without each person seeing my OpenAI bill. Per-user BYOK + per-user watchlist is the minimum.

Phase 4 is the architectural transition: from "anyone with the URL is the user" to "the URL is a multi-tenant equity research desk where login decides personal state".

### 1.2 User scenarios

| Persona | Behaviour | Phase 4 outcome |
|---------|-----------|----------------|
| Anonymous visitor | Lands on /picks via a shared link, reads ratings | Sees /picks + /stock + /alerts unchanged; sees "Sign in to use Rich brief" hint on stock cards |
| Returning owner (me) | Has Phase 1 localStorage BYOK key | First sign-in shows import banner; one-click migrates key to server-encrypted store; localStorage cleared after success |
| New friend / classmate | Got the URL from me, wants to try Rich brief | Clicks Generate → redirected to /signin → enters email → magic link → returns to /stock → adds own OpenAI key in /settings → Rich brief works |
| Privacy-conscious user | Wants to leave | /settings danger zone: Delete account + Export my data (cascade delete + JSON dump) |

### 1.3 Design goals

- **G1 — Phase 1 read paths stay public.** /picks, /stock, /alerts work without sign-in. Only mutations + Rich brief + admin endpoints require auth.
- **G2 — Zero data migration.** Global signal tables (daily_signals_fast/slow, alert_queue, cron_runs, error_log) stay schema-stable. Only new user-scoped tables are added.
- **G3 — BYOK keys are never logged, never in error messages, never in plaintext at rest.** Application-layer AES-256-GCM with a single project master key.
- **G4 — Stateless backend.** FastAPI verifies JWT signed by the frontend NextAuth.js layer. No backend session table; no backend ↔ frontend tight coupling beyond shared `NEXTAUTH_SECRET`.
- **G5 — Sub-5-minute add-account experience.** Email magic link, no password, no captcha, no MFA in Phase 4.
- **G6 — Reversible.** If Phase 4 auth code path breaks in production, we can disable the auth requirement on /api/brief/{t}/stream via a single env flag and fall back to anonymous-with-localStorage-BYOK.

### 1.4 Non-goals (deferred to Phase 5+)

- OAuth providers (Google / GitHub) — `Email magic link only` is sufficient for Phase 4.
- Two-factor authentication / WebAuthn.
- Team / organization accounts.
- Per-user backtest history, per-user model fine-tuning, per-user push channels.
- Real-time presence ("who else is viewing /stock/AAPL?").
- Server-rendered email previews — Resend HTML template is fine.

### 1.5 Constraints

- **Vercel Hobby tier** function timeouts (300s); no long-running auth callbacks.
- **Neon Free tier** Postgres; the 5 new user tables fit comfortably.
- **Resend free tier** 3000 emails/month; with self-imposed throttle (3 magic-link requests per email per day) this supports ~30 active accounts trivially.
- **NextAuth.js v5** (Auth.js, stable) — locked pre-brainstorm.
- **Backward compatible** anonymous browsing: an unauthenticated visitor must see the same /picks /stock /alerts as today.

---

## 2. High-Level Architecture

### 2.1 System diagram

```
┌────────────────────────────────────────────────────────────────┐
│                         Browser                                │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Next.js 14 App Router (alpha.bobbyzhong.com)             │  │
│  │ - NextAuth.js v5: /api/auth/* routes                     │  │
│  │ - getServerSession() in server components                │  │
│  │ - <Sidebar> shows Sign in / <email> Sign out             │  │
│  │ - <Auth> middleware redirects protected pages to /signin │  │
│  └──────────────────────────────────────────────────────────┘  │
│           │                                          │         │
│           │ httpOnly JWT cookie                      │         │
│           │ (NEXTAUTH_SECRET-signed)                 │         │
│           ▼                                          ▼         │
└─────────────────────────────────────────────────────────────────
            │                                          │
            │ /api/auth/* (NextAuth handlers)          │ /api/* (rewrite)
            │ Email magic link → Resend SMTP           │ Authorization: Bearer <jwt>
            ▼                                          ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│ NextAuth.js v5 server    │         │ FastAPI (alpha-agent)    │
│ - Email Provider         │         │ - require_user() dep     │
│ - JWT issuance           │         │   verifies same JWT      │
│ - VerificationToken DB   │         │ - reads sub claim        │
│   write                  │         │ - decrypts user_byok     │
│ - Adapter: Drizzle/Neon  │         │   AES-256-GCM            │
└──────────────────────────┘         └──────────────────────────┘
            │                                          │
            └──────────┬───────────────────────────────┘
                       ▼
              ┌──────────────────────┐
              │ Neon Postgres        │
              │ users / preferences  │
              │ user_watchlist       │
              │ user_byok            │
              │ verification_tokens  │
              │                      │
              │ + existing global:   │
              │  daily_signals_fast  │
              │  alert_queue         │
              │  cron_runs           │
              └──────────────────────┘
```

### 2.2 Key architectural decisions

- **A1 — NextAuth.js v5 + Email magic link only.** No OAuth provider setup, no password storage, no MFA. Resend handles SMTP.
- **A2 — JWT in httpOnly cookie (NextAuth default).** Stateless. No backend session table to manage. Sign-out clears the cookie; cannot force-revoke a single JWT until expiry (acceptable trade-off given small user base).
- **A3 — Backend verifies JWT with same `NEXTAUTH_SECRET`.** Frontend signs, backend verifies. FastAPI's `require_user()` dependency reads `Authorization: Bearer <jwt>` and validates locally — no callback to the frontend, no shared session table.
- **A4 — Application-layer AES-256-GCM for BYOK keys.** Master key `BYOK_MASTER_KEY` (32-byte base64, in Vercel env). Per-key random 12-byte nonce stored alongside ciphertext. DB never sees plaintext.
- **A5 — Global data stays global.** Existing `daily_signals_fast`, `daily_signals_slow`, `alert_queue`, `cron_runs`, `error_log` get NO `user_id` column. Only `user_byok`, `user_watchlist`, `user_preferences` are user-scoped.
- **A6 — Sidebar auth slot + protected-page redirect.** New TmSidebar bottom block; protected pages use Next middleware to redirect `→ /signin?callbackUrl=…` with bounce-back.
- **A7 — First-sign-in import banner.** Existing localStorage BYOK key is detected on first authenticated `/settings` load. Banner offers explicit Import (POST to backend) or Discard. After successful import, localStorage is cleared.

---

## 3. Component Design

### 3.1 Database schema (V003__phase4_users.sql)

```sql
-- Phase 4 user-scoped tables. Migration is purely additive; no existing
-- tables are altered. Cascade delete on user_id ensures account-delete
-- atomicity.

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    -- NextAuth.js v5 expects these column names verbatim for Email provider
    email_verified TIMESTAMPTZ,
    name TEXT,
    image TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active'  -- 'active', 'disabled'
);
CREATE INDEX idx_users_email ON users (email);

CREATE TABLE user_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    locale TEXT NOT NULL DEFAULT 'zh',          -- 'zh' | 'en'
    theme TEXT NOT NULL DEFAULT 'dark',         -- 'dark' | 'light'
    extras JSONB NOT NULL DEFAULT '{}'::jsonb,  -- forward-compat bucket
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_watchlist (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, ticker)
);
CREATE INDEX idx_user_watchlist_user ON user_watchlist (user_id);

CREATE TABLE user_byok (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                     -- 'openai' | 'anthropic' | 'kimi' | 'ollama'
    ciphertext BYTEA NOT NULL,                  -- AES-256-GCM output
    nonce BYTEA NOT NULL,                       -- 12-byte random nonce
    last4 TEXT NOT NULL,                        -- last 4 chars of plaintext for UI confirmation
    model TEXT,
    base_url TEXT,
    encrypted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    encrypted_with_key_id INT NOT NULL DEFAULT 1,  -- future master-key rotation tag
    PRIMARY KEY (user_id, provider)
);
CREATE INDEX idx_user_byok_user ON user_byok (user_id);

-- NextAuth.js v5 standard table for email magic-link tokens.
-- Token is a one-time hex string; identifier is the email.
CREATE TABLE verification_tokens (
    identifier TEXT NOT NULL,
    token TEXT NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);
```

### 3.2 Backend auth module: `alpha_agent/auth/`

New package, 3 files. Each has one clear responsibility.

#### 3.2.1 `crypto_box.py` — AES-256-GCM wrapper

- `encrypt(plaintext: str, master_key: bytes) -> tuple[bytes, bytes]` returns (ciphertext, nonce)
- `decrypt(ciphertext: bytes, nonce: bytes, master_key: bytes) -> str` raises `CryptoError` on tamper / wrong key
- Uses `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
- Per-call random nonce; nonce stored with ciphertext (12 bytes is fine for GCM with random nonces)
- Never logs the plaintext or master key

#### 3.2.2 `jwt_verify.py` — NextAuth.js JWT validation

- `verify_jwt(token: str, secret: str) -> dict` returns payload dict or raises `JwtError`
- Uses `jose.jwt.decode` with `algorithms=["HS256"]` (NextAuth.js v5 default)
- Validates `exp`, `iat`, `sub` (= user_id); rejects on any missing
- 5ms typical local verification, no DB call

#### 3.2.3 `dependencies.py` — FastAPI deps

- `require_user()` extracts `Authorization: Bearer` header → calls `verify_jwt()` → returns `int` user_id; raises 401 on failure
- `current_user_optional()` same but returns `int | None` for routes that work with or without auth (Phase 4 has no such routes; reserved for Phase 5)

### 3.3 Backend user routes: `alpha_agent/api/routes/user.py`

New file. 5 endpoints:

- `GET /api/user/me` → `{user_id, email, created_at, has_byok: bool}` (auth required)
- `GET /api/user/byok` → `{provider, last4, model?, base_url?} | 404 None`
- `POST /api/user/byok` body `{provider, api_key, model?, base_url?}` → encrypts, UPSERTs, returns `{provider, last4, encrypted_at}`. **NEVER returns the plaintext key in response.**
- `DELETE /api/user/byok` → 204
- `POST /api/user/account/delete` → cascade-deletes all user_* rows + users row → 204 (frontend then signs out)
- `GET /api/user/account/export` → JSON dump `{user, preferences, watchlist, byok_metadata_only}` (no plaintext key in export)

### 3.4 Backend updates: `alpha_agent/api/routes/brief.py`

- `POST /api/brief/{ticker}/stream` request body changes:
  - **Before (M4b):** `{provider, api_key, model?, base_url?}` — key in body
  - **After (Phase 4):** `{}` empty body OR `{model_override?}`; key is fetched server-side from `user_byok` for the authenticated user
- New dependency injection: `user_id: int = Depends(require_user)`
- Lookup flow: `SELECT * FROM user_byok WHERE user_id = $1` → decrypt → call `stream_brief(provider, decrypted_key, …)`
- On no key → 400 with `{detail: "No BYOK key set; visit /settings"}`
- On decrypt failure → SSE error event `{type: "error", message: "Stored key cannot be decrypted; please re-save in /settings"}`

### 3.5 Backend updates: `alpha_agent/api/routes/admin.py`

- Add `Depends(require_user)` to `POST /api/admin/refresh` — anyone signed in can trigger refresh (per design §1.3 G1; admin features are auth-gated but not role-restricted in Phase 4).

### 3.6 Frontend NextAuth config: `frontend/src/auth.ts`

NextAuth.js v5 config object. Approximately:

```typescript
import NextAuth from "next-auth";
import Email from "next-auth/providers/email";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PostgresAdapter(pool),
  providers: [
    Email({
      server: {
        host: "smtp.resend.com",
        port: 465,
        auth: { user: "resend", pass: process.env.RESEND_API_KEY! },
      },
      from: process.env.EMAIL_FROM!,
      // 24h expiry on magic links
      maxAge: 24 * 60 * 60,
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    jwt: async ({ token, user }) => {
      if (user) token.sub = String(user.id);
      return token;
    },
    session: async ({ session, token }) => {
      if (token.sub) (session.user as any).id = token.sub;
      return session;
    },
  },
  pages: {
    signIn: "/signin",
    verifyRequest: "/signin/check-email",
  },
});
```

### 3.7 Frontend pages

- `frontend/src/app/(auth)/signin/page.tsx` — magic-link email form (client component). On submit calls `signIn("email", {email, callbackUrl})`.
- `frontend/src/app/(auth)/signin/check-email/page.tsx` — "We sent you a link" confirmation static page.
- `frontend/src/app/(auth)/signin/error/page.tsx` — magic-link expired/invalid landing.

### 3.8 Frontend sidebar auth slot

`frontend/src/components/layout/Sidebar.tsx` gets a new bottom section reading `useSession()`:

- Anonymous: shows lucide `<LogIn>` icon + "Sign in" → `signIn()` opens /signin
- Authed: shows `<UserCircle>` icon + user.email (truncated) → menu with "Sign out" + "Account" link

### 3.9 Frontend `/settings` extensions

- BYOK form now posts to `POST /api/user/byok` (backend) instead of localStorage. Auth required to access page.
- New "Import existing key" banner shown if `(localStorage byok.v1 exists) AND (GET /api/user/byok returns 404)`.
- New "Danger zone" collapsible at bottom: "Export my data" (GET /api/user/account/export → download JSON) + "Delete my account" (confirmation modal → POST /api/user/account/delete).

### 3.10 Frontend `RichThesis` updates

- Reads `useSession()` instead of `loadByok()`.
- If `status === "unauthenticated"`: shows Link to `/signin?callbackUrl=/stock/[ticker]` instead of Generate button.
- If signed in: clicking Generate POSTs to `/api/brief/{ticker}/stream` with empty body + `Authorization: Bearer <jwt>` from session (server component) OR `credentials: "include"` (client component reads cookie automatically since same origin).
- Removes direct dependency on `lib/byok.ts` (which becomes legacy / unused).

---

## 4. Data Flow

### 4.1 Sign-in flow (email magic link)

```
1. Anonymous user clicks "Sign in" in sidebar
2. Browser → GET /signin
3. User enters email "user@example.com" + clicks Send
4. Browser → POST /api/auth/signin/email (NextAuth handler)
5. NextAuth: INSERT verification_tokens (identifier=email, token=hex, expires=now+24h)
6. NextAuth: Resend.send(to=email, subject="...", html="<a href=callback_url>...")
7. Browser → redirect to /signin/check-email
8. User clicks email link → GET /api/auth/callback/email?token=...&email=...
9. NextAuth: DELETE FROM verification_tokens WHERE identifier=email AND token=token
10. NextAuth: UPSERT users (email, email_verified=now)
11. NextAuth: issue JWT with sub=user_id, set httpOnly cookie
12. Browser → redirect to callbackUrl (or /picks)
```

### 4.2 Rich brief flow (auth-protected)

```
1. User on /stock/AAPL clicks "Generate Rich brief"
2. RichThesis client component → fetch POST /api/brief/AAPL/stream
   with credentials: "include" (sends JWT cookie via same-origin)
3. Next.js middleware on /api/* → reads cookie → extracts JWT → forwards in Authorization header
   (alternative: server component reads session, passes token explicitly)
4. FastAPI POST /api/brief/AAPL/stream
   - require_user dep: verify_jwt() → returns user_id=42
5. FastAPI: SELECT * FROM user_byok WHERE user_id = 42 AND provider = preferred_provider
6. FastAPI: crypto_box.decrypt(ciphertext, nonce, MASTER_KEY) → plaintext api_key
7. FastAPI: stream_brief(provider=row.provider, api_key=plaintext, ...) → SSE
8. FastAPI: UPDATE user_byok SET last_used_at = now() WHERE user_id=42 AND provider=row.provider
```

### 4.3 BYOK save flow

```
1. User on /settings enters key sk-abc123xyz, picks provider="openai"
2. Frontend: POST /api/user/byok body {provider:"openai", api_key:"sk-abc123xyz", model:"gpt-4o-mini"}
   with credentials: "include"
3. FastAPI: require_user → user_id=42
4. FastAPI: nonce = os.urandom(12)
5. FastAPI: ciphertext = AESGCM(MASTER_KEY).encrypt(nonce, "sk-abc123xyz".encode(), None)
6. FastAPI: last4 = "3xyz"
7. FastAPI: INSERT INTO user_byok (user_id, provider, ciphertext, nonce, last4, model, encrypted_at)
   VALUES (42, 'openai', ciphertext, nonce, '3xyz', 'gpt-4o-mini', now())
   ON CONFLICT (user_id, provider) DO UPDATE SET ciphertext=EXCLUDED.ciphertext, nonce=..., last4=..., encrypted_at=now()
8. FastAPI returns {provider:"openai", last4:"3xyz", encrypted_at:"2026-05-14T17:00:00Z"}
9. Frontend: displays "Key saved, ending in …3xyz"
10. Frontend: clears localStorage.byok.v1 (if previous Phase 1 key existed)
```

### 4.4 localStorage migration banner flow

```
1. Authenticated user opens /settings
2. Frontend client component: useEffect → check localStorage.getItem("byok.v1")
3. If localStorage HAS a key:
   - Frontend: GET /api/user/byok → if 404 (no server key yet):
     - Show banner: "Existing key detected in browser. [Import to server] [Discard]"
4. User clicks "Import":
   - Frontend: POST /api/user/byok with the localStorage contents
   - On 200: localStorage.removeItem("byok.v1"); hide banner; show "Imported. Key ending in …xxxx"
   - On error: show banner with retry
5. User clicks "Discard":
   - Frontend: localStorage.removeItem("byok.v1"); hide banner
```

### 4.5 Delete account flow

```
1. /settings danger zone → "Delete my account"
2. Confirmation modal: "Type DELETE to confirm" + button
3. Frontend: POST /api/user/account/delete
4. FastAPI: require_user → user_id=42
5. FastAPI: DELETE FROM users WHERE id=42 (cascade-deletes user_preferences, user_watchlist, user_byok rows)
6. FastAPI returns 204
7. Frontend: signOut() → clears JWT cookie → redirect /signin
```

### 4.6 Export my data flow

```
1. /settings → "Export my data"
2. Frontend: GET /api/user/account/export with credentials
3. FastAPI builds JSON:
   {
     "user": {email, created_at, last_login_at},
     "preferences": {locale, theme},
     "watchlist": [...tickers],
     "byok_metadata": [{provider, last4, model, encrypted_at, last_used_at}]
     // NOTE: encrypted ciphertext NOT included; user already has their plaintext key
   }
4. Frontend: triggers browser download as alpha-agent-export-<date>.json
```

---

## 5. Error Handling

### 5.1 Auth failures

| Symptom | HTTP | Frontend reaction |
|---------|------|-------------------|
| JWT missing / malformed / wrong signature | 401 | Redirect to /signin?callbackUrl=<current> |
| JWT expired | 401 | Same; NextAuth.js refresh attempts before this fires |
| Magic link token used | 400 | /signin/error page: "Link already used. Request a new one." |
| Magic link token expired | 410 | /signin/error page: "Link expired. Request a new one." |
| User status='disabled' in DB | 403 | "Account disabled. Contact support." |

### 5.2 BYOK decrypt failures

If `BYOK_MASTER_KEY` is rotated and old ciphertext can't decrypt:

- For `POST /api/brief/{ticker}/stream`: SSE stream yields `{type: "error", message: "Stored key cannot be decrypted. Please re-save in /settings."}` then `{type: "done"}`.
- For `GET /api/user/byok`: 200 with `{provider, last4, error: "decrypt_failed"}` so the settings page shows "Key needs re-entry" CTA.

The `encrypted_with_key_id` column (default 1) reserves space for future versioned master-key rotation; Phase 4 ships with a single key.

### 5.3 Email send failures

| Failure | Response | User experience |
|---------|----------|----------------|
| Resend 5xx | 503 from /api/auth/signin/email | "Email service temporarily unavailable. Try again in a minute." |
| Resend invalid API key (config error) | 500 + app.state.email_init_error | Logged for diagnosis; user sees generic "Sign-in temporarily unavailable" |
| Invalid email format | 400 (client-side validation primary) | Inline form error |

Per the **enumeration-attack mitigation**: when a user submits an email, ALWAYS return the same response shape (200 "check your inbox") regardless of whether the email is registered. Token is only created server-side if email is allowed.

### 5.4 Database failures

- All new auth/user routes write `app.state.<route>_init_error` on cold-start ImportError or asyncpg failure (Phase 1 pattern).
- Health endpoint `/api/_debug/load-errors` surfaces these.

### 5.5 Account-deletion partial-failure

- All cascades are FK-enforced (`ON DELETE CASCADE`). If the `DELETE FROM users` succeeds, all dependent rows go automatically.
- If the transaction rolls back mid-delete: 500 to client; user retries.
- No "partial deletion" state is possible by construction.

---

## 6. Testing

### 6.1 Backend unit tests (~12 new tests)

```
tests/auth/
├── test_crypto_box.py
│   - test_encrypt_decrypt_roundtrip
│   - test_decrypt_wrong_key_raises
│   - test_decrypt_tampered_ciphertext_raises
│   - test_nonce_uniqueness_across_100_encryptions
├── test_jwt_verify.py
│   - test_valid_token_returns_payload
│   - test_expired_token_raises
│   - test_wrong_signature_raises
│   - test_missing_sub_raises
└── test_dependencies.py
    - test_require_user_returns_user_id
    - test_require_user_401_on_missing_auth_header
    - test_require_user_401_on_invalid_jwt
```

### 6.2 Backend integration tests (~8 new tests)

```
tests/api/
├── test_user_routes.py
│   - test_get_user_me_with_auth
│   - test_get_user_me_without_auth_401
│   - test_post_user_byok_encrypts_and_stores
│   - test_post_user_byok_never_returns_plaintext
│   - test_get_user_byok_returns_last4_only
│   - test_delete_user_account_cascade
└── test_brief_stream_auth.py
    - test_brief_stream_requires_auth_returns_401_without_token
    - test_brief_stream_reads_byok_from_db_with_valid_token
```

Crypto tests use a fixed test master key. Auth tests use a fixture that constructs valid JWTs with the same `NEXTAUTH_SECRET` the tests set in env.

### 6.3 Frontend automated tests

Deferred to post-Phase-4 Playwright milestone (out of scope). Manual UAT only.

### 6.4 Manual UAT checklist (Phase 4 acceptance)

1. Sign-in: enter email → receive magic link → click → land on /picks signed in.
2. Repeat sign-in with same email → see "last_login_at" update in DB.
3. Sign out from sidebar → /picks still renders (public).
4. Click "Generate Rich brief" while signed out → redirected to /signin.
5. Sign in, navigate to /settings → BYOK form shows; paste OpenAI key + save → success toast + key shows as "…xxxx".
6. Refresh page → key shows as saved server-side (last4).
7. Click Generate Rich brief → streams correctly (no key in request body).
8. /settings → Import banner does NOT show (we just saved fresh).
9. With dev tools: localStorage `byok.v1` is null after save.
10. Test localStorage migration: manually set localStorage.byok.v1 to a fake key → reload /settings → see banner → click Import.
11. /settings → Export my data → download JSON; verify ciphertext NOT in export.
12. /settings → Delete account → confirm → cascaded delete confirmed in DB; user signed out; signing in again creates fresh user row.
13. With JWT cookie expired (manually delete cookie): visit /settings → redirect /signin?callbackUrl=/settings.

### 6.5 Integration smoke (m5-acceptance Makefile target)

```bash
make m5-acceptance:
  - pytest tests/auth/ tests/api/test_user_routes.py tests/api/test_brief_stream_auth.py -v
  - cd frontend && npm ci && npx tsc --noEmit && npx next lint && npx next build
  - curl smoke: POST /api/brief/AAPL/stream with no auth → expect 401
  - curl smoke: GET /api/user/me with no auth → expect 401
  - curl smoke: GET /api/user/me with crafted fake JWT (test secret) → expect user_id back
```

---

## 7. API Contract

### 7.1 NextAuth-handled routes (frontend Next.js handles all of these)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/auth/signin/email` | Body `{email, callbackUrl?}` → sends magic link |
| GET | `/api/auth/callback/email?token=...&email=...` | Verifies + sets cookie + redirects |
| POST | `/api/auth/signout` | Clears cookie |
| GET | `/api/auth/session` | Returns `{user: {id, email}} | null` |
| GET | `/api/auth/csrf` | Returns CSRF token (used by NextAuth client lib) |

### 7.2 New FastAPI backend routes

| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| GET | `/api/user/me` | Required | (none) | `{user_id, email, created_at, has_byok: bool}` |
| GET | `/api/user/byok` | Required | (none) | `{provider, last4, model?, base_url?, encrypted_at, last_used_at?}` or 404 |
| POST | `/api/user/byok` | Required | `{provider, api_key, model?, base_url?}` | `{provider, last4, encrypted_at}` |
| DELETE | `/api/user/byok` | Required | (none) | 204 |
| POST | `/api/user/account/delete` | Required | (none) | 204 |
| GET | `/api/user/account/export` | Required | (none) | JSON blob (see §4.6) |

### 7.3 Updated existing backend routes

| Method | Path | Phase 4 change |
|--------|------|----------------|
| POST | `/api/brief/{ticker}/stream` | Now requires auth; body changes to `{}` or `{model_override?}`; key fetched server-side from user_byok |
| POST | `/api/admin/refresh` | Now requires auth |

### 7.4 Unchanged routes

`/api/picks/lean`, `/api/stock/{ticker}`, `/api/stock/{ticker}/ohlcv`, `/api/alerts/recent`, `/api/cron/*` (CRON_SECRET-protected separately).

---

## 8. Migration / Rollout

### 8.1 Migration script: `alpha_agent/storage/migrations/V003__phase4_users.sql`

Contains the 5 CREATE TABLE statements from §3.1. Migration is purely additive — no `ALTER TABLE` on any existing table.

Apply locally via `psql $DATABASE_URL -f V003__phase4_users.sql`. Apply to production via the existing migration runner (Phase 1 already establishes V001 + V002 patterns).

### 8.2 New environment variables

**Frontend Vercel project:**
- `NEXTAUTH_URL` = `https://alpha.bobbyzhong.com`
- `NEXTAUTH_SECRET` = 32-byte b64 random (shared with backend)
- `RESEND_API_KEY` = from Resend dashboard
- `EMAIL_FROM` = `Alpha Agent <noreply@bobbyzhong.com>` (configured in Resend)
- `DATABASE_URL` = Neon (same string as backend)

**Backend Vercel project:**
- `NEXTAUTH_SECRET` = same as frontend
- `BYOK_MASTER_KEY` = 32-byte b64 random (NEW — different from NEXTAUTH_SECRET)

### 8.3 Rollout order (phased, each step is reversible)

1. **Add DB tables** — run V003 migration; zero downtime.
2. **Deploy backend** with new auth module + user routes; `require_user()` exists but no existing endpoints use it yet. Backend smoke: GET /api/user/me without auth returns 401.
3. **Deploy frontend** with NextAuth.js config + sign-in pages + sidebar slot. Existing pages work for anonymous + sign-in flow is testable in isolation.
4. **Test the full sign-in loop internally** with one real email.
5. **Enable auth on `/api/brief/{ticker}/stream`** — single commit toggling the dependency. Smoke test Rich brief works for signed-in user.
6. **Enable auth on `/api/admin/refresh`**.
7. **Ship the import banner** on /settings.
8. **Announce to users**: "Rich brief now requires sign-in; here's how to import your existing key."

### 8.4 Rollback plan

If steps 5-6 surface a JWT verification bug in production:

- Revert the two commits (one per endpoint) that added `Depends(require_user)`. Total ~5 lines.
- Backend deploys auto via `git push`. Frontend doesn't need redeploy because the change is backend-only.
- Users continue using the M4b BYOK localStorage path. Phase 4 auth lives dormant until fixed.

### 8.5 Data migration for me (the existing single-user)

I'm the only existing user. On first sign-in:

- Magic link → click → JWT cookie set
- Visit /settings → import banner appears (localStorage has my OpenAI key)
- Click Import → key encrypted + stored server-side
- localStorage cleared
- Done

---

## 9. Out of Scope (deferred to Phase 5+)

| Item | Notes |
|------|-------|
| OAuth providers (Google, GitHub, etc.) | Phase 5; needs OAuth app setup per provider |
| 2FA / WebAuthn / passkeys | Phase 5 |
| Team / organization accounts | Phase 5 |
| Per-user watchlist API (frontend integration) | Tables exist (§3.1) but `/watchlist` page comes in Phase 5 or as M5 follow-up |
| Per-user backtest history | Phase 5 (requires backtest UI which doesn't exist yet) |
| Real-time presence | Out of scope, possibly never |
| Server-rendered email templates (HTML beyond plain) | Default Resend HTML wrapper is fine |
| Email enumeration full mitigation (always-200 plus rate limit) | Mitigation is documented in §5.3; full implementation deferred to spec extension if needed |
| GDPR Subject Access Request automation | Manual export + delete cover the spirit; full SAR formal workflow deferred |
| Master-key rotation tooling | `encrypted_with_key_id` column reserves space; tooling is Phase 5 |
| Phase 3 LLM news sentiment | Separate spec after Phase 4 lands |

---

## 10. Risks

| Risk | Likelihood | Severity | Mitigation |
|------|------------|----------|------------|
| `NEXTAUTH_SECRET` drift between frontend and backend env | Medium | High (all auth breaks) | Cross-env smoke in m5-acceptance: backend tries to verify a frontend-issued JWT against its own secret in a contract test |
| Resend free-tier 3k emails/month exceeded | Low | Medium | Self-throttle 3 magic-link sends per email per day at NextAuth.js level; monitor Resend dashboard |
| `BYOK_MASTER_KEY` rotation breaks existing ciphertexts | Medium | Medium | `encrypted_with_key_id` per-row tag reserves multi-version support; Phase 4 ships v1 only; rotation runbook documents "re-encrypt" path |
| Magic links land in spam folder | Medium | Low | Resend has good deliverability; instruction text shows "check spam" hint on /signin/check-email page |
| Account deletion cascade fails partial (some FK violation) | Low | High | All FKs use `ON DELETE CASCADE`; integration test verifies clean delete |
| FastAPI cold-start JWT verify slow | Low | Low | `jose` library typical verify is <5ms; benchmarked locally |
| CSRF on magic-link callback | Low | Medium | NextAuth.js v5 has built-in CSRF; we use default config |
| Email enumeration attack | Medium | Low | Always-200 response from `/api/auth/signin/email` regardless of whether user exists |
| BYOK plaintext leaked in logs | Low | High | `BYOK_MASTER_KEY` never logged; ciphertext bytes only in DB; `repr(...)` on Pydantic BYOK request bodies uses `Field(repr=False)`; m5-acceptance includes a grep check for `api_key` in any log statement |
| User can't sign in because email magic-link expired in transit | Low | Low | 24-hour expiry; "Request new link" CTA on `/signin/error` |
| Existing localStorage BYOK ignored by user (never imported) | Medium | Low | Banner persists across all /settings visits until imported or discarded; no time pressure |
| JWT cookie stolen via XSS | Low | High | httpOnly cookie, strict SameSite=Lax, no JS access; CSP on the frontend already; depending on a future XSS surviving CSP would expose JWT but not the underlying BYOK key (which never leaves the server) |

---

## Appendix A: Glossary

- **BYOK** — Bring Your Own Key. The user provides their own LLM API key; the platform never bills LLM usage.
- **Magic link** — A one-time URL with embedded token, sent to the user's email. Clicking signs them in.
- **AES-256-GCM** — Authenticated encryption with associated data (AEAD). 256-bit key, 12-byte nonce; protects both confidentiality and integrity.
- **JWT** — JSON Web Token. Signed (HS256 here) self-contained claim object; no DB lookup to validate.
- **NextAuth.js v5 (Auth.js)** — Stable open-source auth library for Next.js App Router.
- **Cascade delete** — Database FK constraint where deleting a parent row automatically deletes referencing child rows.

## Appendix B: New project dependencies

**Backend (pyproject.toml):**
- `cryptography>=42` (for AES-256-GCM; already a transitive dep via httpx, but pin explicitly)
- `python-jose[cryptography]>=3.3` (for JWT verify)

**Frontend (package.json):**
- `next-auth@^5.0.0` (replaces nothing; new)
- `@auth/pg-adapter@^1.0` (Postgres adapter — raw SQL, no ORM)
- `pg@^8` (node-postgres driver, peer dep of @auth/pg-adapter)
- `nodemailer@^6` (NextAuth.js Email provider underlying SMTP client — Resend exposes SMTP credentials so no Resend SDK needed; pure SMTP keeps the dep surface minimal)
