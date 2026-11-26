from datetime import UTC, datetime
from unittest.mock import AsyncMock

import asyncpg
import pytest
from fastapi import HTTPException

from alpha_agent.scheduling import dispatch

NOW = datetime(2026, 11, 12, 11, 30, tzinfo=UTC)
pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool(applied_db, monkeypatch):
    monkeypatch.setattr(dispatch, "read_capacity", AsyncMock(return_value={"allow_writes": True}))
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as value:
        yield value


async def test_dispatch_once_per_day_with_scheduled_inputs(pool, monkeypatch):
    monkeypatch.setenv("GH_PAT", "token")
    post = AsyncMock(return_value=204)
    first = await dispatch.dispatch_workflow(pool, "brain-backfill-selfcorr", now=NOW, post=post)
    second = await dispatch.dispatch_workflow(pool, "brain-backfill-selfcorr", now=NOW, post=post)
    assert first["status"] == "dispatched" and first["ok"] is True
    assert second == {"ok": True, "workflow": "brain-backfill-selfcorr",
                      "skipped": "already_dispatched_today"}
    post.assert_awaited_once_with("brain-backfill-selfcorr", {"ref": "main", "inputs": {"limit": "30"}})


async def test_failed_dispatch_is_recorded_and_not_retried_the_same_day(pool, monkeypatch):
    monkeypatch.setenv("GH_PAT", "token")
    post = AsyncMock(return_value=422)
    result = await dispatch.dispatch_workflow(pool, "earnings-finnhub", now=NOW, post=post)
    assert result["ok"] is False and result["http_status"] == 422
    again = await dispatch.dispatch_workflow(pool, "earnings-finnhub", now=NOW, post=post)
    assert again["skipped"] == "already_dispatched_today"
    assert post.await_count == 1


async def test_missing_token_and_unknown_workflow(pool, monkeypatch):
    monkeypatch.delenv("GH_PAT", raising=False)
    result = await dispatch.dispatch_workflow(pool, "insider-form4", now=NOW, post=AsyncMock())
    assert result["reason"] == "gh_pat_missing"
    with pytest.raises(HTTPException):
        await dispatch.dispatch_workflow(pool, "daily-factor-loop", now=NOW)


async def test_dispatch_claim_committed_before_remote_call(pool, monkeypatch):
    import asyncio

    monkeypatch.setenv("GH_PAT", "fixture")
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def post(workflow, payload):
        calls.append(workflow)
        if len(calls) == 1:
            started.set()
            await release.wait()
        return 204

    first = asyncio.create_task(dispatch.dispatch_workflow(pool, "insider-form4", now=NOW, post=post))
    try:
        await asyncio.wait_for(started.wait(), 3)
        second = await asyncio.wait_for(
            dispatch.dispatch_workflow(pool, "insider-form4", now=NOW, post=post), 3,
        )
    finally:
        release.set()
        result = await first
    assert calls == ["insider-form4"]
    assert result["ok"] and second["skipped"] == "already_dispatched_today"
    assert await pool.fetchval("SELECT count(*) FROM cron_runs WHERE cron_name='dispatch_insider-form4'") == 1


async def test_ambiguous_transport_outcome_never_dispatches_again(pool, monkeypatch):
    import httpx

    monkeypatch.setenv("GH_PAT", "fixture")
    post = AsyncMock(side_effect=httpx.ReadTimeout("fixture"))
    first = await dispatch.dispatch_workflow(pool, "insider-form4", now=NOW, post=post)
    again = await dispatch.dispatch_workflow(pool, "insider-form4", now=NOW, post=post)
    assert first["status"] == "unconfirmed" and not first["ok"]
    assert again["skipped"] == "already_dispatched_today"
    post.assert_awaited_once()
