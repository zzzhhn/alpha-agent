import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.db_pool import APIConnectionPool
from alpha_agent.api.performance import PerformanceMiddleware
from alpha_agent.storage.postgres import DBUnavailable


@pytest.mark.asyncio
async def test_acquire_timeout_and_command_timeout_are_separate():
    raw = AsyncMock()
    raw.acquire.side_effect = TimeoutError()
    pool = APIConnectionPool(raw)
    with pytest.raises(DBUnavailable):
        await pool.fetch("SELECT 1")
    raw.acquire.assert_awaited_once_with(timeout=10)
    raw.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_releases_connection_and_does_not_retry_write():
    conn = AsyncMock()
    conn.execute.side_effect = asyncio.CancelledError()
    raw = AsyncMock()
    raw.acquire.return_value = conn
    pool = APIConnectionPool(raw)
    with pytest.raises(asyncio.CancelledError):
        await pool.execute("UPDATE sample SET n=1", timeout=45)
    conn.execute.assert_awaited_once_with("UPDATE sample SET n=1", timeout=45)
    raw.release.assert_awaited_once_with(conn)


def test_timing_headers_without_sql_or_parameters():
    app = FastAPI()
    app.add_middleware(PerformanceMiddleware)

    @app.get("/sample/{ticker}")
    async def endpoint(ticker: str):
        raw = AsyncMock()
        raw.acquire.return_value.fetchval.return_value = 1
        return {"value": await APIConnectionPool(raw).fetchval("SELECT $1", ticker)}

    response = TestClient(app).get("/sample/PRIVATE?token=SECRET")
    assert response.json() == {"value": 1}
    assert "db_query;dur=" in response.headers["server-timing"]
    assert "PRIVATE" not in response.headers["server-timing"]
    assert "SECRET" not in response.headers["server-timing"]
