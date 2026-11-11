"""Phase 4 user routes: profile, BYOK key, account lifecycle.

All routes require auth via require_user. The BYOK key is stored
AES-256-GCM encrypted (crypto_box) and is NEVER returned in plaintext -
GET /byok exposes only last4. Account delete relies on the V002
ON DELETE CASCADE FKs for atomicity.
"""
from __future__ import annotations

import json
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from alpha_agent.api.byok import (
    LLM_CREDENTIAL_PROVIDERS,
    fetch_user_llm_credential,
    managed_llm_client,
)
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.routes.investment import router as investment_router
from alpha_agent.auth.crypto_box import CryptoError, encrypt
from alpha_agent.auth.dependencies import is_admin, require_user
from alpha_agent.llm.base import LLMClient, Message

router = APIRouter(prefix="/api/user", tags=["user"])

router.include_router(investment_router)


class MeResponse(BaseModel):
    user_id: int
    email: str
    created_at: str
    has_byok: bool
    is_admin: bool = False


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


class ByokTestResponse(BaseModel):
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


@router.get("/me", response_model=MeResponse)
async def get_me(user_id: int = Depends(require_user)) -> MeResponse:
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT id, email, created_at FROM users WHERE id = $1", user_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    has_byok = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM user_byok "
        "WHERE user_id = $1 AND provider = ANY($2::text[]))",
        user_id,
        list(LLM_CREDENTIAL_PROVIDERS),
    )
    return MeResponse(
        user_id=row["id"],
        email=row["email"],
        created_at=row["created_at"].isoformat(),
        has_byok=bool(has_byok),
        is_admin=is_admin(user_id),
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
    prior = await fetch_user_llm_credential(pool, user_id)

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
    # One active LLM credential per user.  Preserve non-LLM rows such as
    # ``worldquant_brain`` while removing stale provider choices that could
    # otherwise be selected by old clients or future regressions.
    await pool.execute(
        "DELETE FROM user_byok WHERE user_id = $1 "
        "AND provider = ANY($2::text[]) AND provider <> $3",
        user_id,
        list(LLM_CREDENTIAL_PROVIDERS),
        body.provider,
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
    row = await fetch_user_llm_credential(pool, user_id)
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


@router.post("/byok/test", response_model=ByokTestResponse)
async def test_byok(
    user_id: int = Depends(require_user),
    llm: LLMClient = Depends(managed_llm_client),
) -> ByokTestResponse:
    """Exercise the configured provider without coupling health to factor JSON."""
    started = time.monotonic()
    try:
        result = await llm.chat(
            [Message(role="user", content="Reply with exactly: OK")],
            temperature=0.0,
            max_tokens=128,
        )
        if not result.content.strip():
            raise RuntimeError("provider completed without user-visible text")
    except Exception as exc:  # noqa: BLE001 - normalized into a safe status
        response = getattr(exc, "response", None)
        upstream_status = getattr(response, "status_code", None)
        if upstream_status in (401, 403):
            detail = "LLM provider rejected the API key or account access"
        elif upstream_status == 429:
            detail = "LLM provider quota or rate limit was reached"
        elif upstream_status is not None:
            detail = f"LLM provider returned HTTP {upstream_status}"
        else:
            detail = f"LLM request failed ({type(exc).__name__})"
        raise HTTPException(status_code=502, detail=detail) from exc
    pool = await get_db_pool()
    credential = await fetch_user_llm_credential(pool, user_id)
    if credential is None:
        raise HTTPException(status_code=400, detail="No BYOK key set")
    await pool.execute(
        "UPDATE user_byok SET last_used_at = now() "
        "WHERE user_id = $1 AND provider = $2",
        user_id,
        credential["provider"],
    )
    return ByokTestResponse(
        provider=credential["provider"],
        model=result.model,
        latency_ms=round((time.monotonic() - started) * 1000),
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


@router.delete("/byok", status_code=204)
async def delete_byok(user_id: int = Depends(require_user)) -> Response:
    pool = await get_db_pool()
    await pool.execute(
        "DELETE FROM user_byok WHERE user_id = $1 "
        "AND provider = ANY($2::text[])",
        user_id,
        list(LLM_CREDENTIAL_PROVIDERS),
    )
    return Response(status_code=204)


@router.post("/account/delete", status_code=204)
async def delete_account(user_id: int = Depends(require_user)) -> Response:
    pool = await get_db_pool()
    # ON DELETE CASCADE on user_preferences / user_watchlist / user_byok
    # FKs handles the dependent rows atomically.
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)
    return Response(status_code=204)


_EXPORT_LIMIT = 5000
_EXPORT_SECRET_KEY = re.compile(r"key|secret|token|password|cipher|nonce", re.I)


def _export_json(value):
    """Remove credential-like keys recursively from structured user data."""
    if isinstance(value, dict):
        return {
            key: _export_json(item) for key, item in value.items()
            if not _EXPORT_SECRET_KEY.search(key)
        }
    if isinstance(value, list):
        return [_export_json(item) for item in value]
    return value


@router.get("/account/export")
async def export_account(
    response: Response, user_id: int = Depends(require_user),
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    pool = await get_db_pool()
    user = await pool.fetchrow(
        "SELECT email, created_at, last_login_at FROM users WHERE id = $1", user_id
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    prefs = await pool.fetchrow(
        "SELECT locale, theme, extras->'investment_profile' AS investment_profile "
        "FROM user_preferences WHERE user_id = $1", user_id
    )
    limit = _EXPORT_LIMIT
    watch = await pool.fetch(
        "SELECT ticker, added_at FROM user_watchlist WHERE user_id = $1 "
        "ORDER BY id LIMIT $2", user_id, limit + 1,
    )
    byok = await pool.fetch(
        "SELECT provider, last4, model, encrypted_at, last_used_at "
        "FROM user_byok WHERE user_id = $1 "
        "AND provider = ANY($2::text[]) ORDER BY provider LIMIT $3",
        user_id,
        list(LLM_CREDENTIAL_PROVIDERS),
        limit + 1,
    )
    truncated = {"watchlist": len(watch) > limit, "byok_metadata": len(byok) > limit}

    async def section(name, sql, json_fields=()):
        rows = await pool.fetch(sql, user_id, limit + 1)
        truncated[name] = len(rows) > limit
        items = []
        for row in rows[:limit]:
            item = dict(row)
            for field in json_fields:
                value = item[field]
                item[field] = _export_json(json.loads(value) if isinstance(value, str) else value)
            items.append(item)
        return items

    sections = {}
    # Explicit allowlists: no authentication tables, encrypted credentials,
    # bot context/config snapshots, or lease material enter these queries.
    account_columns = "id, kind, name, status, initial_cash, cash, reset_count, created_at, reset_at"
    sections["paper_accounts"] = await section(
        "paper_accounts", f"SELECT {account_columns} FROM sim_account "
        "WHERE user_id=$1 ORDER BY id LIMIT $2",
    )
    owned_sections = {
        "orders": ("sim_order", """id, account_id, ticker, side, order_type, qty,
            limit_price, signal_date, fill_date, fill_price, status, expire_after_days,
            created_at, filled_at, pick_date, pick_ticker, fail_reason, source_run_id,
            source_policy_id, source_payload_hash, reserved_notional, fee_bps,
            transaction_cost, cohort_id, bot_run_id, action_id, instrument_id,
            execution_model, accepted_at, expires_at, cancel_requested_at,
            reference_price, slippage_bps, execution_evidence""", ("execution_evidence",)),
        "positions": ("sim_position", """id, account_id, ticker, qty, avg_cost,
            realized_pnl, opened_at, updated_at, cohort_id, instrument_id,
            mark_price, mark_at, price_quality""", ()),
        "daily_equity": ("sim_equity_daily", """id, account_id, as_of_date,
            portfolio_value, cash, unrealized_pnl, realized_pnl, benchmark_close,
            cohort_id, valuation_quality, valued_at""", ()),
        "bot_config": ("sim_bot_config", "account_id, config, config_version, updated_at", ("config",)),
        "bot_runs": ("sim_bot_run", """id, account_id, trigger, status, stage,
            trading_session, created_at, started_at, finished_at, summary, error,
            provider, model, prompt_tokens, completion_tokens, llm_calls""", ("result",)),
    }
    for name, (table, columns, json_fields) in owned_sections.items():
        selected = ", ".join(f"t.{column.strip()}" for column in columns.split(","))
        if name == "bot_runs":
            selected += ", jsonb_build_object('outcome_reason', t.result->'outcome_reason') AS result"
        sections[name] = await section(
            name, f"SELECT {selected} FROM {table} t "
            "JOIN sim_account a ON a.id=t.account_id WHERE a.user_id=$1 "
            f"ORDER BY t.{'account_id' if name == 'bot_config' else 'id'} LIMIT $2",
            json_fields,
        )
    sections["investment_notebook"] = await section(
        "investment_notebook",
        "SELECT entry.value AS entry FROM user_preferences p "
        "CROSS JOIN LATERAL jsonb_each(COALESCE(p.extras->'investment_theses', '{}'::jsonb)) entry "
        "WHERE p.user_id=$1 ORDER BY entry.key LIMIT $2", ("entry",),
    )
    sections["investment_notebook"] = [item["entry"] for item in sections["investment_notebook"]]
    profile = prefs["investment_profile"] if prefs else None
    sections["investment_profile"] = _export_json(json.loads(profile) if isinstance(profile, str) else profile)
    truncated["investment_profile"] = False  # One document per user.
    sections["alert_triage_state"] = await section(
        "alert_triage_state", "SELECT alert_id, status, snooze_until, resolved_at, note, "
        "created_at, updated_at FROM alert_triage_state WHERE user_id=$1 ORDER BY alert_id LIMIT $2",
    )
    sections["brain_runs"] = []
    truncated["brain_runs"] = False
    sections["brain_runs_available"] = await pool.fetchval("SELECT to_regclass('brain_runs') IS NOT NULL")
    if sections["brain_runs_available"]:
        sections["brain_runs"] = await section(
            "brain_runs", """SELECT id, source, family_focus, requested_n, generated_n,
                screened_n, simulated_n, persisted_n, passed_n, flagged_n, rejected_n,
                sim_error_n, status, screen_status, seed, created_at, queued_at,
                started_at, completed_at, updated_at, generation_target_n, parent_run_id
                FROM brain_runs WHERE user_id=$1 ORDER BY id LIMIT $2""",
        )
    return jsonable_encoder({
        "schema_version": 2,
        "excluded": [
            "llm_credentials_encrypted", "brain_credentials", "authentication_material",
            "bot_run_context", "bot_run_config_snapshots", "bot_run_leases",
            "bot_run_diagnostics", "brain_run_diagnostic_details",
            "structured_data_redactions", "browser_local_factor_zoo",
        ],
        "truncated": truncated,
        **sections,
        "user": {
            "email": user["email"],
            "created_at": user["created_at"].isoformat(),
            "last_login_at": user["last_login_at"].isoformat()
            if user["last_login_at"] else None,
        },
        "preferences": {"locale": prefs["locale"], "theme": prefs["theme"]} if prefs else None,
        "watchlist": [w["ticker"] for w in watch[:limit]],
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
            for b in byok[:limit]
        ],
    })


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

    credential = await fetch_user_llm_credential(pool, user_id)
    if credential is None:
        raise HTTPException(404, "no LLM credential to restore")

    # Apply the rollback to the actual settings table. For now only
    # byok.* fields are rollback-safe; weight-override rollback wires in
    # at B9.1 when the weight UI ships.
    if field == "byok.provider":
        raise HTTPException(
            400, "Provider changes require saving the matching API key in Settings",
        )
    elif field == "byok.model":
        await pool.execute(
            "UPDATE user_byok SET model = $1 WHERE user_id = $2 AND provider = $3",
            target, user_id, credential["provider"],
        )
    elif field == "byok.base_url":
        await pool.execute(
            "UPDATE user_byok SET base_url = $1 WHERE user_id = $2 AND provider = $3",
            target, user_id, credential["provider"],
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
