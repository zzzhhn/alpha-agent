# Alpha-Agent v4 · M5 · Phase 4 Auth + Server-side Encrypted BYOK · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship multi-user auth (NextAuth.js v5 email magic link) + move BYOK keys from browser localStorage to AES-256-GCM-encrypted server storage, with a stateless JWT handshake between the Next.js frontend and the FastAPI backend.

**Architecture:** NextAuth.js v5 in the frontend issues JWTs (httpOnly cookie). The backend FastAPI verifies the same JWT with a shared `NEXTAUTH_SECRET` via a `require_user` dependency. BYOK keys are encrypted application-side with `cryptography`'s AESGCM under a project `BYOK_MASTER_KEY`, decrypted only just before the LLM upstream call. Global SP500 signal tables stay untouched; 5 new user-scoped tables carry per-user state.

**Tech Stack:** Backend: Python 3.12, FastAPI, asyncpg, `cryptography>=42` (AES-256-GCM), `python-jose[cryptography]>=3.3` (JWT verify). Frontend: Next.js 14 App Router, `next-auth@^5`, `@auth/pg-adapter`, `pg`, `nodemailer` (Resend SMTP), Tailwind `tm-*` tokens, lucide-react icons.

**Spec reference:** `docs/superpowers/specs/2026-05-14-phase4-auth-and-server-byok.md` — read it first; it is the authoritative design. This plan implements it task-by-task.

**Migration numbering note:** The spec text says `V003`. The repo only has `V001__initial_schema.sql` today (no V002). The correct next migration is therefore **`V002__phase4_users.sql`**. This plan uses V002.

---

## Scope

| In M5 | Out of scope (Phase 5+) |
|-------|-------------------------|
| `V002__phase4_users.sql` — 5 user-scoped tables | OAuth providers (Google/GitHub) |
| `alpha_agent/auth/` — crypto_box + jwt_verify + dependencies | 2FA / WebAuthn / passkeys |
| `GET /api/user/me`, `GET/POST/DELETE /api/user/byok` | Team / org accounts |
| `POST /api/user/account/delete`, `GET /api/user/account/export` | Per-user backtest history |
| `POST /api/brief/{ticker}/stream` now auth-gated + server-side key | `/watchlist` page (tables exist, page deferred) |
| `POST /api/admin/refresh` now auth-gated | Master-key rotation tooling |
| NextAuth.js v5 config + `/signin` pages + Sidebar auth slot | Phase 3 (LLM news sentiment — separate spec) |
| `/settings` server-side BYOK + localStorage import banner + danger zone | Real Playwright E2E |
| `RichThesis` switches `loadByok()` → `useSession()` | |
| `make m5-acceptance` (pytest + frontend build + curl smokes) | |

---

## File Structure

**New files — backend:**

```
alpha_agent/storage/migrations/
└── V002__phase4_users.sql              # A1 — 5 tables, additive only

alpha_agent/auth/                       # A2-A4 — new package
├── __init__.py
├── crypto_box.py                       # A2 — AES-256-GCM encrypt/decrypt
├── jwt_verify.py                       # A3 — NextAuth JWT verification
└── dependencies.py                     # A4 — require_user FastAPI dep

alpha_agent/api/routes/
└── user.py                             # B1 — 6 user endpoints

tests/auth/                             # A2-A4 — new test dir
├── __init__.py
├── test_crypto_box.py
├── test_jwt_verify.py
└── test_dependencies.py

tests/api/
├── test_user_routes.py                 # B1
└── test_brief_stream_auth.py           # C1
```

**New files — frontend:**

```
frontend/src/
├── auth.ts                             # D1 — NextAuth.js v5 config
├── middleware.ts                       # D2 — protected-route redirect
├── app/
│   ├── api/auth/[...nextauth]/route.ts # D2 — NextAuth route handler
│   └── (auth)/
│       └── signin/
│           ├── page.tsx                # E1 — magic-link email form
│           ├── check-email/page.tsx    # E1 — "link sent" confirmation
│           └── error/page.tsx          # E1 — expired/invalid link
├── components/
│   └── layout/
│       └── SidebarAuthSlot.tsx         # E2 — sign-in / user block
└── lib/
    └── api/user.ts                     # E3 — typed client for /api/user/*
```

**Modified files:**

```
alpha_agent/api/routes/brief.py         # C1 — /stream requires auth, server-side key
alpha_agent/api/routes/admin.py         # C1 — /refresh requires auth
api/index.py                            # B1 — register user_router
pyproject.toml                          # A2/A3 — add cryptography + python-jose

frontend/package.json                   # D1 — next-auth + @auth/pg-adapter + pg + nodemailer
frontend/src/components/layout/Sidebar.tsx   # E2 — mount SidebarAuthSlot
frontend/src/app/(dashboard)/settings/page.tsx  # E3 — server-side BYOK + banner + danger zone
frontend/src/components/stock/RichThesis.tsx    # E4 — useSession instead of loadByok
frontend/src/lib/i18n.ts                # E1/E2/E3 — auth.* + signin.* keys
Makefile                                # F1 — m5-acceptance target
```

Backend net: ~620 LOC (migration 60 + crypto_box 70 + jwt_verify 60 + dependencies 50 + user.py 180 + brief/admin edits 60 + tests 140).
Frontend net: ~560 LOC (auth.ts 60 + middleware 40 + route handler 10 + signin pages 130 + SidebarAuthSlot 70 + user.ts client 50 + settings edits 120 + RichThesis edits 50 + i18n 30).

---

## Phase Order & Dependency Tiers

```
Tier 1 (sequential foundation):  A1 -> A2 -> A3 -> A4
Tier 2 (backend consumers):      B1 (needs A4) -> C1 (needs A4 + B1 byok helper)
Tier 3 (frontend auth core):     D1 (needs A1 tables) -> D2 (needs D1)
Tier 4 (frontend UI):            E1 -> E2 -> E3 -> E4 (all need D1/D2)
Tier 5 (acceptance):             F1
```

Execution is **strictly sequential**: A1 → A2 → A3 → A4 → B1 → C1 → D1 → D2 → E1 → E2 → E3 → E4 → F1. 13 tasks. The tier annotations are informational only — `superpowers:subagent-driven-development` never parallel-dispatches implementers.

---

## USER SETUP — ops actions outside the plan's automation

The implementer subagents **must not** attempt to set these — they live in Vercel project settings and would fail from a subagent shell. Tests use fixture values. The user does these once, before F1 acceptance:

**Frontend Vercel project env:**
- `NEXTAUTH_URL` = `https://alpha.bobbyzhong.com`
- `NEXTAUTH_SECRET` = `openssl rand -base64 32` output (shared with backend)
- `RESEND_API_KEY` = from Resend dashboard
- `EMAIL_FROM` = `Alpha Agent <noreply@bobbyzhong.com>`
- `DATABASE_URL` = Neon connection string (same as backend)

**Backend Vercel project (alpha-agent) env:**
- `NEXTAUTH_SECRET` = SAME value as frontend
- `BYOK_MASTER_KEY` = `python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"` output (DIFFERENT from NEXTAUTH_SECRET)

**Resend:** verify the `bobbyzhong.com` sending domain in the Resend dashboard.

The migration `V002__phase4_users.sql` is applied via the existing runner: `python -c "import asyncio; from alpha_agent.storage.migrations.runner import apply_migrations; asyncio.run(apply_migrations('<DATABASE_URL>'))"`.

---

## Phase A — Foundation

### Task A1: V002 migration — 5 user-scoped tables

**Why:** Phase 4 needs `users` + 4 satellite tables. The migration is purely additive — no `ALTER TABLE` on any existing table — so it is zero-downtime and instantly rollback-safe (drop the 5 tables).

**Files:**
- Create: `alpha_agent/storage/migrations/V002__phase4_users.sql`
- Test: `tests/auth/__init__.py` (empty) + `tests/auth/test_migration_v002.py`

- [ ] **Step 1: Write the failing test**

Create `tests/auth/__init__.py` as an empty file, then create `tests/auth/test_migration_v002.py`:

```python
# tests/auth/test_migration_v002.py
"""V002 migration applies cleanly and creates the 5 Phase 4 tables."""
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).parents[2]
    / "alpha_agent" / "storage" / "migrations" / "V002__phase4_users.sql"
)


def test_v002_file_exists():
    assert _MIGRATION.exists(), "V002__phase4_users.sql missing"


def test_v002_declares_five_tables():
    sql = _MIGRATION.read_text(encoding="utf-8")
    for table in (
        "users",
        "user_preferences",
        "user_watchlist",
        "user_byok",
        "verification_tokens",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"missing table {table}"


def test_v002_user_byok_has_crypto_columns():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # The encryption columns the crypto_box round-trip depends on.
    for col in ("ciphertext BYTEA", "nonce BYTEA", "last4 TEXT", "encrypted_with_key_id"):
        assert col in sql, f"user_byok missing column fragment: {col}"


def test_v002_cascade_deletes_on_user_drop():
    sql = _MIGRATION.read_text(encoding="utf-8")
    # Account deletion atomicity depends on ON DELETE CASCADE everywhere.
    cascade_count = sql.count("ON DELETE CASCADE")
    assert cascade_count >= 3, (
        f"expected >=3 ON DELETE CASCADE (preferences/watchlist/byok), got {cascade_count}"
    )


def test_v002_is_additive_only():
    sql = _MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE" not in sql.upper(), "V002 must be additive; no ALTER TABLE"
    assert "DROP TABLE" not in sql.upper(), "V002 must not drop anything"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/auth/test_migration_v002.py -v
```

Expected: 5 FAIL — the migration file does not exist.

- [ ] **Step 3: Write the migration**

Create `alpha_agent/storage/migrations/V002__phase4_users.sql`:

```sql
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/auth/test_migration_v002.py -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add alpha_agent/storage/migrations/V002__phase4_users.sql tests/auth/__init__.py tests/auth/test_migration_v002.py
git commit -m "feat(migration): V002 phase 4 user tables (M5 A1)

5 additive user-scoped tables: users / user_preferences / user_watchlist
/ user_byok / verification_tokens. No ALTER on existing global tables -
zero downtime, drop-the-5-tables rollback. ON DELETE CASCADE on every
user_id FK gives account-delete atomicity. Column names on users +
verification_tokens match NextAuth.js v5 Email provider expectations."
```

---

### Task A2: crypto_box module — AES-256-GCM

**Why:** BYOK keys must never sit in plaintext at rest. `crypto_box` is the single place that touches `BYOK_MASTER_KEY`; every encrypt/decrypt funnels through it so the key-handling discipline lives in one auditable file.

**Files:**
- Create: `alpha_agent/auth/__init__.py` (empty)
- Create: `alpha_agent/auth/crypto_box.py`
- Modify: `pyproject.toml` (add `cryptography>=42`)
- Test: `tests/auth/test_crypto_box.py`

- [ ] **Step 1: Write the failing test**

Create `tests/auth/test_crypto_box.py`:

```python
# tests/auth/test_crypto_box.py
import base64
import os

import pytest

from alpha_agent.auth.crypto_box import CryptoError, decrypt, encrypt

# Fixed 32-byte test master key (base64). NEVER a real key.
_TEST_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef")


def test_encrypt_decrypt_roundtrip():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    assert isinstance(ciphertext, bytes)
    assert isinstance(nonce, bytes)
    assert len(nonce) == 12
    assert ciphertext != b"sk-test-abc123"
    plaintext = decrypt(ciphertext, nonce, _TEST_KEY)
    assert plaintext == "sk-test-abc123"


def test_decrypt_wrong_key_raises():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    wrong = base64.b64encode(b"WRONGWRONGWRONGWRONGWRONGWRONG!!")
    with pytest.raises(CryptoError):
        decrypt(ciphertext, nonce, wrong)


def test_decrypt_tampered_ciphertext_raises():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(CryptoError):
        decrypt(tampered, nonce, _TEST_KEY)


def test_nonce_uniqueness_across_encryptions():
    nonces = {encrypt("sk-same", _TEST_KEY)[1] for _ in range(100)}
    assert len(nonces) == 100, "nonces must be unique per encryption"


def test_encrypt_rejects_malformed_master_key():
    with pytest.raises(CryptoError):
        encrypt("sk-test", b"not-base64-and-too-short")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/auth/test_crypto_box.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'alpha_agent.auth.crypto_box'`.

- [ ] **Step 3: Add the dependency + write the module**

Add `cryptography>=42` to `pyproject.toml` `[project.dependencies]` — insert after the `"lxml>=4.9",` line:

```toml
    "lxml>=4.9",
    # M5 Phase 4: AES-256-GCM for server-side BYOK key encryption.
    "cryptography>=42",
```

Then `pip install -e .` (or `pip install cryptography>=42`) so the import resolves.

Create `alpha_agent/auth/__init__.py` as an empty file.

Create `alpha_agent/auth/crypto_box.py`:

```python
"""AES-256-GCM wrapper for server-side BYOK key encryption.

Single audit point for BYOK_MASTER_KEY. Every encrypt/decrypt of a user
API key funnels through here. The master key and plaintext are NEVER
logged, NEVER put in exception messages.

Storage contract: caller persists (ciphertext, nonce) together; nonce is
12 random bytes per encryption (safe for GCM with random nonces at our
volume). Master key is a base64-encoded 32-byte value from env.
"""
from __future__ import annotations

import base64

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(Exception):
    """Raised on any encrypt/decrypt failure. Message never contains the
    plaintext, the master key, or the ciphertext bytes."""


def _load_key(master_key_b64: bytes) -> bytes:
    """Decode + validate the base64 master key into 32 raw bytes."""
    try:
        raw = base64.b64decode(master_key_b64, validate=True)
    except (ValueError, TypeError) as e:
        raise CryptoError(f"master key is not valid base64: {type(e).__name__}") from e
    if len(raw) != 32:
        raise CryptoError(
            f"master key must decode to 32 bytes (got {len(raw)})"
        )
    return raw


def encrypt(plaintext: str, master_key_b64: bytes) -> tuple[bytes, bytes]:
    """Encrypt `plaintext` under the master key. Returns (ciphertext, nonce).

    Raises CryptoError on a malformed master key. The 12-byte nonce is
    fresh per call and must be stored alongside the ciphertext.
    """
    import os

    key = _load_key(master_key_b64)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes, master_key_b64: bytes) -> str:
    """Decrypt `ciphertext` with `nonce` under the master key.

    Raises CryptoError if the key is wrong, the ciphertext was tampered
    with, or the master key is malformed.
    """
    key = _load_key(master_key_b64)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as e:
        raise CryptoError("decryption failed (wrong key or tampered data)") from e
    return plaintext.decode("utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/auth/test_crypto_box.py -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/auth/__init__.py alpha_agent/auth/crypto_box.py tests/auth/test_crypto_box.py pyproject.toml
git commit -m "feat(auth): crypto_box AES-256-GCM module for BYOK encryption (M5 A2)

Single audit point for BYOK_MASTER_KEY. encrypt() returns (ciphertext,
nonce) with a fresh 12-byte nonce per call; decrypt() raises CryptoError
on wrong key or tampered data via the AESGCM InvalidTag. Master key and
plaintext never appear in logs or exception messages. cryptography>=42
added to core deps (Vercel runtime installs only [project.dependencies])."
```

---

### Task A3: jwt_verify module — NextAuth.js JWT verification

**Why:** The backend must trust JWTs the frontend NextAuth.js layer issues, without a shared session table or a callback. `jwt_verify` validates the HS256 signature with the shared `NEXTAUTH_SECRET` and extracts the `sub` claim (= user_id).

**Files:**
- Create: `alpha_agent/auth/jwt_verify.py`
- Modify: `pyproject.toml` (add `python-jose[cryptography]>=3.3`)
- Test: `tests/auth/test_jwt_verify.py`

- [ ] **Step 1: Write the failing test**

Create `tests/auth/test_jwt_verify.py`:

```python
# tests/auth/test_jwt_verify.py
import time

import pytest
from jose import jwt

from alpha_agent.auth.jwt_verify import JwtError, verify_jwt

_SECRET = "test-secret-not-real-0123456789"


def _make_token(**overrides) -> str:
    now = int(time.time())
    payload = {
        "sub": "42",
        "iat": now,
        "exp": now + 3600,
        "email": "user@example.com",
    }
    payload.update(overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def test_valid_token_returns_payload():
    token = _make_token()
    payload = verify_jwt(token, _SECRET)
    assert payload["sub"] == "42"
    assert payload["email"] == "user@example.com"


def test_expired_token_raises():
    token = _make_token(exp=int(time.time()) - 10)
    with pytest.raises(JwtError, match="expired"):
        verify_jwt(token, _SECRET)


def test_wrong_signature_raises():
    token = _make_token()
    with pytest.raises(JwtError):
        verify_jwt(token, "a-completely-different-secret-value")


def test_missing_sub_raises():
    token = _make_token(sub=None)
    # jose drops None claims; building without sub then verifying must fail.
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600}
    bare = jwt.encode(payload, _SECRET, algorithm="HS256")
    with pytest.raises(JwtError, match="sub"):
        verify_jwt(bare, _SECRET)


def test_malformed_token_raises():
    with pytest.raises(JwtError):
        verify_jwt("not.a.jwt", _SECRET)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/auth/test_jwt_verify.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'alpha_agent.auth.jwt_verify'` (and `jose` may also be missing).

- [ ] **Step 3: Add the dependency + write the module**

Add to `pyproject.toml` `[project.dependencies]` after the `cryptography>=42` line from A2:

```toml
    "cryptography>=42",
    # M5 Phase 4: verify NextAuth.js HS256 JWTs issued by the frontend.
    "python-jose[cryptography]>=3.3",
```

Then `pip install -e .` (or `pip install "python-jose[cryptography]>=3.3"`).

Create `alpha_agent/auth/jwt_verify.py`:

```python
"""Verify NextAuth.js v5 JWTs issued by the frontend.

NextAuth.js v5 (session strategy "jwt") signs the session JWT with
HS256 using AUTH_SECRET / NEXTAUTH_SECRET. The backend shares that
secret via env and verifies locally - no DB lookup, no callback to the
frontend.

The `sub` claim carries the user_id (set in the frontend's jwt callback,
spec section 3.6).
"""
from __future__ import annotations

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError


class JwtError(Exception):
    """Raised when a JWT is missing, malformed, expired, or wrongly signed."""


def verify_jwt(token: str, secret: str) -> dict:
    """Verify `token` against `secret` (HS256). Returns the claims dict.

    Raises JwtError on: expired token, bad signature, malformed token, or
    a missing `sub` claim. The raised message never contains the token.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except ExpiredSignatureError as e:
        raise JwtError("token expired") from e
    except JWTError as e:
        raise JwtError(f"invalid token: {type(e).__name__}") from e
    if not payload.get("sub"):
        raise JwtError("token missing 'sub' (user_id) claim")
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/auth/test_jwt_verify.py -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/auth/jwt_verify.py tests/auth/test_jwt_verify.py pyproject.toml
git commit -m "feat(auth): jwt_verify module for NextAuth.js HS256 tokens (M5 A3)

Stateless verification of the frontend-issued session JWT against the
shared NEXTAUTH_SECRET. Raises JwtError on expired / bad-signature /
malformed / missing-sub. Token bytes never appear in the error message.
python-jose[cryptography]>=3.3 added to core deps."
```

---

### Task A4: require_user FastAPI dependency

**Why:** Routes that need auth declare `user_id: int = Depends(require_user)`. The dependency reads `Authorization: Bearer`, verifies via A3, returns the user_id int, raises 401 on any failure.

**Files:**
- Create: `alpha_agent/auth/dependencies.py`
- Test: `tests/auth/test_dependencies.py`

- [ ] **Step 1: Write the failing test**

Create `tests/auth/test_dependencies.py`:

```python
# tests/auth/test_dependencies.py
import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from alpha_agent.auth.dependencies import require_user

_SECRET = "test-secret-not-real-0123456789"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user_id: int = Depends(require_user)) -> dict:
        return {"user_id": user_id}

    return TestClient(app)


def _token(sub="42", **overrides) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iat": now, "exp": now + 3600}
    payload.update(overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def test_require_user_returns_user_id(client):
    r = client.get("/whoami", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": 42}


def test_require_user_401_on_missing_header(client):
    r = client.get("/whoami")
    assert r.status_code == 401


def test_require_user_401_on_non_bearer(client):
    r = client.get("/whoami", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_require_user_401_on_invalid_jwt(client):
    r = client.get("/whoami", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_require_user_401_on_expired_jwt(client):
    expired = _token(exp=int(time.time()) - 10)
    r = client.get("/whoami", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_require_user_401_on_non_numeric_sub(client):
    bad = _token(sub="not-a-number")
    r = client.get("/whoami", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/auth/test_dependencies.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'alpha_agent.auth.dependencies'`.

- [ ] **Step 3: Write the module**

Create `alpha_agent/auth/dependencies.py`:

```python
"""FastAPI auth dependencies for Phase 4 protected routes.

`require_user` is the single gate: it pulls the bearer token, verifies
it with the shared NEXTAUTH_SECRET, and returns the integer user_id.
Any failure -> HTTP 401 with a structured detail (never a bare except,
never the token in the message).
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException

from alpha_agent.auth.jwt_verify import JwtError, verify_jwt


async def require_user(authorization: str | None = Header(default=None)) -> int:
    """Resolve the authenticated user_id from the Authorization header.

    Raises HTTPException(401) if the header is missing, not a Bearer
    token, the JWT fails verification, or the `sub` claim is not an int.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")

    token = authorization[len("Bearer ") :]
    secret = os.environ.get("NEXTAUTH_SECRET")
    if not secret:
        # Config error, not a client error - surface clearly (CLAUDE.md
        # silent-exception rule) but still 401 so the client redirects.
        raise HTTPException(
            status_code=401,
            detail="server auth not configured (NEXTAUTH_SECRET missing)",
        )

    try:
        payload = verify_jwt(token, secret)
    except JwtError as e:
        raise HTTPException(status_code=401, detail=f"auth failed: {e}") from e

    sub = payload["sub"]
    try:
        return int(sub)
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=401, detail="token 'sub' claim is not a valid user_id"
        ) from e
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/auth/test_dependencies.py -v
```

Expected: 6/6 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/auth/dependencies.py tests/auth/test_dependencies.py
git commit -m "feat(auth): require_user FastAPI dependency (M5 A4)

Single 401 gate for protected routes. Pulls the Bearer token, verifies
with the shared NEXTAUTH_SECRET, returns int user_id. Missing header /
non-Bearer / bad JWT / expired / non-numeric sub all -> structured 401.
Missing NEXTAUTH_SECRET surfaces as a clear 401 detail rather than a
silent crash."
```

---

## Phase B — Backend user routes

### Task B1: user.py — 6 user endpoints + register

**Why:** All per-user state (profile, BYOK key, account lifecycle) is exposed through one router. The BYOK read endpoint returns only `last4` — never the plaintext key.

**Files:**
- Create: `alpha_agent/api/routes/user.py`
- Modify: `api/index.py` (register router)
- Test: `tests/api/test_user_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_user_routes.py`:

```python
# tests/api/test_user_routes.py
import base64
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"
_MASTER = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _MASTER)
    from api.index import app
    return TestClient(app)


def _auth(sub="42"):
    now = int(time.time())
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600, "email": "u@example.com"},
        _SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


def test_get_me_requires_auth(client):
    assert client.get("/api/user/me").status_code == 401


def test_get_me_with_auth(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "id": 42, "email": "u@example.com",
        "created_at": __import__("datetime").datetime(2026, 5, 14),
    })
    pool.fetchval = AsyncMock(return_value=False)  # has_byok
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/me", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 42
    assert body["email"] == "u@example.com"
    assert body["has_byok"] is False


def test_post_byok_encrypts_and_stores(client, monkeypatch):
    pool = MagicMock()
    pool.execute = AsyncMock()
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post(
        "/api/user/byok",
        headers=_auth(),
        json={"provider": "openai", "api_key": "sk-secret-tail1234", "model": "gpt-4o-mini"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai"
    assert body["last4"] == "1234"
    # The plaintext key must NEVER be echoed back.
    assert "api_key" not in body
    assert "sk-secret" not in r.text
    # The INSERT call must carry ciphertext bytes, not the plaintext.
    insert_sql = pool.execute.call_args.args[0]
    assert "INSERT INTO user_byok" in insert_sql
    assert b"sk-secret-tail1234" not in pool.execute.call_args.args


def test_get_byok_returns_last4_only(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "provider": "openai", "last4": "1234", "model": "gpt-4o-mini",
        "base_url": None, "encrypted_at": __import__("datetime").datetime(2026, 5, 14),
        "last_used_at": None,
    })
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/byok", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["last4"] == "1234"
    assert "ciphertext" not in body
    assert "api_key" not in body


def test_get_byok_404_when_none(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.get("/api/user/byok", headers=_auth())
    assert r.status_code == 404


def test_delete_account_cascades(client, monkeypatch):
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="DELETE 1")
    monkeypatch.setattr("alpha_agent.api.routes.user.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post("/api/user/account/delete", headers=_auth())
    assert r.status_code == 204
    # A single DELETE FROM users relies on ON DELETE CASCADE for the rest.
    assert "DELETE FROM users" in pool.execute.call_args.args[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_user_routes.py -v
```

Expected: FAIL — `/api/user/*` routes return 404 (router not registered).

- [ ] **Step 3: Write user.py**

Create `alpha_agent/api/routes/user.py`:

```python
"""Phase 4 user routes: profile, BYOK key, account lifecycle.

All routes require auth via require_user. The BYOK key is stored
AES-256-GCM encrypted (crypto_box) and is NEVER returned in plaintext -
GET /byok exposes only last4. Account delete relies on the V002
ON DELETE CASCADE FKs for atomicity.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.crypto_box import encrypt
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/api/user", tags=["user"])


class MeResponse(BaseModel):
    user_id: int
    email: str
    created_at: str
    has_byok: bool


class ByokSaveRequest(BaseModel):
    provider: str = Field(pattern="^(openai|anthropic|kimi|ollama)$")
    api_key: str = Field(min_length=1, repr=False)
    model: str | None = None
    base_url: str | None = None


class ByokSaveResponse(BaseModel):
    provider: str
    last4: str
    encrypted_at: str


class ByokGetResponse(BaseModel):
    provider: str
    last4: str
    model: str | None
    base_url: str | None
    encrypted_at: str
    last_used_at: str | None


@router.get("/me", response_model=MeResponse)
async def get_me(user_id: int = Depends(require_user)) -> MeResponse:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT id, email, created_at FROM users WHERE id = $1", user_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    has_byok = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM user_byok WHERE user_id = $1)", user_id
    )
    return MeResponse(
        user_id=row["id"],
        email=row["email"],
        created_at=row["created_at"].isoformat(),
        has_byok=bool(has_byok),
    )


@router.post("/byok", response_model=ByokSaveResponse)
async def save_byok(
    body: ByokSaveRequest, user_id: int = Depends(require_user)
) -> ByokSaveResponse:
    master = os.environ.get("BYOK_MASTER_KEY")
    if not master:
        raise HTTPException(
            status_code=500, detail="BYOK_MASTER_KEY not configured"
        )
    ciphertext, nonce = encrypt(body.api_key, master.encode("utf-8"))
    last4 = body.api_key[-4:]
    pool = await get_db_pool()
    await pool.execute(
        """
        INSERT INTO user_byok
            (user_id, provider, ciphertext, nonce, last4, model, base_url, encrypted_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        ON CONFLICT (user_id, provider) DO UPDATE SET
            ciphertext = EXCLUDED.ciphertext,
            nonce = EXCLUDED.nonce,
            last4 = EXCLUDED.last4,
            model = EXCLUDED.model,
            base_url = EXCLUDED.base_url,
            encrypted_at = now()
        """,
        user_id, body.provider, ciphertext, nonce, last4, body.model, body.base_url,
    )
    from datetime import UTC, datetime

    return ByokSaveResponse(
        provider=body.provider, last4=last4, encrypted_at=datetime.now(UTC).isoformat()
    )


@router.get("/byok", response_model=ByokGetResponse)
async def get_byok(user_id: int = Depends(require_user)) -> ByokGetResponse:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT provider, last4, model, base_url, encrypted_at, last_used_at "
        "FROM user_byok WHERE user_id = $1 LIMIT 1",
        user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no BYOK key set")
    return ByokGetResponse(
        provider=row["provider"],
        last4=row["last4"],
        model=row["model"],
        base_url=row["base_url"],
        encrypted_at=row["encrypted_at"].isoformat(),
        last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
    )


@router.delete("/byok", status_code=204)
async def delete_byok(user_id: int = Depends(require_user)) -> Response:
    pool = await get_db_pool()
    await pool.execute("DELETE FROM user_byok WHERE user_id = $1", user_id)
    return Response(status_code=204)


@router.post("/account/delete", status_code=204)
async def delete_account(user_id: int = Depends(require_user)) -> Response:
    pool = await get_db_pool()
    # ON DELETE CASCADE on user_preferences / user_watchlist / user_byok
    # FKs handles the dependent rows atomically.
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)
    return Response(status_code=204)


@router.get("/account/export")
async def export_account(user_id: int = Depends(require_user)) -> dict:
    pool = await get_db_pool()
    user = await pool.fetchrow(
        "SELECT email, created_at, last_login_at FROM users WHERE id = $1", user_id
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    prefs = await pool.fetchrow(
        "SELECT locale, theme FROM user_preferences WHERE user_id = $1", user_id
    )
    watch = await pool.fetch(
        "SELECT ticker, added_at FROM user_watchlist WHERE user_id = $1", user_id
    )
    byok = await pool.fetch(
        "SELECT provider, last4, model, encrypted_at, last_used_at "
        "FROM user_byok WHERE user_id = $1",
        user_id,
    )
    return {
        "user": {
            "email": user["email"],
            "created_at": user["created_at"].isoformat(),
            "last_login_at": user["last_login_at"].isoformat()
            if user["last_login_at"] else None,
        },
        "preferences": dict(prefs) if prefs else None,
        "watchlist": [w["ticker"] for w in watch],
        # Ciphertext deliberately excluded - the user already has their
        # plaintext key; exporting ciphertext would just be noise.
        "byok_metadata": [
            {
                "provider": b["provider"],
                "last4": b["last4"],
                "model": b["model"],
                "encrypted_at": b["encrypted_at"].isoformat(),
                "last_used_at": b["last_used_at"].isoformat()
                if b["last_used_at"] else None,
            }
            for b in byok
        ],
    }
```

- [ ] **Step 4: Register the router in api/index.py**

Locate the `alerts_router` registration block in `api/index.py` (added in M4b A1, after the `admin_router` block). Append immediately after it:

```python
try:
    from alpha_agent.api.routes.user import router as user_router
    app.include_router(user_router)
    print(f"✓ user routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["user"] = msg
    print(f"✗ user routes: {msg}", file=sys.stderr, flush=True)
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/api/test_user_routes.py -v
pytest tests/api/ -q 2>&1 | tail -5
```

Expected: 6/6 pass on test_user_routes.py; full tests/api/ no regressions.

```bash
git add alpha_agent/api/routes/user.py api/index.py tests/api/test_user_routes.py
git commit -m "feat(api): user routes - profile / BYOK / account lifecycle (M5 B1)

6 endpoints under /api/user, all require_user-gated:
- GET /me                   profile + has_byok flag
- POST /byok                AES-256-GCM encrypt + UPSERT; returns last4 only
- GET /byok                 last4 + metadata, never the plaintext key
- DELETE /byok              drop the stored key
- POST /account/delete      single DELETE FROM users; CASCADE FKs do the rest
- GET /account/export       JSON dump (byok ciphertext deliberately excluded)

Plaintext API key never echoed in any response; Field(repr=False) on the
request model. If openapi.snapshot.json drift fails, regen via
make openapi-export and include in this commit."
```

---

## Phase C — Backend route auth integration

### Task C1: brief.py + admin.py require auth

**Why:** Rich brief now reads the BYOK key server-side from `user_byok` for the authenticated user, instead of accepting it in the request body. `admin/refresh` becomes auth-gated.

**Files:**
- Modify: `alpha_agent/api/routes/brief.py`
- Modify: `alpha_agent/api/routes/admin.py`
- Test: `tests/api/test_brief_stream_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_brief_stream_auth.py`:

```python
# tests/api/test_brief_stream_auth.py
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"
_MASTER = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _MASTER)
    from api.index import app
    return TestClient(app)


def _auth(sub="42"):
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iat": now, "exp": now + 3600},
                     _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def _signal_row():
    return {
        "ticker": "AAPL", "rating": "OW", "composite": 1.2,
        "breakdown": json.dumps({"breakdown": []}),
        "fetched_at": __import__("datetime").datetime(2026, 5, 14),
    }


def test_brief_stream_401_without_auth(client):
    r = client.post("/api/brief/AAPL/stream", json={})
    assert r.status_code == 401


def test_brief_stream_400_when_no_byok_key(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[_signal_row(), None])  # signal row, then no byok
    monkeypatch.setattr("alpha_agent.api.routes.brief.get_db_pool",
                        AsyncMock(return_value=pool))
    r = client.post("/api/brief/AAPL/stream", headers=_auth(), json={})
    assert r.status_code == 400
    assert "settings" in r.json()["detail"].lower()


def test_brief_stream_decrypts_byok_and_streams(client, monkeypatch):
    from alpha_agent.auth.crypto_box import encrypt
    ciphertext, nonce = encrypt("sk-real-user-key", _MASTER.encode())
    byok_row = {
        "provider": "openai", "ciphertext": ciphertext, "nonce": nonce,
        "model": "gpt-4o-mini", "base_url": None,
    }
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=[_signal_row(), byok_row])
    pool.execute = AsyncMock()
    monkeypatch.setattr("alpha_agent.api.routes.brief.get_db_pool",
                        AsyncMock(return_value=pool))

    captured = {}

    async def fake_stream(*, provider, api_key, **kwargs):
        captured["provider"] = provider
        captured["api_key"] = api_key
        yield {"type": "summary", "delta": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("alpha_agent.api.routes.brief.stream_brief", fake_stream)
    with client.stream("POST", "/api/brief/AAPL/stream", headers=_auth(), json={}) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    # The server decrypted the stored key and passed the plaintext to the streamer.
    assert captured["api_key"] == "sk-real-user-key"
    assert captured["provider"] == "openai"
    assert '"type": "done"' in body


def test_admin_refresh_401_without_auth(client):
    r = client.post("/api/admin/refresh", json={"job": "fast_intraday"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_brief_stream_auth.py -v
```

Expected: FAIL — `/api/brief/AAPL/stream` currently accepts no-auth (200/422, not 401); `/api/admin/refresh` not auth-gated.

- [ ] **Step 3: Modify brief.py**

In `alpha_agent/api/routes/brief.py`, replace the `StreamBriefRequest` model and the `post_brief_stream` function (the M4b block at the end of the file) with:

```python
class StreamBriefRequest(BaseModel):
    # Phase 4: the BYOK key is no longer in the body - it is read
    # server-side from user_byok for the authenticated user. Only an
    # optional model override remains.
    model_override: str | None = None


@router.post("/{ticker}/stream")
async def post_brief_stream(
    payload: StreamBriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
    user_id: int = Depends(require_user),
) -> StreamingResponse:
    """SSE-streaming Rich brief. Auth required; BYOK key fetched + decrypted
    server-side from the authenticated user's stored credentials."""
    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT ticker, rating, composite, breakdown, fetched_at "
        "FROM daily_signals_fast WHERE ticker = $1 "
        "ORDER BY fetched_at DESC LIMIT 1",
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    byok = await pool.fetchrow(
        "SELECT provider, ciphertext, nonce, model, base_url "
        "FROM user_byok WHERE user_id = $1 LIMIT 1",
        user_id,
    )
    if byok is None:
        raise HTTPException(
            status_code=400, detail="No BYOK key set; visit /settings to add one"
        )

    master = os.environ.get("BYOK_MASTER_KEY")
    if not master:
        raise HTTPException(status_code=500, detail="BYOK_MASTER_KEY not configured")

    breakdown: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    composite = float(row["composite"]) if row["composite"] is not None else 0.0
    rating = row["rating"] or "HOLD"

    async def generator():
        try:
            plaintext_key = decrypt(byok["ciphertext"], byok["nonce"], master.encode("utf-8"))
        except CryptoError:
            yield _sse_format({
                "type": "error",
                "message": "Stored key cannot be decrypted. Please re-save it in /settings.",
            })
            return
        try:
            async for event in stream_brief(
                provider=byok["provider"],
                api_key=plaintext_key,
                ticker=ticker,
                rating=rating,
                composite=composite,
                breakdown=breakdown,
                model=payload.model_override or byok["model"],
                base_url=byok["base_url"],
            ):
                yield _sse_format(event)
                await asyncio.sleep(0)
            # Stamp usage for the /settings "last used" display.
            await pool.execute(
                "UPDATE user_byok SET last_used_at = now() "
                "WHERE user_id = $1 AND provider = $2",
                user_id, byok["provider"],
            )
        except Exception as e:
            # Sanitize: never echo the api_key. type + truncated message only.
            yield _sse_format({
                "type": "error",
                "message": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
```

Then update the imports at the top of the M4b appended block (or the file's import section) — add:

```python
import os

from alpha_agent.auth.crypto_box import CryptoError, decrypt
from alpha_agent.auth.dependencies import require_user
```

`asyncio`, `StreamingResponse`, `stream_brief`, `_sse_format`, `Depends`, `Path`, `BaseModel`, `HTTPException`, `json`, `get_db_pool` are already imported from M4b — do not duplicate. Add `Depends` to the `from fastapi import ...` line if it is not already there.

- [ ] **Step 4: Modify admin.py**

In `alpha_agent/api/routes/admin.py`, the `trigger_refresh` function currently checks `x_refresh_auth` against `REFRESH_SECRET`. Phase 4 layers `require_user` on top. Change the function signature:

```python
from alpha_agent.auth.dependencies import require_user

# ... in the route:
@router.post("/refresh", response_model=RefreshResponse)
async def trigger_refresh(
    body: RefreshRequest,
    user_id: int = Depends(require_user),
) -> RefreshResponse:
    # The x_refresh_auth header check is removed - require_user is the gate
    # now. Any signed-in user can trigger a refresh (Phase 4 has no roles).
```

Remove the `x_refresh_auth: str | None = Header(default=None)` parameter and the `secret = os.environ.get("REFRESH_SECRET")` / `if secret and x_refresh_auth != secret` block. Keep everything after the auth check (the `GH_PAT` lookup + dispatch logic) unchanged. Ensure `Depends` is imported from fastapi.

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/api/test_brief_stream_auth.py -v
pytest tests/api/ -q 2>&1 | tail -5
```

Expected: 4/4 pass on the new file; existing tests/api/ — note `test_brief_stream.py` from M4b will now FAIL because it posts a body with `provider`/`api_key` and no auth. Update `tests/api/test_brief_stream.py`: the M4b tests that posted `{provider, api_key}` should be deleted or rewritten to use auth + the new `{}` / `{model_override}` body. Replace the M4b-era body-key tests with the auth-aware versions from `test_brief_stream_auth.py` (they supersede). After the rewrite, the full suite is green.

```bash
git add alpha_agent/api/routes/brief.py alpha_agent/api/routes/admin.py tests/api/test_brief_stream_auth.py tests/api/test_brief_stream.py
git commit -m "feat(api): brief stream + admin refresh require auth (M5 C1)

/api/brief/{ticker}/stream is now require_user-gated. The BYOK key
leaves the request body entirely - the server looks up the caller's
user_byok row, decrypts it with BYOK_MASTER_KEY, and passes the
plaintext to stream_brief(). Decrypt failure surfaces as an SSE error
event pointing the user at /settings. last_used_at is stamped after a
successful stream.

/api/admin/refresh drops the X-Refresh-Auth shared-secret header in
favor of require_user - any signed-in user can trigger a refresh.

M4b test_brief_stream.py body-key tests rewritten to the auth-aware
contract."
```

---

## Phase D — Frontend NextAuth core

### Task D1: NextAuth.js config + deps

**Why:** `auth.ts` is the NextAuth.js v5 config object — Email provider via Resend SMTP, Postgres adapter, JWT session strategy, and the `jwt` callback that stamps `user.id` into `token.sub` so the backend can read it.

**Files:**
- Modify: `frontend/package.json` (deps)
- Create: `frontend/src/auth.ts`

- [ ] **Step 1: Add the dependencies**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npm install next-auth@beta @auth/pg-adapter pg nodemailer
npm install --save-dev @types/pg @types/nodemailer
```

`next-auth@beta` resolves to the v5 line. Verify `package.json` now lists `next-auth`, `@auth/pg-adapter`, `pg`, `nodemailer`.

- [ ] **Step 2: Write auth.ts**

Create `frontend/src/auth.ts`:

```typescript
// frontend/src/auth.ts
//
// NextAuth.js v5 config. Email magic-link provider via Resend SMTP,
// Postgres adapter (raw SQL, no ORM), JWT session strategy. The jwt
// callback stamps the DB user id into token.sub so the FastAPI backend
// can read it from the same NEXTAUTH_SECRET-signed token.
import NextAuth from "next-auth";
import Email from "next-auth/providers/nodemailer";
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
      maxAge: 24 * 60 * 60, // magic links valid 24h
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    jwt: async ({ token, user }) => {
      // `user` is only present on initial sign-in; persist its id into sub.
      if (user?.id) token.sub = String(user.id);
      return token;
    },
    session: async ({ session, token }) => {
      if (token.sub && session.user) {
        (session.user as { id?: string }).id = token.sub;
      }
      return session;
    },
  },
  pages: {
    signIn: "/signin",
    verifyRequest: "/signin/check-email",
    error: "/signin/error",
  },
});
```

- [ ] **Step 3: Verify tsc**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
```

Expected: silent. If `next-auth/providers/nodemailer` is not found, the installed v5 beta may export the email provider as `next-auth/providers/email` — try that import path and keep whichever compiles.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/package.json frontend/package-lock.json frontend/src/auth.ts
git commit -m "feat(auth): NextAuth.js v5 config - email magic link + pg adapter (M5 D1)

auth.ts wires the Resend SMTP Email provider, the raw-SQL Postgres
adapter (no ORM), and JWT session strategy. The jwt callback persists
the DB user id into token.sub so the FastAPI backend can verify the
same NEXTAUTH_SECRET-signed token and read the user_id. Magic links
expire after 24h. Adds next-auth + @auth/pg-adapter + pg + nodemailer."
```

---

### Task D2: NextAuth route handler + protected-route middleware

**Why:** The `[...nextauth]` route handler mounts all `/api/auth/*` endpoints. The middleware redirects unauthenticated visitors away from protected pages with a `callbackUrl` bounce-back.

**Files:**
- Create: `frontend/src/app/api/auth/[...nextauth]/route.ts`
- Create: `frontend/src/middleware.ts`

- [ ] **Step 1: Write the route handler**

Create `frontend/src/app/api/auth/[...nextauth]/route.ts`:

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
// Mounts all NextAuth.js v5 endpoints: signin, callback, signout, session, csrf.
import { handlers } from "@/auth";

export const { GET, POST } = handlers;
```

- [ ] **Step 2: Write the middleware**

Create `frontend/src/middleware.ts`:

```typescript
// frontend/src/middleware.ts
//
// Protected-route gate. /picks /stock /alerts stay public (spec B-tier);
// only /settings requires a session. Unauthenticated access redirects to
// /signin?callbackUrl=<original> so the user bounces straight back after
// the magic-link round-trip.
import { auth } from "@/auth";
import { NextResponse } from "next/server";

const PROTECTED_PREFIXES = ["/settings"];

export default auth((req) => {
  const { pathname } = req.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (isProtected && !req.auth) {
    const signinUrl = new URL("/signin", req.nextUrl.origin);
    signinUrl.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(signinUrl);
  }
  return NextResponse.next();
});

export const config = {
  // Run on app pages, skip Next internals + static assets + the auth API
  // itself (NextAuth handles its own routes).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/auth).*)"],
};
```

- [ ] **Step 3: Verify tsc + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next build 2>&1 | tail -8
```

Expected: tsc silent; build succeeds. The build exercises the middleware + route handler wiring.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/api/auth/[...nextauth]/route.ts" frontend/src/middleware.ts
git commit -m "feat(auth): NextAuth route handler + protected-route middleware (M5 D2)

[...nextauth]/route.ts mounts signin/callback/signout/session/csrf.
middleware.ts gates /settings only (B-tier: picks/stock/alerts stay
public) and redirects unauthenticated access to
/signin?callbackUrl=<original> for a clean bounce-back."
```

---

## Phase E — Frontend UI

### Task E1: /signin pages + i18n keys

**Why:** Three small pages: the magic-link email form, the "check your inbox" confirmation, and the expired/invalid-link landing.

**Files:**
- Create: `frontend/src/app/(auth)/signin/page.tsx`
- Create: `frontend/src/app/(auth)/signin/check-email/page.tsx`
- Create: `frontend/src/app/(auth)/signin/error/page.tsx`
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, locate the last M4b key block (`rich.aborted` from M4b E1b). Add after it in BOTH zh and en blocks.

zh block:
```typescript
    "signin.title": "登录",
    "signin.email_label": "邮箱地址",
    "signin.email_placeholder": "you@example.com",
    "signin.send_button": "发送登录链接",
    "signin.sending": "发送中…",
    "signin.check_email_title": "查收邮件",
    "signin.check_email_body": "登录链接已发送。点击邮件里的链接即可登录（24 小时内有效）。",
    "signin.error_title": "链接无效",
    "signin.error_body": "登录链接已过期或已被使用。请重新申请。",
    "signin.back_to_signin": "重新登录",
    "auth.sign_in": "登录",
    "auth.sign_out": "退出",
    "auth.account": "账户",
```

en block:
```typescript
    "signin.title": "Sign in",
    "signin.email_label": "Email address",
    "signin.email_placeholder": "you@example.com",
    "signin.send_button": "Send magic link",
    "signin.sending": "Sending…",
    "signin.check_email_title": "Check your inbox",
    "signin.check_email_body": "A sign-in link has been sent. Click it to sign in (valid for 24 hours).",
    "signin.error_title": "Invalid link",
    "signin.error_body": "The sign-in link has expired or was already used. Request a new one.",
    "signin.back_to_signin": "Back to sign in",
    "auth.sign_in": "Sign in",
    "auth.sign_out": "Sign out",
    "auth.account": "Account",
```

- [ ] **Step 2: Write the three pages**

Create `frontend/src/app/(auth)/signin/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import { useEffect } from "react";

export default function SignInPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const params = useSearchParams();
  const callbackUrl = params.get("callbackUrl") ?? "/picks";

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    await signIn("nodemailer", { email, callbackUrl });
    // NextAuth redirects to /signin/check-email on success.
  };

  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6">
      <h1 className="mb-4 text-lg font-semibold text-tm-fg">
        {t(locale, "signin.title")}
      </h1>
      <form onSubmit={onSubmit} className="space-y-3">
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
        <button
          type="submit"
          disabled={sending}
          className="w-full rounded border border-tm-rule bg-tm-bg px-3 py-1.5 text-sm text-tm-fg hover:border-tm-accent disabled:opacity-60"
        >
          {t(locale, sending ? "signin.sending" : "signin.send_button")}
        </button>
      </form>
    </div>
  );
}
```

Create `frontend/src/app/(auth)/signin/check-email/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function CheckEmailPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-fg">
        {t(locale, "signin.check_email_title")}
      </h1>
      <p className="text-sm text-tm-muted">{t(locale, "signin.check_email_body")}</p>
    </div>
  );
}
```

Create `frontend/src/app/(auth)/signin/error/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function SignInErrorPage() {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  return (
    <div className="mx-auto mt-24 max-w-sm rounded border border-tm-rule bg-tm-bg-2 p-6 text-center">
      <h1 className="mb-2 text-lg font-semibold text-tm-neg">
        {t(locale, "signin.error_title")}
      </h1>
      <p className="mb-4 text-sm text-tm-muted">{t(locale, "signin.error_body")}</p>
      <Link href="/signin" className="text-sm text-tm-accent hover:underline">
        {t(locale, "signin.back_to_signin")}
      </Link>
    </div>
  );
}
```

- [ ] **Step 3: Verify tsc + lint**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint
```

Expected: clean. NOTE: `signIn("nodemailer", ...)` — the provider id must match the provider used in `auth.ts`. If D1 used `next-auth/providers/email` instead of `nodemailer`, change the id here to `"email"`.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add "frontend/src/app/(auth)/signin/page.tsx" "frontend/src/app/(auth)/signin/check-email/page.tsx" "frontend/src/app/(auth)/signin/error/page.tsx" frontend/src/lib/i18n.ts
git commit -m "feat(auth): /signin pages - magic-link form + confirmation + error (M5 E1)

Three small client pages: email form (posts via signIn), check-email
confirmation, and expired/invalid-link landing. i18n keys for signin.*
+ auth.* in both zh and en."
```

---

### Task E2: Sidebar auth slot + i18n

**Why:** The sidebar bottom shows "Sign in" when anonymous, or the user's email + "Sign out" when authed.

**Files:**
- Create: `frontend/src/components/layout/SidebarAuthSlot.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Write SidebarAuthSlot.tsx**

Create `frontend/src/components/layout/SidebarAuthSlot.tsx`:

```tsx
"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { LogIn, LogOut, UserCircle } from "lucide-react";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

export default function SidebarAuthSlot() {
  const { data: session, status } = useSession();
  const { locale } = useLocale();

  if (status === "loading") {
    return (
      <div className="border-t border-tm-rule p-3 text-[10.5px] text-tm-muted">
        …
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="border-t border-tm-rule p-3">
        <button
          type="button"
          onClick={() => signIn()}
          className="flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
        >
          <LogIn aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
          {t(locale, "auth.sign_in")}
        </button>
      </div>
    );
  }

  const email = session.user.email ?? "user";
  return (
    <div className="border-t border-tm-rule p-3 space-y-1">
      <div className="flex items-center gap-2 px-1.5 text-[10.5px] text-tm-muted">
        <UserCircle aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span className="truncate">{email}</span>
      </div>
      <button
        type="button"
        onClick={() => signOut({ callbackUrl: "/picks" })}
        className="flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"
      >
        <LogOut aria-hidden className="h-3.5 w-3.5" strokeWidth={1.75} />
        {t(locale, "auth.sign_out")}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Mount it in Sidebar.tsx**

In `frontend/src/components/layout/Sidebar.tsx`, add the import near the top:

```tsx
import SidebarAuthSlot from "./SidebarAuthSlot";
```

Then place `<SidebarAuthSlot />` just before the closing `</aside>` tag, after the footer "system online" pulse block (so it sits at the very bottom of the sidebar).

- [ ] **Step 3: Wrap the app in SessionProvider**

`useSession()` requires a `SessionProvider` ancestor. In `frontend/src/app/layout.tsx` (the root layout), wrap the existing children tree with NextAuth's provider. Add the import:

```tsx
import { SessionProvider } from "next-auth/react";
```

And wrap the body content:

```tsx
        <SessionProvider>
          {/* existing providers + children */}
        </SessionProvider>
```

If the root layout already has a provider nesting (LocaleProvider, ThemeProvider), put `SessionProvider` as the outermost wrapper inside `<body>`.

- [ ] **Step 4: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -6
```

Expected: all clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/layout/SidebarAuthSlot.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/app/layout.tsx
git commit -m "feat(auth): sidebar auth slot - sign in / email / sign out (M5 E2)

SidebarAuthSlot reads useSession(): anonymous shows a Sign in button,
authed shows the email + Sign out. Mounted at the sidebar bottom below
the system-online pulse. Root layout wrapped in SessionProvider so
useSession works app-wide. lucide-react icons (LogIn/LogOut/UserCircle)."
```

---

### Task E3: /settings server-side BYOK + import banner + danger zone

**Why:** The BYOK form posts to the backend instead of localStorage. A one-time banner offers to import an existing localStorage key. A danger zone adds Export + Delete account.

**Files:**
- Create: `frontend/src/lib/api/user.ts`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, append after the `auth.account` key from E1 in both blocks.

zh block:
```typescript
    "settings.byok.saved_as": "已保存，结尾 …{last4}",
    "settings.byok.import_banner": "检测到浏览器里有 BYOK key，是否导入服务端？",
    "settings.byok.import_button": "导入",
    "settings.byok.discard_button": "丢弃",
    "settings.danger.title": "危险操作",
    "settings.danger.export": "导出我的数据",
    "settings.danger.delete": "删除账户",
    "settings.danger.delete_confirm": "输入 DELETE 确认",
```

en block:
```typescript
    "settings.byok.saved_as": "Saved, ending in …{last4}",
    "settings.byok.import_banner": "A BYOK key was found in this browser. Import it to the server?",
    "settings.byok.import_button": "Import",
    "settings.byok.discard_button": "Discard",
    "settings.danger.title": "Danger zone",
    "settings.danger.export": "Export my data",
    "settings.danger.delete": "Delete account",
    "settings.danger.delete_confirm": "Type DELETE to confirm",
```

- [ ] **Step 2: Write the user API client**

Create `frontend/src/lib/api/user.ts`:

```typescript
// frontend/src/lib/api/user.ts
//
// Typed client for the Phase 4 /api/user/* backend routes. All calls use
// credentials: "include" so the same-origin NextAuth JWT cookie rides
// along; the Next.js rewrite forwards it to FastAPI as the Bearer token.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app";

export interface ByokGetResponse {
  provider: string;
  last4: string;
  model: string | null;
  base_url: string | null;
  encrypted_at: string;
  last_used_at: string | null;
}

export interface ByokSaveResponse {
  provider: string;
  last4: string;
  encrypted_at: string;
}

export async function getByok(): Promise<ByokGetResponse | null> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    credentials: "include",
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getByok failed: HTTP ${r.status}`);
  return (await r.json()) as ByokGetResponse;
}

export async function saveByok(body: {
  provider: string;
  api_key: string;
  model?: string;
  base_url?: string;
}): Promise<ByokSaveResponse> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`saveByok failed: HTTP ${r.status}`);
  return (await r.json()) as ByokSaveResponse;
}

export async function deleteByok(): Promise<void> {
  const r = await fetch(`${API_BASE}/api/user/byok`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) throw new Error(`deleteByok failed: HTTP ${r.status}`);
}

export async function deleteAccount(): Promise<void> {
  const r = await fetch(`${API_BASE}/api/user/account/delete`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok && r.status !== 204) throw new Error(`deleteAccount failed: HTTP ${r.status}`);
}

export async function exportAccount(): Promise<Record<string, unknown>> {
  const r = await fetch(`${API_BASE}/api/user/account/export`, {
    credentials: "include",
  });
  if (!r.ok) throw new Error(`exportAccount failed: HTTP ${r.status}`);
  return (await r.json()) as Record<string, unknown>;
}
```

- [ ] **Step 3: Rework the settings page**

Modify `frontend/src/app/(dashboard)/settings/page.tsx`. The exact edits depend on the current structure (the M3/M4b BYOK form), so the implementer must read the file first. The required changes:

1. The BYOK save handler calls `saveByok()` from `@/lib/api/user` instead of `saveByok()` from `@/lib/byok`.
2. On mount, run the import-banner check: read `localStorage` for the legacy `alpha-agent.byok.v1` key AND call `getByok()`. If localStorage has a key AND `getByok()` returns null, render the import banner.
3. Import banner: "Import" button POSTs the localStorage contents via `saveByok()`, and on success `localStorage.removeItem("alpha-agent.byok.v1")`. "Discard" button just removes the localStorage key.
4. Add a "Danger zone" collapsible section at the bottom with two buttons:
   - "Export my data" → `exportAccount()` → triggers a browser download of the JSON.
   - "Delete account" → confirmation (type DELETE) → `deleteAccount()` → `signOut({callbackUrl: "/signin"})`.

The implementer should preserve the existing form layout and tm-* token styling, adding the banner above the form and the danger zone below it. If the existing settings page is too tangled to modify surgically, REPORT BACK as NEEDS_CONTEXT with the current file contents — do not rewrite the whole page from scratch.

- [ ] **Step 4: Verify tsc + lint**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/api/user.ts "frontend/src/app/(dashboard)/settings/page.tsx" frontend/src/lib/i18n.ts
git commit -m "feat(settings): server-side BYOK + import banner + danger zone (M5 E3)

BYOK form now posts to /api/user/byok (server-side AES-256-GCM storage)
instead of localStorage. First-load import banner detects a legacy
localStorage key and offers one-click import (clears localStorage on
success). Danger zone adds Export my data (JSON download) and Delete
account (type-DELETE confirm, then signOut). New typed client in
lib/api/user.ts; all calls use credentials:include so the JWT cookie
rides along."
```

---

### Task E4: RichThesis switches to useSession

**Why:** RichThesis must stop reading `loadByok()` from localStorage. Authenticated → POST `/api/brief/{ticker}/stream` with `credentials: "include"` (cookie carries the JWT). Unauthenticated → a Link to `/signin`.

**Files:**
- Modify: `frontend/src/components/stock/RichThesis.tsx`
- Modify: `frontend/src/lib/api/streamBrief.ts`

- [ ] **Step 1: Update streamBrief.ts**

In `frontend/src/lib/api/streamBrief.ts`, the M4b `streamBrief` function takes a `StreamBriefBody` with `{provider, api_key, model?, base_url?}`. Phase 4 removes the key from the body. Change the function signature + fetch call:

```typescript
export interface StreamBriefBody {
  model_override?: string;
}

export async function* streamBrief(
  ticker: string,
  body: StreamBriefBody = {},
  signal?: AbortSignal,
): AsyncGenerator<BriefEvent, void, void> {
  const r = await fetch(`${API_BASE}/api/brief/${ticker.toUpperCase()}/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include", // same-origin JWT cookie -> Bearer at the rewrite
    body: JSON.stringify(body),
    signal,
  });
  // ... rest of the M4b reader logic is unchanged
```

Keep the entire ReadableStream reader body from M4b — only the signature, the `body` shape, and the added `credentials: "include"` change.

- [ ] **Step 2: Update RichThesis.tsx**

In `frontend/src/components/stock/RichThesis.tsx`:

1. Remove the `import { loadByok, hasByok } from "@/lib/byok"` line.
2. Add `import { useSession } from "next-auth/react"`.
3. Replace the `keyPresent` state + the `hasByok()` / `loadByok()` logic with `const { data: session, status } = useSession()`.
4. The "no key" branch becomes "no session": when `status === "unauthenticated"`, render a `<Link href="/signin?callbackUrl=/stock/${ticker}">` with the existing `rich.no_key_hint` i18n text (or a new `rich.sign_in_hint` if you prefer — reuse `rich.no_key_hint` to avoid an i18n churn).
5. The `onGenerate` callback no longer reads `loadByok()` — it just calls `streamBrief(ticker, {}, ac.signal)`. The backend resolves the key from the authenticated user's `user_byok` row.
6. The storage-event listener (multi-tab key change) is removed — there is no localStorage key anymore. Replace it with nothing; `useSession` already reacts to auth state changes.

The rest of the component (streaming accumulation into summary/bull/bear, abort button, error states) is unchanged.

- [ ] **Step 3: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build 2>&1 | tail -6
```

Expected: all clean.

- [ ] **Step 4: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/components/stock/RichThesis.tsx frontend/src/lib/api/streamBrief.ts
git commit -m "feat(stock): RichThesis uses session auth, not localStorage BYOK (M5 E4)

RichThesis reads useSession() instead of loadByok(). Unauthenticated ->
Link to /signin?callbackUrl. Authenticated -> POST the stream with
credentials:include; the backend resolves the BYOK key from the user's
encrypted user_byok row. streamBrief body drops provider/api_key, keeps
only an optional model_override. The multi-tab storage listener is
removed (no localStorage key to watch anymore)."
```

---

## Phase F — Acceptance

### Task F1: m5-acceptance Makefile + smoke + deploy + handoff

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append the m5-acceptance target**

Add to the end of `Makefile` (after `m4b-acceptance`):

```makefile

m5-acceptance:
	@echo "==> Running M5 acceptance suite"
	# Backend: auth module + user routes + brief auth tests
	pytest tests/auth/ tests/api/test_user_routes.py tests/api/test_brief_stream_auth.py -v
	# Frontend: deps clean, types clean, lint clean, builds
	cd frontend && npm ci
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: protected endpoints reject anonymous access
	@echo "==> Smoke: POST /api/brief/AAPL/stream without auth -> 401"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  -X POST -H 'content-type: application/json' -d '{}' \
	  "https://alpha.bobbyzhong.com/api/brief/AAPL/stream"); \
	  if [ "$$code" != "401" ]; then echo "expected 401 got $$code"; exit 1; fi
	@echo "==> Smoke: GET /api/user/me without auth -> 401"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  "https://alpha.bobbyzhong.com/api/user/me"); \
	  if [ "$$code" != "401" ]; then echo "expected 401 got $$code"; exit 1; fi
	@echo "M5 acceptance PASS"
```

- [ ] **Step 2: Run the pytest portion locally**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/auth/ tests/api/test_user_routes.py tests/api/test_brief_stream_auth.py -v 2>&1 | tail -15
```

Expected: all green (5 migration + 5 crypto + 5 jwt + 6 deps + 6 user + 4 brief auth = 31 tests).

- [ ] **Step 3: USER ACTION — set env vars + apply migration**

This step is the user's, not the implementer's. The implementer prints these instructions and waits:

> **Before the acceptance smoke can pass, the user must:**
> 1. Set the env vars listed in the "USER SETUP" section of this plan (NEXTAUTH_SECRET on both Vercel projects, BYOK_MASTER_KEY on backend, NEXTAUTH_URL + RESEND_API_KEY + EMAIL_FROM on frontend).
> 2. Apply the V002 migration to the Neon production DB.
> 3. Verify the Resend sending domain.

- [ ] **Step 4: Deploy backend + frontend (both auto on git push)**

As of 2026-05-14 the frontend Vercel project's `rootDirectory` was set to
`frontend` (API PATCH after the M4b error-analysis). Both the backend
(`alpha-agent`) and the frontend (`frontend`) Vercel projects now
auto-deploy on `git push origin main` — no manual `vercel` invocation
needed.

Verify both deploys reach READY via the Vercel API or direct HTTP probe.
If the Vercel API token is expired (403/empty response — see CLAUDE.md
memory `feedback_vercel_authjson_token_expiry.md`), fall back to HTTP
probes: `curl -I https://alpha.bobbyzhong.com/<route>`.

If a manual frontend deploy is ever needed (e.g. a hotfix without a
commit), run it **from the repo root**, NOT from `frontend/` — with
`rootDirectory=frontend` set, running from `frontend/` would make Vercel
look for `frontend/frontend` (the doubled-path trap, memory
`feedback_vercel_root_directory_doubled_path.md`):

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
VTOK=$(python3 -c "import json; print(json.load(open('/Users/a22309/Library/Application Support/com.vercel.cli/auth.json'))['token'])")
vercel deploy --prod --token "$VTOK" --scope team_F2QuyPNaBdqEtaQ1LmBrASKG 2>&1 | tail -6
```

- [ ] **Step 5: Run the full acceptance target**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
make m5-acceptance 2>&1 | tail -20
```

Expected: ends with `M5 acceptance PASS`.

- [ ] **Step 6: Manual UAT**

Run the 13-item manual UAT checklist from spec §6.4. Capture screenshots of the sign-in flow + /settings server-side BYOK + RichThesis-while-signed-out into `docs/superpowers/screenshots/m5-*.png`.

- [ ] **Step 7: Commit + handoff**

```bash
mkdir -p docs/superpowers/screenshots
git add Makefile docs/superpowers/screenshots/
git commit -m "ci(m5): m5-acceptance Makefile + Phase 4 UAT screenshots

Encodes pytest (auth module + user routes + brief auth) + frontend
tsc/lint/build + two 401 smokes against the deployed backend.
Acceptance reproducible by 'make m5-acceptance'. Manual UAT covers the
13-item checklist from the Phase 4 spec section 6.4.

Phase 4 SHIPS: multi-user auth + server-side encrypted BYOK live.
Next: Phase 3 (LLM news sentiment) - separate spec."
git push origin main
```

---

## Hand-off

**After M5 acceptance + visual approval, Phase 4 is complete.** Next is Phase 3 (LLM-backed news sentiment, on-demand when a user opens /stock, 15-min cache) — it gets its own brainstorming → spec → plan cycle and now has a clean server-side BYOK key to read from.

**M5 → Phase 3 contract:**

| M5 output | Phase 3 consumer |
|-----------|------------------|
| `crypto_box.decrypt` + `user_byok` lookup | Phase 3 sentiment scorer decrypts the same user key server-side |
| `require_user` dependency | The on-demand sentiment endpoint is auth-gated the same way |
| The `/stock/[ticker]` page already auth-aware (RichThesis) | Sentiment re-score reuses the same session check |

---

## Risk Matrix

Inherits spec §10 in full. Implementation-specific additions:

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `next-auth@beta` v5 API differs from the config in D1 (provider import path, callback shape) | Medium | D1 Step 3 explicitly says try `next-auth/providers/email` if `nodemailer` import fails; the implementer adapts the import + provider id and keeps whichever compiles. E1 Step 3 cross-references the provider id. |
| `@auth/pg-adapter` table column names mismatch V002 schema | Medium | V002 `users` + `verification_tokens` columns match the documented NextAuth.js Postgres adapter schema. If the adapter rejects, the implementer compares the adapter's expected schema and reports a NEEDS_CONTEXT rather than guessing. |
| M4b `test_brief_stream.py` breaks (posts body key, no auth) | High (expected) | C1 Step 5 explicitly rewrites those tests to the auth-aware contract; this is planned, not a surprise. |
| Frontend `SessionProvider` placement breaks existing provider nesting | Medium | E2 Step 3 says place it as the outermost wrapper inside `<body>`; the implementer reads the current layout.tsx first. |
| openapi.snapshot.json drift on new user routes | Medium | B1 Step 5 commit message instructs `make openapi-export` regen if the snapshot test fails (M4a/M4b precedent). |
| `pg.Pool` opens a connection at frontend module load (cold start cost) | Low | Acceptable; NextAuth.js needs the adapter pool. Neon's serverless driver could replace `pg` later if cold starts bite. |
| User forgets to set env vars before F1 smoke | Medium | F1 Step 3 is an explicit USER ACTION gate; the smoke fails loudly with "expected 401 got 500" if NEXTAUTH_SECRET is missing. |

---

## LOC Estimate

- **Backend:** ~620 LOC (V002 migration 60 + crypto_box 70 + jwt_verify 60 + dependencies 50 + user.py 230 + brief/admin edits 80 + tests 270 - shared boilerplate)
- **Frontend:** ~560 LOC (auth.ts 50 + route handler 5 + middleware 30 + signin pages 130 + SidebarAuthSlot 70 + user.ts client 90 + settings edits 100 + RichThesis/streamBrief edits 60 + i18n 30)
- **Plan total: ~1180 LOC of new+modified code across 13 tasks**

---

## Execution Tip

Tier 1 (A1-A4) is the critical path — every later task imports from `alpha_agent/auth/`. Get the crypto + JWT primitives rock-solid (they have the most unit tests for a reason) before touching routes.

The single biggest external-API risk is `next-auth@beta` v5's exact surface (D1/D2). If the implementer hits an import or config-shape mismatch, the right move is NEEDS_CONTEXT with the specific error — the controller can fetch the current NextAuth.js v5 docs via context7 and re-dispatch. Do not guess at the v5 API.

Sequential order: **A1 → A2 → A3 → A4 → B1 → C1 → D1 → D2 → E1 → E2 → E3 → E4 → F1**.
