"""Request-bound tick executor; the planner itself has no database dependencies."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime

from alpha_agent.data.capacity import read_capacity
from alpha_agent.data.research_refresh import research_price_readiness
from alpha_agent.market_session import latest_completed_xnys_session, xnys_close
from alpha_agent.scheduling.ticks import (
    BUDGET_SECONDS,
    Job,
    Unit,
    next_unit,
    scheduled_slot,
    within_research_day,
)


async def execute_unit(unit: Unit, *, research_day: str, slot: str, request_id: str) -> dict:
    """Call existing route functions, retaining their own cron_names and gates."""
    from alpha_agent.api.routes import cron_routes as routes
    from alpha_agent.api.routes.ic_backtest import ic_backtest_monthly

    if unit.name == "daily_prices":
        return await routes.cron_daily_prices(limit=unit.limit, offset=unit.offset, period="5d")
    if unit.name in ("fast_intraday", "fast_tech"):
        return await routes.fast_intraday(
            limit=unit.limit, offset=unit.offset,
            tier="full" if unit.name == "fast_intraday" else "tech",
            run_key=f"tick-{research_day}-{unit.offset}" if unit.name == "fast_intraday"
            else f"tick-tech-{slot}-{request_id}",
        )
    if unit.name == "slow_daily":
        return await routes.slow_daily(limit=unit.limit, offset=unit.offset)
    if unit.name == "news_per_ticker":
        return await routes.cron_news_per_ticker(limit=unit.limit, offset=unit.offset)
    if unit.name == "minute_bars":
        return await routes.cron_minute_bars(limit=unit.limit, offset=unit.offset)
    if unit.name == "compute_ic_annotations":
        return await routes.cron_compute_ic_annotations(window_days=30)
    if unit.name == "publish_recommendation":
        return await routes.publish_recommendation(request_id=request_id)
    if unit.name == "ic_backtest_monthly":
        return await ic_backtest_monthly()
    if unit.name == "news_macro":
        return await routes.cron_news_macro()
    if unit.name == "l2_cycle":
        return await routes.l2_cycle()
    raise ValueError("Unknown tick unit")


async def _insert(conn, job, details, *, finished=True):
    return await conn.fetchval(
        "INSERT INTO cron_runs (cron_name,started_at,finished_at,ok,error_count,details) "
        "VALUES ($1,$2,CASE WHEN $3 THEN now() ELSE NULL END,$4,$5,$6::jsonb) RETURNING id",
        f"tick_{job}", datetime.now(UTC), finished, details["ok"], int(not details["ok"]), json.dumps(details),
    )


def _unit_outcome(unit: Unit, result: dict) -> tuple[bool, str | None, int]:
    """Match the old workflow: a unit fails on an exception or an explicit
    rejection, not on per-ticker provider errors. Those are counted, and the
    readiness and publication gates still judge actual coverage."""
    errors = result.get("error_count")
    if not isinstance(errors, int):
        errors = len(result.get("errors") or [])
    # An existing handler's overlap response is NOT proof that its shard ran.
    if result.get("skipped") and result.get("reason") != "no_op_same_market_date":
        return False, "UnitSkipped", errors
    ok = result.get("ok") is True or (unit.name == "daily_prices" and "updated" in result)
    return ok, None if ok else "HandlerRejected", errors


async def run_tick(job: Job, pool) -> dict:
    started = time.monotonic()
    now = datetime.now(UTC)
    # Neon's pooler runs pgbouncer in transaction mode, where a session
    # advisory lock can stay pinned to a server connection and block later
    # ticks. Hold a transaction-scoped lock on one dedicated connection; it
    # is released on commit, rollback or a killed function. Receipts are
    # written through the pool so each one commits immediately.
    async with pool.acquire() as lock_conn, lock_conn.transaction():
        if not await lock_conn.fetchval("SELECT pg_try_advisory_xact_lock(hashtext($1))", f"tick:{job}"):
            return {"ok": True, "skipped": "overlap"}
        return await _run_locked(job, pool, started=started, now=now)


async def _run_locked(job: Job, pool, *, started: float, now: datetime) -> dict:
    day = now.date().isoformat()
    slot = scheduled_slot(job, now)
    market_date = latest_completed_xnys_session(now)
    tick_id = str(uuid.uuid4())
    base = {"research_day": day, "market_date": market_date.isoformat(), "slot": slot,
            "tick_id": tick_id, "request_id": tick_id, "unit": None, "offset": None,
            "ok": True, "error_type": None}

    async def stop(reason, units):
        await _insert(pool, job, {**base, "reason": reason})
        return {"ok": True, "reason": reason, "research_day": day,
                "market_date": market_date.isoformat(), "units": units}

    capacity = await read_capacity(pool)
    if not capacity["allow_writes"]:
        return await stop(capacity["reason"], [])
    if slot is None:
        return await stop("outside_scheduled_slot", [])
    records = await pool.fetch(
        "SELECT details FROM cron_runs WHERE cron_name=$1 "
        "AND started_at >= $2 AND details->>'research_day'=$3 ORDER BY id",
        f"tick_{job}", datetime.combine(now.date(), datetime.min.time(), UTC), day,
    )
    receipts = [json.loads(r["details"]) if isinstance(r["details"], str)
                else dict(r["details"]) for r in records]
    executed, cooldown = [], 0
    while True:
        instant = datetime.now(UTC)
        if scheduled_slot(job, instant) != slot:
            return await stop("scheduled_slot_ended", executed)
        # Recheck the real coverage before each stage, including publish.
        readiness = await research_price_readiness(pool, now=instant) if job == "daily_close" else {}
        plan = next_unit(
            job, now=instant, research_day=day, slot=slot, receipts=receipts,
            market_close=xnys_close(market_date), ready=readiness.get("ready") is True,
            price_universe_count=readiness.get("price_universe_count", 0),
        )
        if plan.unit is None:
            return await stop(plan.reason, executed)
        unit = plan.unit
        if time.monotonic() - started + cooldown + unit.estimate >= BUDGET_SECONDS:
            return await stop("time_budget", executed)
        if cooldown:
            await asyncio.sleep(cooldown)
        # Same UTC guard is re-evaluated after the pause, before work.
        if job == "daily_close" and not within_research_day(day, datetime.now(UTC)):
            return await stop("research_day_window_ended", executed)
        capacity = await read_capacity(pool)
        if not capacity["allow_writes"]:
            return await stop(capacity["reason"], executed)
        details = {**base, "unit": unit.name, "offset": unit.offset,
                   "price_pass": unit.price_pass, "ok": False,
                   "error_type": "UnitInterrupted",
                   "observed_at": datetime.now(UTC).isoformat()}
        # Reserve one durable receipt before I/O. A killed request counts as a
        # failed attempt on the next tick, rather than retrying forever.
        row_id = await _insert(pool, job, details, finished=False)
        try:
            async with asyncio.timeout(max(0, BUDGET_SECONDS - (time.monotonic() - started))):
                result = await execute_unit(unit, research_day=day, slot=slot, request_id=tick_id)
            details["ok"], details["error_type"], details["handler_errors"] = _unit_outcome(unit, result)
            # Only known scalar correlation IDs, no arbitrary provider payloads.
            if isinstance(result.get("run_id"), (str, int)):
                details["run_id"] = result["run_id"]
        except Exception as exc:  # noqa: BLE001 - recorded as a failed unit
            details["error_type"] = type(exc).__name__
        await pool.execute(
            "UPDATE cron_runs SET finished_at=now(),ok=$2,error_count=$3,details=$4::jsonb WHERE id=$1",
            row_id, details["ok"], int(not details["ok"]), json.dumps(details),
        )
        receipts.append(details)
        executed.append({"unit": unit.name, "offset": unit.offset, "ok": details["ok"],
                         "error_type": details["error_type"], "request_id": tick_id})
        if not details["ok"] and unit.name != "publish_recommendation":
            # No in-tick retry. The next tick decides (L2 still runs once the
            # daily budget is spent).
            return await stop("unit_failed", executed)
        cooldown = unit.cooldown
