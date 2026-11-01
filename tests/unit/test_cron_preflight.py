from unittest.mock import AsyncMock
from urllib.error import HTTPError

import pytest

from alpha_agent.data.capacity import read_capacity, storage_admission
from scripts.cron_preflight import check, finish


def test_capacity_keeps_headroom():
    assert storage_admission(200 * 1024**2, 512)["allow_writes"] is True
    assert storage_admission(410 * 1024**2, 512)["allow_writes"] is False
    with pytest.raises(ValueError):
        storage_admission(10, 0)


async def test_capacity_is_bounded_read_only():
    pool = AsyncMock()
    pool.fetchval.return_value = 246939648
    result = await read_capacity(pool)
    assert result["allow_writes"] is True
    pool.fetchval.assert_awaited_once_with("SELECT pg_database_size(current_database())", timeout=5)
    pool.execute.assert_not_called()


@pytest.mark.parametrize("status,expected_pause", [(402, True), (429, True), (503, True), (401, False), (404, False), (500, False)])
def test_preflight_does_not_mask_auth_or_code_errors(monkeypatch, status, expected_pause):
    def request(*args, **kwargs):
        raise HTTPError("https://example.test", status, "error", {}, None)
    monkeypatch.setattr("scripts.cron_preflight.urlopen", request)
    result = check("https://example.test", "not-a-real-secret")
    assert result["ready"] is False
    assert result["expected_pause"] is expected_pause
    assert finish(result, scheduled=True) == (0 if expected_pause else 1)
    assert finish(result, scheduled=False) == 1


def test_success_and_storage_pause(monkeypatch):
    from unittest.mock import MagicMock
    response = MagicMock()
    response.__enter__.return_value = response
    monkeypatch.setattr("scripts.cron_preflight.urlopen", lambda *a, **kw: response)
    response.read.return_value = b'{"ok":true,"allow_writes":true,"database_bytes":100,"budget_bytes":200}'
    assert check("https://example.test", "secret")["ready"] is True
    response.read.return_value = b'{"ok":true,"allow_writes":false,"reason":"storage_headroom_low"}'
    assert check("https://example.test", "secret")["expected_pause"] is True
    response.read.return_value = b'{"ok":true}'
    assert check("https://example.test", "secret")["expected_pause"] is False


async def test_authenticated_preflight_has_no_writes(monkeypatch):
    import json
    from pathlib import Path

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from alpha_agent.api.routes.cron_routes import router

    pool = AsyncMock()
    pool.fetchval.return_value = 200 * 1024**2
    monkeypatch.setattr("alpha_agent.api.dependencies.get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setenv("CRON_SECRET", "not-a-real-secret")
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/cron/preflight")).status_code == 401
        pool.fetchval.assert_not_called()
        response = await client.get(
            "/api/cron/preflight", headers={"Authorization": "Bearer not-a-real-secret"},
        )
    assert response.status_code == 200
    assert response.json()["allow_writes"] is True
    pool.execute.assert_not_called()
    snapshot = json.loads((Path(__file__).parents[2] / "openapi.snapshot.json").read_text())
    assert app.openapi()["paths"]["/api/cron/preflight"] == snapshot["paths"]["/api/cron/preflight"]
