import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from alpha_agent.api import dependencies
from alpha_agent.api.routes import cron_routes, paper_bot
from alpha_agent.scheduling import runner
from alpha_agent.scheduling.ticks import Unit

DAY = "2026-11-11"
NOW = datetime(2026, 11, 11, 22, 30, tzinfo=UTC)
HEADERS = {"Authorization": "Bearer test-tick-secret"}


@pytest.fixture
async def pool(applied_db):
    async with asyncpg.create_pool(applied_db, min_size=1, max_size=5) as value:
        yield value


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=NOW, elapsed=0)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.now

    async def pause(seconds):
        state.elapsed += seconds

    monkeypatch.setattr(runner, "datetime", Frozen)
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: state.elapsed))
    monkeypatch.setattr(runner, "asyncio", SimpleNamespace(timeout=asyncio.timeout, sleep=pause))
    monkeypatch.setattr(runner, "read_capacity", AsyncMock(return_value={"allow_writes": True}))
    monkeypatch.setattr(runner, "research_price_readiness", AsyncMock(return_value={
        "ready": True, "price_universe_count": 151}))
    return state


@pytest.fixture
async def api(pool, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-tick-secret")
    monkeypatch.setattr(dependencies, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(paper_bot, "get_db_pool", AsyncMock(return_value=pool))
    app = FastAPI()
    app.include_router(cron_routes.router)
    app.include_router(paper_bot.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def receipts(pool, job):
    rows = await pool.fetch("SELECT details FROM cron_runs WHERE cron_name=$1 ORDER BY id", f"tick_{job}")
    return [json.loads(r["details"]) for r in rows]


@pytest.mark.parametrize("path", ["tick/daily_close", "paper_bot/drive"])
async def test_tick_and_drive_auth_before_work(api, path, monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(runner, "execute_unit", execute)
    monkeypatch.setattr(paper_bot, "enqueue_due", execute)
    assert (await api.get(f"/api/cron/{path}")).status_code == 401
    assert execute.await_count == 0


async def test_tick_overlap_is_a_noop_and_lock_is_released(api, pool, clock, monkeypatch):
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(runner, "execute_unit", execute)
    async with pool.acquire() as other, other.transaction():
        # Another live tick holds the transaction-scoped lock.
        await other.execute("SELECT pg_advisory_xact_lock(hashtext('tick:daily_close'))")
        response = await api.get("/api/cron/tick/daily_close", headers=HEADERS)
        assert response.json() == {"ok": True, "skipped": "overlap"}
    execute.assert_not_awaited()
    assert not await receipts(pool, "daily_close")
    # A handler exception must also release the lock (transaction ends).
    execute.side_effect = ValueError("a secret provider payload that must not be logged")
    await api.get("/api/cron/tick/daily_close", headers=HEADERS)
    async with pool.acquire() as other, other.transaction():
        assert await other.fetchval("SELECT pg_try_advisory_xact_lock(hashtext('tick:daily_close'))")
    details = await receipts(pool, "daily_close")
    assert "secret provider payload" not in json.dumps(details)
    assert details[0]["error_type"] == "ValueError"
    # No session-level advisory lock is ever left behind (pgbouncer safety).
    assert not await pool.fetchval("SELECT count(*) FROM pg_locks WHERE locktype='advisory'")


async def test_capacity_pause_records_without_running_work(api, pool, clock, monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(runner, "execute_unit", execute)
    monkeypatch.setattr(runner, "read_capacity", AsyncMock(return_value={
        "allow_writes": False, "reason": "storage_headroom_low"}))
    response = await api.get("/api/cron/tick/daily_close", headers=HEADERS)
    assert response.json()["reason"] == "storage_headroom_low"
    execute.assert_not_awaited()
    assert (await receipts(pool, "daily_close"))[0]["unit"] is None


async def test_daily_chain_resumes_from_real_postgres_rows(api, pool, clock, monkeypatch):
    called = []

    async def execute(unit, **kwargs):
        called.append((unit.name, unit.offset))
        clock.elapsed += 180 if unit.name in ("ic_backtest_monthly", "fast_intraday") else 65
        if unit.name == "daily_prices":
            return {"updated": 75, "error_count": 2}  # per-ticker misses are not a unit failure
        return {"ok": unit.name != "publish_recommendation", "errors": [], "run_id": 42}

    monkeypatch.setattr(runner, "execute_unit", execute)
    for _ in range(14):
        clock.elapsed = 0
        result = (await api.get("/api/cron/tick/daily_close", headers=HEADERS)).json()
        if result["reason"] == "complete":
            break
    assert called == [("daily_prices", o) for o in (0, 75, 150)] + [
        ("ic_backtest_monthly", None)] + [
        ("fast_intraday", o) for o in range(0, 240, 40)] + [
        ("publish_recommendation", None), ("l2_cycle", None)]
    clock.elapsed = 0
    assert (await api.get("/api/cron/tick/daily_close", headers=HEADERS)).json()["units"] == []
    rows = [r for r in await receipts(pool, "daily_close") if r["unit"]]
    assert len(rows) == 12
    assert rows[0]["ok"] is True and rows[0]["handler_errors"] == 2
    assert rows[-2]["ok"] is False and rows[-1]["ok"] is True
    assert all(r["market_date"] == DAY and r["request_id"] and r["tick_id"] for r in rows)


async def test_failure_budget_stops_research_but_still_values_holdings(api, pool, clock, monkeypatch):
    calls = []

    async def execute(unit, **kwargs):
        calls.append(unit.name)
        if unit.name == "l2_cycle":
            return {"ok": True}
        raise TimeoutError("provider detail")

    monkeypatch.setattr(runner, "execute_unit", execute)
    for _ in range(6):
        clock.elapsed = 0
        result = (await api.get("/api/cron/tick/daily_close", headers=HEADERS)).json()
    assert calls == ["daily_prices"] * 3 + ["l2_cycle"]
    assert result["reason"] == "complete"
    assert "provider detail" not in json.dumps(await receipts(pool, "daily_close"))


async def test_slow_slot_does_not_restart_when_hour_changes(api, pool, clock, monkeypatch):
    called = []

    async def execute(unit, **kwargs):
        called.append((unit.name, unit.offset))
        clock.elapsed += 150
        return {"ok": True}

    monkeypatch.setattr(runner, "execute_unit", execute)
    for i in range(9):
        clock.elapsed = 0
        clock.now = NOW.replace(hour=13 if i < 6 else 14, minute=30 + i * 5 if i < 6 else (i - 6) * 5)
        await api.get("/api/cron/tick/slow_daily", headers=HEADERS)
    assert called == [("slow_daily", o) for o in range(0, 481, 80)] + [("compute_ic_annotations", None)]


async def test_news_two_units_with_workflow_pause_and_slot_dedup(api, clock, monkeypatch):
    clock.now = NOW.replace(hour=15, minute=0)

    async def execute(unit, **kwargs):
        clock.elapsed += 100
        return {"ok": True}

    execute_mock = AsyncMock(side_effect=execute)
    monkeypatch.setattr(runner, "execute_unit", execute_mock)
    result = (await api.get("/api/cron/tick/news_per_ticker", headers=HEADERS)).json()
    assert [u["offset"] for u in result["units"]] == [0, 75]
    assert clock.elapsed == 210
    clock.elapsed = 0
    assert (await api.get("/api/cron/tick/news_per_ticker", headers=HEADERS)).json()["units"] == []
    assert execute_mock.await_count == 2


@pytest.mark.parametrize("processed", [False, True])
async def test_drive_performs_exactly_one_step(api, monkeypatch, processed):
    enqueue = AsyncMock(return_value={"enqueued": 0})
    step = AsyncMock(return_value={"processed": processed})
    settle = AsyncMock(return_value={"filled": 0, "errors": ["private"]})
    monkeypatch.setattr(paper_bot, "enqueue_due", enqueue)
    monkeypatch.setattr(paper_bot, "step", step)
    monkeypatch.setattr("alpha_agent.paper.bot_execution.settle_orders", settle)
    result = (await api.get("/api/cron/paper_bot/drive", headers=HEADERS)).json()
    enqueue.assert_awaited_once()
    step.assert_awaited_once()
    assert settle.await_count == int(not processed)
    assert result["ok"] is True and result["processed"] is processed
    assert "errors" not in result["settlement"]


async def test_drive_with_no_claimable_lease_does_not_advance_or_call_model(api, monkeypatch):
    from alpha_agent.paper import bot_store
    monkeypatch.setattr(paper_bot, "enqueue_due", AsyncMock(return_value={"enqueued": 0}))
    claim = AsyncMock(return_value=None)
    monkeypatch.setattr(bot_store, "claim", claim)
    settle = AsyncMock(return_value={})
    monkeypatch.setattr("alpha_agent.paper.bot_execution.settle_orders", settle)
    result = (await api.get("/api/cron/paper_bot/drive", headers=HEADERS)).json()
    assert result["processed"] is False
    claim.assert_awaited_once()
    settle.assert_awaited_once()


@pytest.mark.parametrize("fallback,error", [(False, False), (True, False), (True, True)])
async def test_wake_dispatch_is_optional_and_nonfatal(api, pool, monkeypatch, fallback, error):
    monkeypatch.setenv("PAPER_BOT_GH_FALLBACK", "1" if fallback else "0")
    fake = SimpleNamespace(fetchval=AsyncMock(return_value=True), execute=AsyncMock())
    monkeypatch.setattr(paper_bot, "get_db_pool", AsyncMock(return_value=fake))
    monkeypatch.setattr(paper_bot, "enqueue_due", AsyncMock(return_value={"enqueued": 1}))
    dispatch = AsyncMock(side_effect=HTTPException(503, "private error") if error else None)
    monkeypatch.setattr(paper_bot, "dispatch_runner", dispatch)
    response = await api.get("/api/cron/paper_bot/wake", headers=HEADERS)
    assert response.status_code == 200
    assert dispatch.await_count == int(fallback)
    assert response.json()["dispatched"] is (fallback and not error)


@pytest.mark.parametrize("name,kwargs", [
    ("daily_prices", {"limit": 75, "offset": 75, "period": "5d"}),
    ("fast_intraday", {"limit": 40, "offset": 40, "tier": "full", "run_key": f"tick-{DAY}-40"}),
    ("fast_tech", {"limit": 40, "offset": 0, "tier": "tech", "run_key": f"tick-tech-{DAY}:15-request"}),
    ("slow_daily", {"limit": 80, "offset": 480}),
    ("compute_ic_annotations", {"window_days": 30}),
    ("publish_recommendation", {"request_id": "request"}),
    ("news_per_ticker", {"limit": 75, "offset": 75}),
    ("minute_bars", {"limit": 75, "offset": 0}),
    ("news_macro", {}), ("l2_cycle", {}), ("ic_backtest_monthly", {}),
])
async def test_executor_calls_existing_handlers_with_exact_scope(monkeypatch, name, kwargs):
    from alpha_agent.api.routes import ic_backtest
    attr = {"daily_prices": "cron_daily_prices", "fast_tech": "fast_intraday",
            "compute_ic_annotations": "cron_compute_ic_annotations", "news_per_ticker": "cron_news_per_ticker",
            "minute_bars": "cron_minute_bars", "news_macro": "cron_news_macro"}.get(name, name)
    handler = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(ic_backtest if name == "ic_backtest_monthly" else cron_routes, attr, handler)
    unit = Unit(name, offset=kwargs.get("offset"), limit=kwargs.get("limit"))
    assert await runner.execute_unit(unit, research_day=DAY, slot=f"{DAY}:15", request_id="request") == {"ok": True}
    handler.assert_awaited_once_with(**kwargs)
