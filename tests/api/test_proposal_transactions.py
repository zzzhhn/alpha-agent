import asyncio
import json

import asyncpg
import pytest
from fastapi import HTTPException

from alpha_agent import config_store
from alpha_agent.api.routes import evolution, factor_lab


@pytest.fixture
async def decision_pool(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()
        config_store._CACHE.clear()


async def seed(pool, kind):
    if kind == "factor":
        return await pool.fetchval(
            "INSERT INTO factor_proposals(expression, new_operators, evidence, diagnostic) "
            "VALUES ('rank(close)', $1::jsonb, '{}', '{}') RETURNING id",
            json.dumps([{"name": "lf_demo", "signature": "x", "python_impl": "return x"}]),
        )
    return await pool.fetchval(
        "INSERT INTO config_change_log(user_id, field, new_value, source, status) "
        "VALUES (0, 'rating.no_trade_band', '0.25', 'proposer', 'pending') RETURNING id"
    )


@pytest.mark.parametrize("kind", ["factor", "methodology"])
async def test_journal_failure_rolls_back_whole_decision(decision_pool, monkeypatch, kind):
    pool = decision_pool
    proposal = await seed(pool, kind)
    async def get_pool():
        return pool
    monkeypatch.setattr(evolution, "get_db_pool", get_pool)
    await pool.execute("""
        CREATE FUNCTION refuse_approval() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'synthetic journal failure'; END $$;
        CREATE TRIGGER refuse_write BEFORE INSERT ON config_change_log
        FOR EACH ROW WHEN (NEW.source='approved') EXECUTE FUNCTION refuse_approval()
    """)
    cache = dict(config_store._CACHE)
    with pytest.raises(asyncpg.RaiseError):
        if kind == "factor":
            await factor_lab.approve_proposal(proposal, 1, pool)
        else:
            await evolution.approve(proposal, 1)
    table = "factor_proposals" if kind == "factor" else "config_change_log"
    assert await pool.fetchval(f"SELECT status FROM {table} WHERE id=$1", proposal) == "pending"
    assert not await pool.fetchval("SELECT EXISTS(SELECT 1 FROM engine_config)")
    assert not await pool.fetchval("SELECT EXISTS(SELECT 1 FROM extended_operators WHERE name='lf_demo')")
    assert config_store._CACHE == cache


async def test_approve_and_reject_have_one_winner(decision_pool):
    pool = decision_pool
    proposal = await seed(pool, "factor")
    outcomes = await asyncio.gather(
        factor_lab.approve_proposal(proposal, 1, pool),
        factor_lab.reject_proposal(proposal, 2, pool), return_exceptions=True,
    )
    assert sum(isinstance(result, HTTPException) and result.status_code == 404 for result in outcomes) == 1
    decision = await pool.fetchval("SELECT status FROM factor_proposals WHERE id=$1", proposal)
    count = await pool.fetchval("SELECT count(*) FROM config_change_log WHERE source='approved'")
    assert count == int(decision == "approved")
