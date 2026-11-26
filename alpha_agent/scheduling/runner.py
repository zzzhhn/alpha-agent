"""Request-bound tick executor; the planner itself has no database dependencies."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from asyncio import shield as _shield
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from alpha_agent.data.capacity import read_capacity
from alpha_agent.data.research_refresh import research_price_readiness
from alpha_agent.market_session import latest_completed_xnys_session, xnys_close
from alpha_agent.scheduling.ticks import (
    BUDGET_SECONDS,
    PRICE_SLICE,
    Job,
    Unit,
    next_unit,
    scheduled_slot,
    within_research_day,
)

# Vercel Python functions have a 300s hard ceiling (BUDGET_SECONDS=240s leaves
# shutdown margin). A 330s lease outlives any still-running invocation so a
# successor never overlaps live work while recovering within ~5.5m of a kill.
VERCEL_MAX_DURATION_SECONDS = 300
LEASE_TTL = timedelta(seconds=VERCEL_MAX_DURATION_SECONDS + 30)
_ACTIVE_LEASE_SQL = (
    "job=$1 AND owner_token=$2 AND lease_until > clock_timestamp()"
)


@dataclass(frozen=True)
class JobLease:
    job: Job
    owner_token: uuid.UUID

    async def is_active(self, pool) -> bool:
        return bool(await pool.fetchval(
            f"SELECT true FROM scheduler_job_lease WHERE {_ACTIVE_LEASE_SQL}",
            self.job, self.owner_token,
        ))

    async def release(self, pool) -> bool:
        return bool(await pool.fetchval(
            "UPDATE scheduler_job_lease "
            "SET owner_token=NULL, leased_at=NULL, lease_until=NULL, updated_at=clock_timestamp() "
            "WHERE job=$1 AND owner_token=$2 RETURNING true",
            self.job, self.owner_token,
        ))


async def claim_job_lease(job: Job, pool) -> JobLease | None:
    """Claim a durable per-job lease in one short transaction without holding a
    pool connection across unit execution.

    Migration note: probing `pg_try_advisory_xact_lock(hashtext('tick:<job>'))`
    inside this short claim transaction only blocks a new worker when a legacy
    (pre-V066) worker is already holding the transaction-scoped advisory lock.
    Once this transaction commits, the advisory lock is released; legacy code
    does not read `scheduler_job_lease`, so if a new worker claims first and
    any instance is still receiving legacy traffic, that legacy worker can
    still acquire the advisory lock and overlap. Rollout must therefore stop
    dispatching to / drain pre-V066 instances rather than relying on
    bidirectional mixed-version exclusion.
    """
    owner = uuid.uuid4()
    async with pool.acquire() as conn, conn.transaction():
        if not await conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtext($1))", f"tick:{job}",
        ):
            return None
        claimed = await conn.fetchval(
            "INSERT INTO scheduler_job_lease (job, owner_token, leased_at, lease_until, updated_at) "
            "VALUES ($1, $2, clock_timestamp(), clock_timestamp() + $3::interval, clock_timestamp()) "
            "ON CONFLICT (job) DO UPDATE SET "
            "owner_token = EXCLUDED.owner_token, "
            "leased_at = EXCLUDED.leased_at, "
            "lease_until = EXCLUDED.lease_until, "
            "updated_at = EXCLUDED.updated_at "
            "WHERE scheduler_job_lease.owner_token IS NULL "
            "   OR scheduler_job_lease.lease_until <= clock_timestamp() "
            "RETURNING true",
            job, owner, LEASE_TTL,
        )
    return JobLease(job=job, owner_token=owner) if claimed else None


async def _insert_fenced(
    pool, lease: JobLease, details: dict, *, finished: bool = True,
) -> int | None:
    return await pool.fetchval(
        "WITH valid_lease AS ("
        f"  SELECT 1 FROM scheduler_job_lease WHERE {_ACTIVE_LEASE_SQL} FOR SHARE"
        ") "
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "SELECT $3, $4, CASE WHEN $5 THEN clock_timestamp() ELSE NULL END, $6, $7, $8::jsonb "
        "FROM valid_lease RETURNING id",
        lease.job,
        lease.owner_token,
        f"tick_{lease.job}",
        datetime.now(UTC),
        finished,
        details["ok"],
        int(not details["ok"]),
        json.dumps(details),
    )


async def _finish_fenced(pool, lease: JobLease, row_id: int, details: dict) -> bool:
    return bool(await pool.fetchval(
        "WITH valid_lease AS ("
        f"  SELECT 1 FROM scheduler_job_lease WHERE {_ACTIVE_LEASE_SQL} FOR SHARE"
        ") "
        "UPDATE cron_runs "
        "SET finished_at=clock_timestamp(), ok=$4, error_count=$5, details=$6::jsonb "
        "FROM valid_lease "
        "WHERE cron_runs.id=$3 AND cron_runs.finished_at IS NULL "
        "  AND cron_runs.details->>'tick_id'=$7 "
        "RETURNING true",
        lease.job,
        lease.owner_token,
        row_id,
        details["ok"],
        int(not details["ok"]),
        json.dumps(details),
        str(lease.owner_token),
    ))


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
    if unit.name == "events_watch":
        from alpha_agent.api.dependencies import get_db_pool
        from alpha_agent.news.event_watch import collect_official_events

        return await collect_official_events(await get_db_pool())
    if unit.name == "l2_cycle":
        return await routes.l2_cycle()
    raise ValueError("Unknown tick unit")


def _unit_outcome(unit: Unit, result: dict) -> tuple[bool, str | None, int]:
    """Match the old workflow: a unit fails on an exception or an explicit
    rejection, not on per-ticker provider errors. Those are counted, and the
    readiness and publication gates still judge actual coverage."""
    errors = result.get("error_count")
    if not isinstance(errors, int):
        errors = len(result.get("errors") or [])
    # An existing handler's overlap response (`skipped: True`) is NOT proof
    # that its shard ran. daily_prices also returns `skipped`, but as the LIST
    # of tickers the provider had no data for; that is a normal per-ticker
    # miss, judged by the readiness gate. Only a literal True is an overlap.
    if result.get("skipped") is True and result.get("reason") != "no_op_same_market_date":
        return False, "UnitSkipped", errors
    ok = result.get("ok") is True or (unit.name == "daily_prices" and "updated" in result)
    return ok, None if ok else "HandlerRejected", errors


async def run_tick(job: Job, pool) -> dict:
    started = time.monotonic()
    now = datetime.now(UTC)
    lease = await claim_job_lease(job, pool)
    if lease is None:
        return {"ok": True, "skipped": "overlap"}
    try:
        return await _run_leased(job, pool, lease=lease, started=started, now=now)
    finally:
        try:
            await _shield(lease.release(pool))
        except Exception:  # noqa: BLE001 - TTL still bounds recovery if DB is unreachable
            pass


async def _run_leased(
    job: Job, pool, *, lease: JobLease, started: float, now: datetime,
) -> dict:
    day = now.date().isoformat()
    slot = scheduled_slot(job, now)
    market_date = latest_completed_xnys_session(now)
    tick_id = str(lease.owner_token)
    base = {"research_day": day, "market_date": market_date.isoformat(), "slot": slot,
            "tick_id": tick_id, "request_id": tick_id, "unit": None, "offset": None,
            "ok": True, "error_type": None}

    async def stop(reason, units):
        if reason == "lease_expired":
            return {"ok": False, "reason": reason, "research_day": day,
                    "market_date": market_date.isoformat(), "units": units}
        # The high-frequency event collector already has durable unit/source
        # receipts. Do not double its write rate with redundant completion rows.
        if job != "events_watch" or reason not in ("complete", "scheduled_slot_ended"):
            inserted = await _insert_fenced(pool, lease, {**base, "reason": reason})
            if inserted is None:
                return {"ok": False, "reason": "lease_expired", "research_day": day,
                        "market_date": market_date.isoformat(), "units": units}
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
            if not await lease.is_active(pool):
                return await stop("lease_expired", executed)
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
        if unit.name == "daily_prices":
            details["expected_shards"] = len(range(0, readiness["price_universe_count"], PRICE_SLICE))
        # Reserve one durable receipt before I/O. A killed request counts as a
        # failed attempt on the next tick, rather than retrying forever.
        row_id = await _insert_fenced(pool, lease, details, finished=False)
        if row_id is None:
            return await stop("lease_expired", executed)
        try:
            async with asyncio.timeout(max(0, BUDGET_SECONDS - (time.monotonic() - started))):
                result = await execute_unit(unit, research_day=day, slot=slot, request_id=tick_id)
            details["ok"], details["error_type"], details["handler_errors"] = _unit_outcome(unit, result)
            # Only known scalar correlation IDs, no arbitrary provider payloads.
            if isinstance(result.get("run_id"), (str, int)):
                details["run_id"] = result["run_id"]
            if unit.name == "events_watch":
                for key in ("attempted", "events_inserted"):
                    if type(result.get(key)) is int:
                        details[key] = result[key]
                if result.get("reason") in ("completed", "sec_cooldown", "poll_budget_exhausted"):
                    details["collector_reason"] = result["reason"]
        except Exception as exc:  # noqa: BLE001 - recorded as a failed unit
            details["error_type"] = type(exc).__name__
        if not await _finish_fenced(pool, lease, row_id, details):
            return await stop("lease_expired", executed)
        receipts.append(details)
        executed.append({"unit": unit.name, "offset": unit.offset, "ok": details["ok"],
                         "error_type": details["error_type"], "request_id": tick_id})
        if not details["ok"] and unit.name != "publish_recommendation":
            # No in-tick retry. The next tick decides (L2 still runs once the
            # daily budget is spent).
            return await stop("unit_failed", executed)
        cooldown = unit.cooldown
