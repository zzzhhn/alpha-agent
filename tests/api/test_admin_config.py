"""Tests for GET/POST /api/admin/config (Phase 2-pre Task 5)."""
from __future__ import annotations

import json
import time

import asyncpg
import pytest
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    tok = jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    """client_with_db with NEXTAUTH_SECRET wired so require_user passes."""
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


async def test_post_config_sets_and_journals(authed_client, applied_db):
    r = authed_client.post(
        "/api/admin/config",
        json={"key": "rating.no_trade_band", "value": 0.2},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    conn = await asyncpg.connect(applied_db)
    try:
        v = await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='rating.no_trade_band'"
        )
        assert json.loads(v) == pytest.approx(0.2)
        n = await conn.fetchval(
            "SELECT count(*) FROM config_change_log"
            " WHERE field='rating.no_trade_band' AND source='manual'"
        )
        assert n >= 1
    finally:
        await conn.close()


async def test_get_config_lists_rows(authed_client, applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO engine_config (key, value, updated_by)"
            " VALUES ('factor.mode', '\"long\"'::jsonb, 0)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        )
    finally:
        await conn.close()
    body = authed_client.get("/api/admin/config").json()
    assert any(
        row["key"] == "factor.mode" and row["value"] == "long"
        for row in body["config"]
    )


async def test_post_config_rejects_unknown_key(authed_client):
    r = authed_client.post(
        "/api/admin/config",
        json={"key": "not.a.real.knob", "value": 1},
        headers=_auth(),
    )
    assert r.status_code == 400


async def test_post_config_requires_auth(authed_client):
    r = authed_client.post(
        "/api/admin/config",
        json={"key": "rating.no_trade_band", "value": 0.1},
    )
    assert r.status_code == 401
