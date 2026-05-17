"""Test POST /api/cron/ic_backtest_monthly route.

Verifies the route is registered and returns the expected JSON envelope
when run_monthly_ic_backtest succeeds. Mocks both the engine and the DB
pool so the test is hermetic (no Postgres dependency).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from alpha_agent.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_ic_backtest_endpoint_returns_count(app):
    """POST /api/cron/ic_backtest_monthly should invoke the engine and return
    a JSON envelope with 'signals_updated' count."""
    async def fake_run(pool):
        return 11

    fake_pool = AsyncMock()
    fake_pool.execute = AsyncMock(return_value=None)

    with patch(
        "alpha_agent.api.routes.ic_backtest.run_monthly_ic_backtest",
        new=fake_run,
    ), patch(
        "alpha_agent.api.routes.ic_backtest.get_db_pool",
        new=AsyncMock(return_value=fake_pool),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/cron/ic_backtest_monthly")

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["signals_updated"] == 11
