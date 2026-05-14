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
