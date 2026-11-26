"""R05 using real local PG and synthetic LLM work."""
import asyncio
from unittest.mock import AsyncMock

import asyncpg
import pytest
from fastapi import HTTPException

from alpha_agent.api.routes import cron_routes, factor_lab
from alpha_agent.evolution.llm_factor_proposer import proposal_generation_checkpoint
from alpha_agent.llm.base import llm_retries_disabled
from alpha_agent.storage import propose_jobs as jobs

OWNER = 7
PARTIAL = {"ok": False, "evaluated": 3, "proposed": 1, "dormant": False, "_diag": {"rejects": []}}
COMPLETE = {"ok": True, "evaluated": 4, "proposed": 2, "dormant": False}


@pytest.fixture
async def worker(applied_db, monkeypatch):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=5)
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(cron_routes, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr("alpha_agent.config_store.refresh_config", AsyncMock())
    monkeypatch.setattr("alpha_agent.evolution.diagnostics.compute_diagnostic", AsyncMock())
    monkeypatch.setattr(factor_lab, "refresh_config", AsyncMock())
    monkeypatch.setattr(factor_lab, "_dispatch_propose_runner", AsyncMock())
    work = AsyncMock(return_value=COMPLETE)
    monkeypatch.setattr(factor_lab, "_run_propose_work", work)
    try:
        yield pool, work
    finally:
        await pool.close()


async def age_claim(pool, job_id):
    await pool.execute(
        "UPDATE factor_propose_jobs SET started_at=clock_timestamp()-interval '10 minutes' WHERE id=$1",
        job_id,
    )


async def test_missing_worker_expires_without_replaying_and_manual_enqueue_is_new(worker, monkeypatch):
    pool, work = worker
    old_id = await jobs.create_job(pool, OWNER, 4)
    await jobs.claim_oldest_queued(pool)
    await age_claim(pool, old_id)
    await cron_routes.cron_run_propose_jobs()

    old = await factor_lab.get_propose_job(old_id, user_id=OWNER, pool=pool)
    assert old["status"] == "failed"
    assert old["error_code"] == "worker_interrupted"
    assert old["finished_at"] is not None
    work.assert_not_awaited()

    monkeypatch.setattr(factor_lab, "_MIN_HISTORY_ROWS", 0)
    fresh = await factor_lab.post_propose({"n": 5}, user_id=OWNER, pool=pool)
    assert fresh["job_id"] != old_id
    await cron_routes.cron_run_propose_jobs()
    await cron_routes.cron_run_propose_jobs()
    work.assert_awaited_once()
    assert (await jobs.get_job(pool, fresh["job_id"]))["status"] == "done"
    assert (await factor_lab.get_propose_job(old_id, user_id=OWNER, pool=pool)) == old


async def test_late_worker_cannot_overwrite_terminal_job(worker):
    pool, work = worker
    job_id = await jobs.create_job(pool, OWNER, 4)
    started = asyncio.Event()
    release = asyncio.Event()

    async def run(*args, **kwargs):
        assert llm_retries_disabled.get()
        checkpoint = proposal_generation_checkpoint.get()
        await checkpoint(4)
        started.set()
        await release.wait()
        return COMPLETE

    work.side_effect = run
    runner = asyncio.create_task(cron_routes.cron_run_propose_jobs())
    try:
        await asyncio.wait_for(started.wait(), 3)
        await age_claim(pool, job_id)
        interrupted = await factor_lab.get_propose_job(job_id, user_id=OWNER, pool=pool)
        assert interrupted["progress"] == {"stage": "evaluating", "generated": 4}
    finally:
        release.set()
        await asyncio.wait_for(runner, 3)

    job = await jobs.get_job(pool, job_id)
    assert job["status"] == "failed"
    assert job["error"] == "worker_interrupted"
    assert job == interrupted
    assert job["result"] is None
    work.assert_awaited_once()


async def test_failed_evaluation_keeps_available_counts(worker):
    pool, work = worker
    work.return_value = PARTIAL
    job_id = await jobs.create_job(pool, OWNER, 4)
    await cron_routes.cron_run_propose_jobs()
    row = await jobs.get_job(pool, job_id)
    assert row["status"] == "failed"
    assert row["result"] == PARTIAL
    work.assert_awaited_once()


async def test_dormant_result_is_never_available_to_a_worker(worker, monkeypatch):
    pool, work = worker
    original = jobs.create_job
    claimed = []

    async def try_claim_after_enqueue(*args, **kwargs):
        job_id = await original(*args, **kwargs)
        claimed.append(await jobs.claim_oldest_queued(pool))
        return job_id

    monkeypatch.setattr(jobs, "create_job", try_claim_after_enqueue)
    response = await factor_lab.post_propose({"n": 3}, user_id=OWNER, pool=pool)
    row = await jobs.get_job(pool, response["job_id"])
    assert not any(claimed)
    assert row["status"] == "done"
    assert row["started_at"] is None
    assert row["result"] == response["inline_result"]
    assert not await jobs.claim_oldest_queued(pool)
    work.assert_not_awaited()
    factor_lab._dispatch_propose_runner.assert_not_awaited()



async def test_legacy_running_row_without_start_is_repaired_only_for_owner(worker):
    pool, work = worker
    job_id = await jobs.create_job(pool, OWNER, 4)
    await pool.execute(
        "UPDATE factor_propose_jobs SET status='running', created_at=clock_timestamp()-interval '10 minutes', "
        """result_json='{"evaluated":2,"proposed":0,"dormant":false}'::jsonb WHERE id=$1""",
        job_id,
    )
    with pytest.raises(HTTPException) as error:
        await factor_lab.get_propose_job(job_id, user_id=OWNER + 1, pool=pool)
    assert error.value.status_code == 403
    assert (await jobs.get_job(pool, job_id))["status"] == "running"
    expired = await factor_lab.get_propose_job(job_id, user_id=OWNER, pool=pool)
    assert expired["error_code"] == "worker_interrupted"
    assert expired["started_at"] is None
    assert expired["result"]["evaluated"] == 2
    assert expired == await factor_lab.get_propose_job(job_id, user_id=OWNER, pool=pool)
    work.assert_not_awaited()


async def test_live_claim_is_not_expired(worker):
    pool, work = worker
    job_id = await jobs.create_job(pool, OWNER, 4)
    await jobs.claim_oldest_queued(pool)
    response = await cron_routes.cron_run_propose_jobs()
    assert response["interrupted"] == 0
    assert (await factor_lab.get_propose_job(job_id, user_id=OWNER, pool=pool))["status"] == "running"
    work.assert_not_awaited()


async def test_known_worker_timeout_keeps_generation_progress(worker):
    pool, work = worker
    job_id = await jobs.create_job(pool, OWNER, 4)

    async def time_out(*args, **kwargs):
        checkpoint = proposal_generation_checkpoint.get()
        await checkpoint(3)
        raise TimeoutError

    work.side_effect = time_out
    await cron_routes.cron_run_propose_jobs()
    assert proposal_generation_checkpoint.get() is None
    assert not llm_retries_disabled.get()
    await cron_routes.cron_run_propose_jobs()
    row = await jobs.get_job(pool, job_id)
    assert row["status"] == "failed"
    assert row["error_code"] == "worker_interrupted"
    assert row["progress"] == {"stage": "evaluating", "generated": 3}
    assert row["result"] is None
    work.assert_awaited_once()
