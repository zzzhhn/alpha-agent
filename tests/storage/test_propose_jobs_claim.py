"""Reliable propose-execution: the GitHub Actions job-runner drains the
factor_propose_jobs queue via claim_oldest_queued. The claim must be atomic and
race-safe — a job must never be handed to two runners — since the runner can
have more than one invocation in flight."""
import asyncio

import asyncpg
import pytest

from alpha_agent.storage import propose_jobs as pj


@pytest.mark.asyncio
async def test_claim_returns_none_when_empty(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        assert await pj.claim_oldest_queued(pool) is None
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_claim_drains_queue_and_flips_running(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        a_id = await pj.create_job(pool, user_id=7, n=5)
        b_id = await pj.create_job(pool, user_id=9, n=3)

        c1 = await pj.claim_oldest_queued(pool)
        c2 = await pj.claim_oldest_queued(pool)
        c3 = await pj.claim_oldest_queued(pool)

        assert c1 is not None and c2 is not None
        assert {c1["id"], c2["id"]} == {a_id, b_id}  # each drained exactly once
        assert c3 is None  # queue empty

        by_id = {c["id"]: c for c in (c1, c2)}
        assert by_id[a_id]["user_id"] == 7 and by_id[a_id]["n"] == 5
        assert by_id[b_id]["user_id"] == 9 and by_id[b_id]["n"] == 3

        for job_id in (a_id, b_id):
            row = await pj.get_job(pool, job_id)
            assert row["status"] == "running"
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_concurrent_claims_single_winner(applied_db):
    """FOR UPDATE SKIP LOCKED: five runners racing one queued job → exactly one
    wins, the rest get None. Without SKIP LOCKED this would double-run the job."""
    pool = await asyncpg.create_pool(applied_db, min_size=4, max_size=8)
    try:
        job = await pj.create_job(pool, user_id=1, n=5)
        results = await asyncio.gather(
            *[pj.claim_oldest_queued(pool) for _ in range(5)]
        )
        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1
        assert claimed[0]["id"] == job
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_get_job_decodes_jsonb_result_to_dict(applied_db):
    """mark_done writes the result as jsonb; get_job must return it as a decoded
    dict, not the raw JSON string asyncpg hands back (no codec on the pool). If
    it's a string the propose UI reads result.proposed/evaluated as undefined and
    shows "undefined 个候选已入队"."""
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        job_id = await pj.create_job(pool, user_id=1, n=5)
        await pj.mark_done(
            pool, job_id, {"evaluated": 5, "proposed": 2, "dormant": False}
        )
        job = await pj.get_job(pool, job_id)
        assert isinstance(job["result"], dict)  # decoded, not a JSON string
        assert job["result"]["proposed"] == 2
        assert job["result"]["evaluated"] == 5
        assert job["status"] == "done"
    finally:
        await pool.close()
