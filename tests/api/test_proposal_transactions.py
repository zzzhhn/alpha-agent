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


def _approval_routes(pool, monkeypatch, kind):
    async def get_pool():
        return pool

    if kind == "factor":
        return "factor.custom_expression", factor_lab.approve_proposal, factor_lab.rollback_proposal
    monkeypatch.setattr(evolution, "get_db_pool", get_pool)

    async def approve(proposal_id, user_id, _):
        return await evolution.approve(proposal_id, user_id)

    async def rollback(proposal_id, user_id, _):
        return await evolution.rollback(proposal_id, user_id)

    return "rating.no_trade_band", approve, rollback


async def _proposal(pool, kind, value):
    if kind == "factor":
        return await pool.fetchval(
            "INSERT INTO factor_proposals(expression,evidence,diagnostic) "
            "VALUES ($1,'{}','{}') RETURNING id", value,
        )
    return await pool.fetchval(
        "INSERT INTO config_change_log(user_id,field,old_value,new_value,source,status) "
        "VALUES (0,'rating.no_trade_band','0.99',$1,'proposer','pending') RETURNING id",
        json.dumps(value),
    )


def _rollback_response(kind, key, value):
    return {"ok": True, "reverted_to": value} if kind == "factor" else {"ok": True, "reverted": {key: value}}


@pytest.mark.parametrize("kind", ["factor", "methodology"])
@pytest.mark.parametrize("same_value", [True, False])
async def test_approvals_roll_back_in_version_order(decision_pool, monkeypatch, kind, same_value):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, kind)
    initial, a_value, b_value = (
        ("rank(volume)", "rank(close)", "rank(open)") if kind == "factor" else (0.11, 0.25, 0.31)
    )
    if same_value:
        b_value = a_value
    await config_store.set_config(pool, key, initial, 3, "manual")
    base = await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key)
    a = await _proposal(pool, kind, a_value)
    b = await _proposal(pool, kind, b_value)
    await approve(a, 1, pool)
    await approve(b, 2, pool)
    table = "factor_proposals" if kind == "factor" else "config_change_log"
    a_applied, b_applied = [
        await pool.fetchval(f"SELECT applied_change_id FROM {table} WHERE id=$1", proposal)
        for proposal in (a, b)
    ]
    assert a_applied != b_applied
    assert await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key) == b_applied
    assert await pool.fetchval("SELECT supersedes_change_id FROM config_change_log WHERE id=$1", b_applied) == a_applied

    with pytest.raises(HTTPException) as expired:
        await rollback(a, 1, pool)
    assert expired.value.status_code == 409
    assert config_store.get_config(key) == b_value

    assert await rollback(b, 2, pool) == _rollback_response(kind, key, a_value)
    assert await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key) == a_applied
    assert await rollback(a, 1, pool) == _rollback_response(kind, key, initial)
    assert await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key) == base
    assert config_store.get_config(key) == initial

    with pytest.raises(HTTPException) as repeated:
        await rollback(a, 1, pool)
    assert repeated.value.status_code == 409
    assert "already rolled back" in repeated.value.detail
    log = await pool.fetch(
        "SELECT id,rollback_of,supersedes_change_id,user_id FROM config_change_log "
        "WHERE field=$1 AND source='rollback' ORDER BY id", key,
    )
    assert [(row["rollback_of"], row["supersedes_change_id"], row["user_id"]) for row in log] == [
        (b_applied if kind == "factor" else b, b_applied, 2),
        (a_applied if kind == "factor" else a, a_applied, 1),
    ]
    for original, rollback_log in zip((b, a), log):
        assert await pool.fetchval(
            f"SELECT rollback_change_id FROM {table} WHERE id=$1", original,
        ) == rollback_log["id"]


@pytest.mark.parametrize("kind", ["factor", "methodology"])
async def test_manual_same_value_is_a_new_version(decision_pool, monkeypatch, kind):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, kind)
    value = "rank(close)" if kind == "factor" else 0.25
    proposal_id = await _proposal(pool, kind, value)
    await approve(proposal_id, 1, pool)
    await config_store.set_config(pool, key, value, 2, "manual")

    with pytest.raises(HTTPException) as expired:
        await rollback(proposal_id, 1, pool)
    assert expired.value.status_code == 409
    assert config_store.get_config(key) == value
    assert await pool.fetchval("SELECT count(*) FROM config_change_log WHERE source='rollback'") == 0


@pytest.mark.parametrize("kind", ["factor", "methodology"])
async def test_concurrent_rollbacks_commit_one_decision(decision_pool, monkeypatch, kind):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, kind)
    initial, approved = ("rank(volume)", "rank(close)") if kind == "factor" else (0.12, 0.25)
    await config_store.set_config(pool, key, initial, 3, "manual")
    proposal_id = await _proposal(pool, kind, approved)
    await approve(proposal_id, 1, pool)

    outcomes = await asyncio.gather(
        rollback(proposal_id, 1, pool), rollback(proposal_id, 2, pool), return_exceptions=True,
    )
    assert sum(result == _rollback_response(kind, key, initial) for result in outcomes) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in outcomes) == 1
    assert await pool.fetchval("SELECT count(*) FROM config_change_log WHERE source='rollback'") == 1
    assert config_store.get_config(key) == initial


async def test_methodology_rollback_restores_default_semantics_for_absent_key(decision_pool, monkeypatch):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, "methodology")
    proposal_id = await _proposal(pool, "methodology", 0.25)
    await approve(proposal_id, 1, pool)
    assert await rollback(proposal_id, 1, pool) == _rollback_response("methodology", key, 0.15)
    assert not await pool.fetchval("SELECT EXISTS(SELECT 1 FROM engine_config WHERE key=$1)", key)
    assert config_store.get_config(key) == 0.15
    assert config_store.get_config(key, 0.17) == 0.17


@pytest.mark.parametrize("kind", ["factor", "methodology"])
async def test_unbound_legacy_approval_requires_review(decision_pool, monkeypatch, kind):
    pool = decision_pool
    key, _, rollback = _approval_routes(pool, monkeypatch, kind)
    value = "rank(close)" if kind == "factor" else 0.25
    proposal_id = await _proposal(pool, kind, value)
    table = "factor_proposals" if kind == "factor" else "config_change_log"
    await pool.execute(f"UPDATE {table} SET status='approved' WHERE id=$1", proposal_id)
    await pool.execute("INSERT INTO engine_config(key,value) VALUES($1,$2::jsonb)", key, json.dumps(value))
    await pool.execute(
        "INSERT INTO config_change_log(user_id,field,old_value,new_value,source) VALUES(1,$1,'null',$2,'approved')",
        key, json.dumps(value),
    )

    with pytest.raises(HTTPException) as bad:
        await rollback(proposal_id, 1, pool)
    assert bad.value.status_code == 409 and "requires review" in bad.value.detail
    assert json.loads(await pool.fetchval("SELECT value FROM engine_config WHERE key=$1", key)) == value
    assert await pool.fetchval("SELECT count(*) FROM config_change_log WHERE source='rollback'") == 0


async def test_unversioned_writer_invalidates_live_pointer_even_for_equal_value(decision_pool, monkeypatch):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, "methodology")
    proposal_id = await _proposal(pool, "methodology", 0.25)
    await approve(proposal_id, 1, pool)
    await pool.execute("UPDATE engine_config SET value='0.25'::jsonb WHERE key=$1", key)

    assert await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key) is None
    with pytest.raises(HTTPException) as bad:
        await rollback(proposal_id, 1, pool)
    assert bad.value.status_code == 409 and "requires review" in bad.value.detail


async def test_methodology_rollback_preserves_explicit_null(decision_pool, monkeypatch):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, "methodology")
    await config_store.set_config(pool, key, None, 3, "manual")
    proposal_id = await _proposal(pool, "methodology", 0.25)
    await approve(proposal_id, 1, pool)
    assert await rollback(proposal_id, 1, pool) == _rollback_response("methodology", key, None)
    assert await pool.fetchval("SELECT value::text FROM engine_config WHERE key=$1", key) == "null"
    assert config_store.get_config(key, 0.17) is None


@pytest.mark.parametrize("kind", ["factor", "methodology"])
async def test_failed_rollback_binding_leaves_config_journal_and_cache_unchanged(decision_pool, monkeypatch, kind):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, kind)
    approved = "rank(close)" if kind == "factor" else 0.25
    proposal_id = await _proposal(pool, kind, approved)
    await approve(proposal_id, 1, pool)
    table = "factor_proposals" if kind == "factor" else "config_change_log"
    version = await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key)
    await pool.execute(f"""
        CREATE FUNCTION refuse_rollback_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'synthetic rollback binding failure'; END $$;
        CREATE TRIGGER refuse_binding BEFORE UPDATE OF rollback_change_id ON {table}
        FOR EACH ROW EXECUTE FUNCTION refuse_rollback_binding()
    """)
    with pytest.raises(asyncpg.RaiseError, match="synthetic rollback binding failure"):
        await rollback(proposal_id, 1, pool)
    assert json.loads(await pool.fetchval("SELECT value FROM engine_config WHERE key=$1", key)) == approved
    assert await pool.fetchval("SELECT current_change_id FROM engine_config WHERE key=$1", key) == version
    assert await pool.fetchval("SELECT count(*) FROM config_change_log WHERE source='rollback'") == 0
    assert config_store.get_config(key) == approved


async def test_unconfiguring_fences_an_in_flight_cache_refresh(decision_pool, monkeypatch):
    pool = decision_pool
    key, approve, rollback = _approval_routes(pool, monkeypatch, "methodology")
    proposal_id = await _proposal(pool, "methodology", 0.25)
    await approve(proposal_id, 1, pool)
    read_done, release = asyncio.Event(), asyncio.Event()

    class DelayedRefresh:
        async def fetch(self, query):
            rows = await pool.fetch(query)
            read_done.set()
            await release.wait()
            return rows

    refreshing = asyncio.create_task(config_store.refresh_config(DelayedRefresh()))
    try:
        await asyncio.wait_for(read_done.wait(), timeout=2)
        await rollback(proposal_id, 1, pool)
    finally:
        release.set()
        await refreshing
    assert config_store.get_config(key, 0.17) == 0.17
    await config_store.set_config(pool, key, 0.23, 3, "manual")
    await config_store.refresh_config(pool)
    assert config_store.get_config(key) == 0.23
