"""Credential settings over independent local PostgreSQL connections."""
import asyncio
import base64
import json
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from alpha_agent.api.routes import user
from alpha_agent.auth.crypto_box import decrypt
from alpha_agent.llm.base import LLMResponse

MASTER = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


class CleanupBarrierPool:
    """Force both legacy pool-level saves to finish their upserts before cleanup."""

    def __init__(self, pool):
        self.pool = pool
        self.cleanups = 0
        self.ready = asyncio.Event()

    def __getattr__(self, name):
        return getattr(self.pool, name)

    async def execute(self, query, *args):
        if "provider <> $3" in query:
            self.cleanups += 1
            if self.cleanups == 2:
                self.ready.set()
            await asyncio.wait_for(self.ready.wait(), 3)
        return await self.pool.execute(query, *args)


@pytest.fixture
async def settings(applied_db, monkeypatch):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=6)
    try:
        uid = await pool.fetchval("INSERT INTO users(email) VALUES('settings@example.test') RETURNING id")
        current = CleanupBarrierPool(pool)

        async def get_pool():
            return current if getattr(current, "enabled", False) else pool

        monkeypatch.setattr(user, "get_db_pool", get_pool)
        monkeypatch.setenv("BYOK_MASTER_KEY", MASTER)
        app = FastAPI()
        app.include_router(user.router)
        app.dependency_overrides[user.require_user] = lambda: uid
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://settings.test",
        ) as client:
            client.cleanup_barrier = current
            yield client, pool, uid
    finally:
        await pool.close()


async def save(client, provider="openai", model="alpha", key="synthetic-key-1234", **extra):
    return await client.post("/api/user/byok", json={
        "provider": provider, "api_key": key, "model": model, **extra,
    })


async def test_two_provider_saves_leave_one_complete_credential(settings):
    client, pool, uid = settings
    client.cleanup_barrier.enabled = True
    bot_id = await pool.fetchval("INSERT INTO sim_account(user_id, kind) VALUES ($1, 'bot') RETURNING id", uid)
    await pool.execute(
        "INSERT INTO sim_bot_credential(account_id, provider, ciphertext, nonce, last4) "
        "VALUES ($1, 'openai', $2, $3, 'bott')", bot_id, b"bot", b"nonce",
    )
    await pool.execute(
        "INSERT INTO user_byok(user_id, provider, ciphertext, nonce, last4) "
        "VALUES ($1, 'worldquant_brain', $2, $3, 'brn1')", uid, b"brain", b"nonce",
    )
    first, second = await asyncio.gather(
        save(client, "openai", "alpha"), save(client, "anthropic", "beta", "synthetic-key-5678"),
    )
    assert first.status_code == second.status_code == 200
    rows = await pool.fetch(
        "SELECT provider, model, last4, encrypted_at, ciphertext, nonce FROM user_byok "
        "WHERE user_id=$1 AND provider <> 'worldquant_brain'", uid,
    )
    assert len(rows) == 1
    row = rows[0]
    final = first if row["provider"] == "openai" else second
    assert (row["provider"], row["model"], row["last4"]) in [
        ("openai", "alpha", "1234"), ("anthropic", "beta", "5678"),
    ]
    assert decrypt(row["ciphertext"], row["nonce"], MASTER.encode()) == f"synthetic-key-{row['last4']}"
    assert final.json()["encrypted_at"] == row["encrypted_at"].isoformat()
    assert final.headers["X-BYOK-Revision"] == final.json()["encrypted_at"]
    assert final.headers["X-BYOK-Account"] == str(uid)
    assert (await client.delete("/api/user/byok")).status_code == 204
    assert await pool.fetchval("SELECT ciphertext FROM user_byok WHERE provider='worldquant_brain'") == b"brain"
    assert await pool.fetchval("SELECT ciphertext FROM sim_bot_credential WHERE account_id=$1", bot_id) == b"bot"
    assert (await client.get("/api/user/byok")).status_code == 404


async def test_rollback_from_former_provider_does_not_overwrite_current_one(settings):
    client, pool, uid = settings
    # This legacy row predates verifiable version evidence.
    await pool.execute(
        "INSERT INTO user_byok(user_id, provider, ciphertext, nonce, last4, model) "
        "VALUES ($1, 'anthropic', $2, $3, '1234', 'beta')",
        uid, b"synthetic", b"nonce",
    )
    change_id = await pool.fetchval(
        "INSERT INTO config_change_log(user_id, field, old_value, new_value, source) "
        "VALUES ($1, 'byok.model', 'former-openai', 'another-openai', 'manual') RETURNING id",
        uid,
    )
    result = await client.post(f"/api/user/settings/rollback/{change_id}")
    assert result.status_code == 409
    assert (await client.get("/api/user/byok")).json()["model"] == "beta"


async def history(client):
    response = await client.get("/api/user/settings/history")
    assert response.status_code == 200
    return response.json()["changes"]


async def test_same_provider_rollback_checks_current_value_and_can_only_happen_once(settings):
    client, pool, uid = settings
    assert (await save(client)).status_code == 200
    saved = await save(client, model="new-model")
    current = next(row for row in await history(client) if row["field"] == "byok.model")
    assert current["rollback_status"] == "available"
    binding = await pool.fetchval("SELECT evidence FROM config_change_log WHERE id=$1", current["id"])
    assert json.loads(binding) == {"byok": {
        "provider": "openai", "old_provider": "openai", "encrypted_at": saved.json()["encrypted_at"],
    }}
    await pool.execute("UPDATE user_byok SET model='out-of-band' WHERE user_id=$1", uid)
    url = f"/api/user/settings/rollback/{current['id']}"
    assert (await client.post(url)).status_code == 409
    assert (await history(client))[0]["rollback_status"] == "value_changed"
    await pool.execute("UPDATE user_byok SET model='new-model' WHERE user_id=$1", uid)

    responses = await asyncio.gather(client.post(url), client.post(url))
    assert sorted(result.status_code for result in responses) == [200, 409]
    revision = (await client.get("/api/user/byok")).json()
    assert revision["model"] == "alpha"
    assert revision["encrypted_at"] != saved.json()["encrypted_at"]
    changes = await history(client)
    assert changes[0]["rollback_of"] == current["id"]
    assert changes[0]["rollback_status"] == "read_only"
    assert (changes[0]["old_value"], changes[0]["new_value"]) == ("new-model", "alpha")
    assert changes[1]["rollback_status"] == "already_rolled_back"


async def test_rotation_and_provider_switch_expire_bound_rollback(settings):
    client, _, _ = settings
    await save(client)
    await save(client, model="middle-model")
    middle = (await history(client))[0]
    rotated = await save(client, model="middle-model", key="new-key-same-1234")
    assert rotated.status_code == 200
    assert (await history(client))[0]["rollback_status"] == "stale_revision"
    assert (await client.post(f"/api/user/settings/rollback/{middle['id']}")).status_code == 409

    await save(client, provider="anthropic", model="last-model")
    changes = await history(client)
    switched = next(row for row in changes if row["field"] == "byok.model")
    assert (switched["old_provider"], switched["provider"], switched["rollback_status"]) == (
        "openai", "anthropic", "different_provider",
    )
    assert (await client.post(f"/api/user/settings/rollback/{switched['id']}")).status_code == 409
    assert (await client.post(f"/api/user/settings/rollback/{middle['id']}")).status_code == 409
    assert (await client.get("/api/user/byok")).json()["model"] == "last-model"


async def test_same_provider_endpoint_can_be_restored(settings):
    client, _, _ = settings
    await save(client, base_url="https://example.test/compatible/v1")
    await save(client, base_url="https://example.test/other/v1")
    change = (await history(client))[0]
    assert change["field"] == "byok.base_url"
    assert change["rollback_status"] == "available"
    response = await client.post(f"/api/user/settings/rollback/{change['id']}")
    assert response.status_code == 200
    assert (await client.get("/api/user/byok")).json()["base_url"] == "https://example.test/compatible/v1"


@pytest.mark.parametrize("url", [
    "https://name:synthetic-password@example.test/v1",
    "https://example.test/v1?api_key=synthetic-query",
    "https://example.test/v1#synthetic-fragment",
    "https://example.test/synthetic%2Dkey%2D1234/v1",
])
async def test_urls_with_embedded_credentials_are_not_saved(settings, url):
    client, _, _ = settings
    assert (await save(client, base_url=url)).status_code == 422
    assert (await client.get("/api/user/byok")).status_code == 404
    assert await history(client) == []


async def test_legacy_secret_url_is_redacted_in_history_and_not_copied(settings):
    client, pool, uid = settings
    secret_url = "https://name:historical-secret@example.test/v1"
    await pool.execute("""
        INSERT INTO user_byok(user_id, provider, ciphertext, nonce, last4, base_url)
        VALUES ($1, 'openai', $2, $3, '1234', $4)
    """, uid, b"synthetic", b"nonce", secret_url)
    await pool.execute("""
        INSERT INTO config_change_log(user_id, field, old_value, new_value, source)
        VALUES ($1, 'byok.base_url', NULL, $2, 'manual')
    """, uid, secret_url)
    await save(client, base_url="https://example.test/v1")
    changes = await history(client)
    assert secret_url not in json.dumps(changes)
    assert all(row["rollback_status"] == "unverified"
               for row in changes if row["field"] == "byok.base_url")
    assert await pool.fetchval("SELECT count(*) FROM config_change_log WHERE old_value=$1 OR new_value=$1",
                               secret_url) == 1


def scope_headers(response):
    return {name: response.headers[name] for name in (
        "X-BYOK-Account", "X-BYOK-Provider", "X-BYOK-Revision",
    )}


async def test_probe_preserves_body_and_binds_success_to_database_revision(settings, monkeypatch):
    client, pool, uid = settings
    saved = await save(client)
    fake = AsyncMock()
    fake.chat.return_value = LLMResponse("OK", "stub-model", 7, 1)
    calls = []

    def build(row):
        calls.append(row["encrypted_at"].isoformat())
        return fake

    monkeypatch.setattr(user, "llm_client_from_credential", build)
    for headers in ({}, scope_headers(saved)):
        response = await client.post("/api/user/byok/test", headers=headers)
        assert response.status_code == 200
        assert set(response.json()) == {"provider", "model", "latency_ms", "prompt_tokens", "completion_tokens"}
        assert response.json()["model"] == "stub-model"
        assert scope_headers(response) == scope_headers(saved)
    assert calls == [saved.json()["encrypted_at"]] * 2
    assert fake.close.await_count == 2
    assert await pool.fetchval("SELECT last_used_at FROM user_byok WHERE user_id=$1", uid) is not None

    stale = await client.post("/api/user/byok/test", headers={**scope_headers(saved), "X-BYOK-Account": "0"})
    assert stale.status_code == 409
    assert fake.chat.await_count == 2


async def test_late_probe_cannot_mark_rotated_credential_as_used(settings, monkeypatch):
    client, pool, uid = settings
    saved = await save(client)
    testing = asyncio.Event()
    release = asyncio.Event()

    async def chat(*args, **kwargs):
        testing.set()
        await release.wait()
        return LLMResponse("OK", "stub-model", 7, 1)

    fake = AsyncMock()
    fake.chat.side_effect = chat
    monkeypatch.setattr(user, "llm_client_from_credential", lambda row: fake)
    task = asyncio.create_task(client.post("/api/user/byok/test", headers=scope_headers(saved)))
    try:
        await asyncio.wait_for(testing.wait(), 3)
        rotated = await save(client, key="another-key-1234")
        assert rotated.json()["encrypted_at"] != saved.json()["encrypted_at"]
    finally:
        release.set()
    result = await asyncio.wait_for(task, 3)
    assert result.status_code == 409
    assert result.headers.get("X-BYOK-Revision") is None
    assert await pool.fetchval("SELECT last_used_at FROM user_byok WHERE user_id=$1", uid) is None
    assert (await client.post("/api/user/byok/test", headers=scope_headers(saved))).status_code == 409
    assert fake.chat.await_count == 1


async def test_save_and_delete_wait_for_the_same_stable_user_lock(settings):
    client, pool, uid = settings
    tasks = []

    async def wait_for_lock_count(count):
        async with asyncio.timeout(3):
            while await pool.fetchval("""
                SELECT count(*) FROM pg_stat_activity
                WHERE datname = current_database() AND wait_event_type = 'Lock'
                  AND query LIKE 'SELECT id FROM users WHERE id = % FOR UPDATE'
            """) < count:
                await asyncio.sleep(0.01)

    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", uid)
            tasks.append(asyncio.create_task(save(client)))
            await wait_for_lock_count(1)
            tasks.append(asyncio.create_task(client.delete("/api/user/byok")))
            await wait_for_lock_count(2)
    finally:
        results = await asyncio.wait_for(asyncio.gather(*tasks), 3)
    assert [response.status_code for response in results] == [200, 204]
    assert (await client.get("/api/user/byok")).status_code == 404


async def test_journal_failure_rolls_back_the_credential_write(settings, monkeypatch):
    client, _, _ = settings
    saved = await save(client)
    original_history = await history(client)
    monkeypatch.setattr(user, "record_change", AsyncMock(side_effect=RuntimeError("synthetic journal failure")))
    with pytest.raises(RuntimeError, match="synthetic journal failure"):
        await save(client, provider="anthropic", model="never-committed")
    current = await client.get("/api/user/byok")
    assert current.json()["provider"] == "openai"
    assert current.json()["encrypted_at"] == saved.json()["encrypted_at"]
    assert await history(client) == original_history


async def test_failed_probe_exposes_only_its_revision_and_safe_error(settings, monkeypatch):
    client, _, _ = settings
    saved = await save(client)
    fake = AsyncMock()
    fake.chat.side_effect = RuntimeError("synthetic provider detail")
    monkeypatch.setattr(user, "llm_client_from_credential", lambda row: fake)
    failed = await client.post("/api/user/byok/test", headers=scope_headers(saved))
    assert failed.status_code == 502
    assert scope_headers(failed) == scope_headers(saved)
    assert failed.json() == {"detail": "LLM request failed (RuntimeError)"}
    assert (await client.get("/api/user/byok")).json()["last_used_at"] is None


async def test_ollama_placeholder_key_allows_a_local_ollama_endpoint(settings):
    client, _, _ = settings
    endpoint = "http://ollama.example.test:11434"
    assert (await save(client, provider="ollama", key="ollama", base_url=endpoint)).status_code == 200
    assert (await client.get("/api/user/byok")).json()["base_url"] == endpoint
