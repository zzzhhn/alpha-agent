"""V02 regression suite: short-transaction durable scheduler leases (`V066`).

Verifies small-pool non-starvation (`max_size = 1, 2, 5`), cross-instance
same-job deduplication, different-job concurrency, killed-invocation recovery
with `UnitInterrupted` failure-budget preservation, DB-clock + owner-token
fencing against expired/late workers, and directional interop with the pre-V066
transaction-scoped advisory lock.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import asyncpg
import pytest

from alpha_agent.api.db_pool import APIConnectionPool
from alpha_agent.scheduling import runner
from alpha_agent.scheduling.ticks import BUDGET_SECONDS, Job

def _freeze_clock(monkeypatch, instant: datetime) -> SimpleNamespace:
    state = SimpleNamespace(now=instant, elapsed=0.0)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.now

    monkeypatch.setattr(runner, "datetime", Frozen)
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: state.elapsed))
    return state


async def _receipts(conn_or_pool, job: Job) -> list[dict]:
    rows = await conn_or_pool.fetch(
        "SELECT id, finished_at, ok, error_count, details "
        "FROM cron_runs WHERE cron_name=$1 ORDER BY id",
        f"tick_{job}",
    )
    out = []
    for row in rows:
        details = json.loads(row["details"]) if isinstance(row["details"], str) else dict(row["details"])
        out.append({
            "id": row["id"],
            "finished_at": row["finished_at"],
            "ok": row["ok"],
            "error_count": row["error_count"],
            "details": details,
        })
    return out


def test_lease_ttl_covers_vercel_300s_hard_ceiling():
    assert runner.VERCEL_MAX_DURATION_SECONDS == 300
    assert BUDGET_SECONDS < runner.VERCEL_MAX_DURATION_SECONDS
    assert runner.LEASE_TTL > timedelta(seconds=runner.VERCEL_MAX_DURATION_SECONDS)


@pytest.mark.asyncio
async def test_small_pool_sizes_1_2_5_do_not_starve_or_deadlock(applied_db, monkeypatch):
    """Exact V02 audit replay (`acquire_timeout=0.15`) across `max_size=1, 2, 5`."""
    _freeze_clock(monkeypatch, datetime(2026, 11, 23, 9, 0, tzinfo=UTC))
    original_capacity = runner.read_capacity

    for size, count in ((1, 1), (1, 2), (2, 1), (2, 2), (5, 2)):
        gate = asyncio.Barrier(count)

        async def gated_capacity(pool):
            await gate.wait()
            return await original_capacity(pool)

        monkeypatch.setattr(runner, "read_capacity", gated_capacity)
        async with asyncpg.create_pool(applied_db, min_size=size, max_size=size) as raw_pool:
            pool = APIConnectionPool(raw_pool, acquire_timeout=0.15)
            jobs: tuple[Job, ...] = ("slow_daily", "minute_bars")[:count]
            results = await asyncio.gather(*(runner.run_tick(j, pool) for j in jobs))
            assert [r["ok"] for r in results] == [True] * count
            assert [r["reason"] for r in results] == ["outside_scheduled_slot"] * count
            active = await raw_pool.fetchval(
                "SELECT count(*) FROM scheduler_job_lease WHERE owner_token IS NOT NULL",
            )
            assert active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("pool_size", [1, 2, 5])
async def test_different_jobs_run_concurrently_in_window_even_on_tiny_pool(
    applied_db, monkeypatch, pool_size: int,
):
    """Two distinct jobs (`fast_tech` and `news_per_ticker`) run concurrently at
    15:30 UTC while `execute_unit` itself borrows DB connections from the same pool."""
    _freeze_clock(monkeypatch, datetime(2026, 11, 23, 15, 30, tzinfo=UTC))
    monkeypatch.setattr(runner, "asyncio", SimpleNamespace(
        timeout=asyncio.timeout, sleep=lambda _s: asyncio.sleep(0),
    ))
    both_started = asyncio.Barrier(2)

    async with asyncpg.create_pool(applied_db, min_size=pool_size, max_size=pool_size) as raw_pool:
        pool = APIConnectionPool(raw_pool, acquire_timeout=0.5)

        async def execute(unit, **kwargs):
            if unit.offset in (0, None):
                await both_started.wait()
            # Borrow a pool connection inside unit I/O to prove lease coordination
            # did not pin the sole connection when max_size=1.
            db_ok = await pool.fetchval("SELECT 1")
            assert db_ok == 1
            return {"ok": True}

        monkeypatch.setattr(runner, "execute_unit", execute)
        tech_res, news_res = await asyncio.gather(
            runner.run_tick("fast_tech", pool),
            runner.run_tick("news_per_ticker", pool),
        )
        assert tech_res["ok"] is True and tech_res["reason"] == "complete"
        assert [u["unit"] for u in tech_res["units"]] == ["fast_tech"]
        assert news_res["ok"] is True and news_res["reason"] == "complete"
        assert [u["offset"] for u in news_res["units"]] == [0, 75]
        assert await raw_pool.fetchval(
            "SELECT count(*) FROM scheduler_job_lease WHERE owner_token IS NOT NULL",
        ) == 0


@pytest.mark.asyncio
async def test_same_job_cross_instance_race_and_midflight_dedup(applied_db, monkeypatch):
    """Across separate pools (separate serverless instances), concurrent invocations
    of the same job execute once and return `skipped='overlap'` for all others."""
    _freeze_clock(monkeypatch, datetime(2026, 11, 23, 18, 15, tzinfo=UTC))
    entered = asyncio.Event()
    release_unit = asyncio.Event()
    calls: list[str] = []

    async def execute(unit, *, request_id, **kwargs):
        calls.append(request_id)
        entered.set()
        await release_unit.wait()
        return {"ok": True}

    monkeypatch.setattr(runner, "execute_unit", execute)

    async with (
        asyncpg.create_pool(applied_db, min_size=1, max_size=1) as raw_a,
        asyncpg.create_pool(applied_db, min_size=1, max_size=1) as raw_b,
        asyncpg.create_pool(applied_db, min_size=1, max_size=1) as raw_c,
    ):
        pool_a = APIConnectionPool(raw_a, acquire_timeout=0.5)
        pool_b = APIConnectionPool(raw_b, acquire_timeout=0.5)
        pool_c = APIConnectionPool(raw_c, acquire_timeout=0.5)

        task_a = asyncio.create_task(runner.run_tick("minute_bars", pool_a))
        task_b = asyncio.create_task(runner.run_tick("minute_bars", pool_b))
        await asyncio.wait_for(entered.wait(), timeout=2.0)

        # While the winner is mid-unit, a third instance also gets immediate overlap.
        overlap_midflight = await runner.run_tick("minute_bars", pool_c)
        assert overlap_midflight == {"ok": True, "skipped": "overlap"}

        release_unit.set()
        res_a, res_b = await asyncio.gather(task_a, task_b)
        outcomes = sorted([res_a, res_b], key=lambda r: "skipped" in r)
        assert outcomes[0]["ok"] is True and outcomes[0]["reason"] == "complete"
        assert len(outcomes[0]["units"]) == 1
        assert outcomes[1] == {"ok": True, "skipped": "overlap"}
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_interrupted_function_recovers_after_db_clock_expiry_and_keeps_failure_budget(
    applied_db, monkeypatch,
):
    """If a function dies hard without running `finally` (leaving an active lease and
    an unfinished `UnitInterrupted` row), overlap is blocked until DB `lease_until`
    passes, then the next tick reclaims the lease, counts the interrupted unit
    toward the 3-failure daily budget, and resumes."""
    clock = _freeze_clock(monkeypatch, datetime(2026, 11, 23, 15, 0, tzinfo=UTC))
    monkeypatch.setattr(runner, "asyncio", SimpleNamespace(
        timeout=asyncio.timeout, sleep=lambda _s: asyncio.sleep(0),
    ))

    async with asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool:
        # Simulate an ungraceful process kill mid-unit: claim lease + write the
        # pre-I/O UnitInterrupted row without calling release() or _finish_fenced().
        crashed_lease = await runner.claim_job_lease("news_per_ticker", pool)
        assert crashed_lease is not None
        interrupted_id = await runner._insert_fenced(
            pool,
            crashed_lease,
            {
                "research_day": "2026-11-23",
                "market_date": "2026-11-20",
                "slot": "2026-11-23:15",
                "tick_id": str(crashed_lease.owner_token),
                "request_id": str(crashed_lease.owner_token),
                "unit": "news_per_ticker",
                "offset": 0,
                "price_pass": None,
                "ok": False,
                "error_type": "UnitInterrupted",
                "observed_at": clock.now.isoformat(),
            },
            finished=False,
        )
        assert interrupted_id is not None

        # Before lease_until expires on the DB clock, another tick sees overlap.
        assert await runner.run_tick("news_per_ticker", pool) == {"ok": True, "skipped": "overlap"}

        # Expire the abandoned lease relative to PostgreSQL clock_timestamp().
        await pool.execute(
            "UPDATE scheduler_job_lease "
            "SET leased_at = clock_timestamp() - interval '331 seconds', "
            "    lease_until = clock_timestamp() - interval '1 second' "
            "WHERE job = 'news_per_ticker'",
        )

        # Next 2 ticks fail on offset 0 -> together with the crashed UnitInterrupted
        # row, that reaches FAILURE_BUDGET == 3 without ever erasing the crash row.
        attempts = 0

        async def fail_then_recover(unit, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise RuntimeError("transient upstream failure")
            return {"ok": True}

        monkeypatch.setattr(runner, "execute_unit", fail_then_recover)

        r1 = await runner.run_tick("news_per_ticker", pool)
        r2 = await runner.run_tick("news_per_ticker", pool)
        r3 = await runner.run_tick("news_per_ticker", pool)
        assert r1["reason"] == "unit_failed"
        assert r2["reason"] == "unit_failed"
        assert r3["reason"] == "failure_budget_exhausted"
        assert r3["units"] == []

        rows = await _receipts(pool, "news_per_ticker")
        assert rows[0]["id"] == interrupted_id
        assert rows[0]["finished_at"] is None
        assert rows[0]["details"]["error_type"] == "UnitInterrupted"

        # On a fresh day, a healthy tick reclaims cleanly and completes both shards.
        clock.now = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
        recovered = await runner.run_tick("news_per_ticker", pool)
        assert recovered["ok"] is True and recovered["reason"] == "complete"
        assert [u["offset"] for u in recovered["units"]] == [0, 75]


@pytest.mark.asyncio
async def test_expired_stale_owner_cannot_overwrite_receipt_advance_or_clobber_new_lease(
    applied_db, monkeypatch,
):
    """When Worker A stalls past `lease_until` and Worker B claims the job, Worker A
    waking up must:
      1. fail `_finish_fenced` and return `ok=False, reason='lease_expired'`,
      2. leave its own `UnitInterrupted` row untouched (`finished_at IS NULL`),
      3. never advance to unit 2 (`offset=75`) or write a stop receipt, and
      4. never release/clobber Worker B's active `owner_token` in `finally`."""
    _freeze_clock(monkeypatch, datetime(2026, 11, 23, 15, 0, tzinfo=UTC))
    monkeypatch.setattr(runner, "asyncio", SimpleNamespace(
        timeout=asyncio.timeout, sleep=lambda _s: asyncio.sleep(0),
    ))

    a_in_unit = asyncio.Event()
    allow_a_resume = asyncio.Event()
    executed_by_worker: list[tuple[str, int | None]] = []

    async with (
        asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool_a,
        asyncpg.create_pool(applied_db, min_size=1, max_size=2) as pool_b,
    ):
        async def execute(unit, *, request_id, **kwargs):
            executed_by_worker.append((request_id, unit.offset))
            if len(executed_by_worker) == 1:
                a_in_unit.set()
                await allow_a_resume.wait()
            return {"ok": True}

        monkeypatch.setattr(runner, "execute_unit", execute)

        task_a = asyncio.create_task(runner.run_tick("news_per_ticker", pool_a))
        await asyncio.wait_for(a_in_unit.wait(), timeout=2.0)

        lease_row_a = await pool_b.fetchrow(
            "SELECT owner_token FROM scheduler_job_lease WHERE job='news_per_ticker'",
        )
        owner_a = lease_row_a["owner_token"]
        assert owner_a is not None

        # Expire Worker A's lease on DB clock and let Worker B claim the lease.
        await pool_b.execute(
            "UPDATE scheduler_job_lease "
            "SET leased_at = clock_timestamp() - interval '331 seconds', "
            "    lease_until = clock_timestamp() - interval '1 second' "
            "WHERE job = 'news_per_ticker' AND owner_token = $1",
            owner_a,
        )
        lease_b = await runner.claim_job_lease("news_per_ticker", pool_b)
        assert lease_b is not None and lease_b.owner_token != owner_a

        # Resume stale Worker A while Worker B owns the active lease.
        allow_a_resume.set()
        res_a = await task_a
        assert res_a["ok"] is False
        assert res_a["reason"] == "lease_expired"
        assert res_a["units"] == []

        # Worker A executed only offset 0 before being fenced; never advanced to 75.
        assert executed_by_worker == [(str(owner_a), 0)]

        # Worker B's lease is still intact (Worker A's finally did NOT release it).
        active_owner = await pool_b.fetchval(
            "SELECT owner_token FROM scheduler_job_lease WHERE job='news_per_ticker'",
        )
        assert active_owner == lease_b.owner_token
        assert await lease_b.is_active(pool_b) is True

        # Worker A's pre-I/O row stays UnitInterrupted (not overwritten to ok=True),
        # and Worker A wrote no trailing control receipt.
        rows_after_a = await _receipts(pool_b, "news_per_ticker")
        assert len(rows_after_a) == 1
        assert rows_after_a[0]["finished_at"] is None
        assert rows_after_a[0]["ok"] is False
        assert rows_after_a[0]["details"]["error_type"] == "UnitInterrupted"
        assert rows_after_a[0]["details"]["tick_id"] == str(owner_a)

        # Direct fenced insert/finish with stale lease_a is also rejected.
        stale_lease = runner.JobLease(job="news_per_ticker", owner_token=owner_a)
        assert await runner._insert_fenced(
            pool_a, stale_lease, {"ok": True, "tick_id": str(owner_a)},
        ) is None
        assert await runner._finish_fenced(
            pool_a,
            stale_lease,
            rows_after_a[0]["id"],
            {"ok": True, "tick_id": str(owner_a)},
        ) is False

        # Release Worker B's manual claim so a full Worker B tick can run cleanly.
        assert await lease_b.release(pool_b) is True
        res_b = await runner.run_tick("news_per_ticker", pool_b)
        assert res_b["ok"] is True and res_b["reason"] == "complete"
        assert [u["offset"] for u in res_b["units"]] == [0, 75]


@pytest.mark.asyncio
async def test_legacy_advisory_lock_interop_both_directions(applied_db, monkeypatch):
    """Document and verify both mixed-version orderings truthfully:
      1. Legacy -> New: while a pre-V066 worker holds `pg_advisory_xact_lock(hashtext('tick:<job>'))`,
         `run_tick` sees it during `claim_job_lease` and returns `skipped='overlap'`
         without writing `scheduler_job_lease` or `cron_runs`.
      2. New -> Legacy: once `claim_job_lease` commits its short transaction, the
         xact advisory lock is released; pre-V066 code does not consult
         `scheduler_job_lease` and CAN acquire `pg_try_advisory_xact_lock` and run.
         Therefore rollout must stop dispatching to / drain pre-V066 instances."""
    _freeze_clock(monkeypatch, datetime(2026, 11, 23, 18, 15, tzinfo=UTC))

    async def legacy_pre_v066_run_tick(job: Job, pool) -> dict:
        """Exact pre-V066 coordination contract from `b1965f9` (`pg_try_advisory_xact_lock` only)."""
        async with pool.acquire() as lock_conn, lock_conn.transaction():
            if not await lock_conn.fetchval(
                "SELECT pg_try_advisory_xact_lock(hashtext($1))", f"tick:{job}",
            ):
                return {"ok": True, "skipped": "overlap"}
            return {"ok": True, "executed_by": "legacy_pre_v066"}

    async with (
        asyncpg.create_pool(applied_db, min_size=1, max_size=2) as new_pool,
        asyncpg.create_pool(applied_db, min_size=1, max_size=2) as legacy_pool,
    ):
        # Direction 1: Legacy holds xact advisory lock first -> New skips cleanly.
        async with legacy_pool.acquire() as legacy_conn, legacy_conn.transaction():
            await legacy_conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", "tick:minute_bars",
            )
            res_new = await runner.run_tick("minute_bars", new_pool)
            assert res_new == {"ok": True, "skipped": "overlap"}
            assert await new_pool.fetchval(
                "SELECT count(*) FROM scheduler_job_lease WHERE job='minute_bars'",
            ) == 0
            assert await _receipts(new_pool, "minute_bars") == []

        # Direction 2: New claims durable lease first -> short claim tx has already
        # committed, so no advisory lock remains held; pre-V066 code does NOT read
        # scheduler_job_lease and CAN acquire pg_try_advisory_xact_lock and proceed,
        # whereas any V066 worker is blocked by scheduler_job_lease.
        lease = await runner.claim_job_lease("minute_bars", new_pool)
        assert lease is not None
        try:
            assert await new_pool.fetchval(
                "SELECT count(*) FROM pg_locks WHERE locktype='advisory'",
            ) == 0
            legacy_res = await legacy_pre_v066_run_tick("minute_bars", legacy_pool)
            assert legacy_res == {"ok": True, "executed_by": "legacy_pre_v066"}
            # Meanwhile any V066-aware worker is blocked by the durable lease.
            assert await runner.run_tick("minute_bars", legacy_pool) == {
                "ok": True, "skipped": "overlap",
            }
        finally:
            assert await lease.release(new_pool) is True
