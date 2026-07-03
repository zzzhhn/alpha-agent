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
from alpha_agent.auth.crypto_box import CryptoError, encrypt
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
    try:
        ciphertext, nonce = encrypt(body.api_key, master.encode("utf-8"))
    except CryptoError as e:
        # A malformed BYOK_MASTER_KEY (e.g. a rotated key pasted with a stray
        # newline) must surface its real reason, not an opaque 500 — the user
        # can't fix what they can't see (project no-opaque-500 rule).
        raise HTTPException(
            status_code=400,
            detail=f"server master key is misconfigured: {e}",
        ) from e
    last4 = body.api_key[-4:]
    pool = await get_db_pool()

    # B9 (2026-05-19): snapshot the prior non-secret BYOK coordinates so
    # the change_log can render a diff card for the user. Secret material
    # (ciphertext/nonce) is intentionally OUT of the log — only the
    # operationally-rollback-safe fields (provider/model/base_url) are
    # journaled.
    prior = await pool.fetchrow(
        "SELECT provider, model, base_url FROM user_byok "
        "WHERE user_id = $1 LIMIT 1",
        user_id,
    )

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

    # B9 change-log writes are best-effort (a logger failure must not
    # block the BYOK save the user actually pressed Save on).
    try:
        from alpha_agent.settings.change_log import record_change

        for field, old, new in [
            ("byok.provider", prior["provider"] if prior else None, body.provider),
            ("byok.model", prior["model"] if prior else None, body.model),
            ("byok.base_url", prior["base_url"] if prior else None, body.base_url),
        ]:
            if old != new:
                await record_change(pool, user_id, field, old, new)
    except Exception:  # noqa: BLE001 — log-write failure is non-fatal
        pass
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


# ---------------------------------------------------------------------------
# B9 (2026-05-19) — settings change log + 1-click rollback
# ---------------------------------------------------------------------------


@router.get("/settings/history")
async def settings_history(
    limit: int = 50,
    user_id: int = Depends(require_user),
) -> dict:
    """Recent config edits for the authenticated user, newest first.
    Drives the diff card UI in /settings (mirrors AlertList.tsx pattern)."""
    from alpha_agent.settings.change_log import fetch_history

    pool = await get_db_pool()
    rows = await fetch_history(pool, user_id, limit=min(max(limit, 1), 200))
    return {"changes": rows}


@router.post("/settings/rollback/{change_id}")
async def settings_rollback(
    change_id: int,
    user_id: int = Depends(require_user),
) -> dict:
    """Re-apply the `old_value` of a historical change as a new write,
    journaled as source='rollback' with rollback_of=change_id pointing
    back at the original row.

    Restricted to ROLLBACK_SAFE_FIELDS — secret material (BYOK
    ciphertext) is never round-tripped through this path. To rotate a
    key, the user must re-enter it via /settings/byok manually.
    """
    from alpha_agent.settings.change_log import (
        ROLLBACK_SAFE_FIELDS, fetch_change, record_change,
    )

    pool = await get_db_pool()
    change = await fetch_change(pool, user_id, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail=f"change {change_id} not found")
    field = change["field"]
    if field not in ROLLBACK_SAFE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"field {field!r} not rollback-safe; manual re-entry required",
        )
    target = change["old_value"]

    # Apply the rollback to the actual settings table. For now only
    # byok.* fields are rollback-safe; weight-override rollback wires in
    # at B9.1 when the weight UI ships.
    if field == "byok.provider":
        await pool.execute(
            "UPDATE user_byok SET provider = $1 WHERE user_id = $2",
            target, user_id,
        )
    elif field == "byok.model":
        await pool.execute(
            "UPDATE user_byok SET model = $1 WHERE user_id = $2",
            target, user_id,
        )
    elif field == "byok.base_url":
        await pool.execute(
            "UPDATE user_byok SET base_url = $1 WHERE user_id = $2",
            target, user_id,
        )

    # Journal the rollback as its own row (preserves append-only audit
    # invariant). new_value here is the value we just re-applied; the
    # natural diff = (current_value_before_rollback → target).
    log_id = await record_change(
        pool, user_id, field,
        old_value=change["new_value"],
        new_value=target,
        source="rollback",
        rollback_of=change_id,
    )
    return {"ok": True, "rollback_change_id": log_id, "applied_value": target}
