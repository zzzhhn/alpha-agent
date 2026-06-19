# tests/storage/test_migration_v024.py
"""Schema-level tests for the append-only product ledger (V024).

The ledger is the engine's causal memory: research_run records WHAT a run
was (provenance) and rating_snapshot records WHAT the user saw. These tests
pin the table shape, the jsonb round-trip, and the two invariants the DB
itself enforces (one snapshot per ticker per run; a constrained status enum).
Cross-run append-only behavior is exercised at the writer level
(test_product_ledger.py), since corrections legitimately add a second
complete run for the same date.
"""
import json
from datetime import date

import asyncpg
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _insert_run(pool, *, status="complete", for_date=date(2026, 6, 18)):
    return await pool.fetchval(
        """
        INSERT INTO research_run
            (scheduled_for_date, run_type, status, started_at, finished_at,
             data_asof, input_data_cutoff, code_version, registry_hash,
             weight_policy_id, tier_threshold_version)
        VALUES ($1, 'daily_close', $2, now(), now(),
                now(), now(), 'abc1234', 'reg-hash-1',
                'STATIC_V2', 'tiers-v1')
        RETURNING id
        """,
        for_date, status,
    )


@pytest.mark.asyncio
async def test_run_and_snapshot_persist_with_provenance(pool):
    run_id = await _insert_run(pool)
    payload = {"ticker": "AAPL", "rating": "BUY", "composite_score": 1.23}
    weights = {"technicals": 0.15, "rsrs": 0.05}
    await pool.execute(
        """
        INSERT INTO rating_snapshot
            (run_id, ticker, in_universe, eligible, eligibility_reason,
             composite_z, rank, tier, coverage, effective_weight_json,
             user_visible_payload_json, price_source, price_downloaded_at,
             adjustment_mode, feed_status)
        VALUES ($1, 'AAPL', true, true, NULL,
                1.23, 1, 'BUY', 0.8, $2::jsonb,
                $3::jsonb, 'yfinance', now(),
                'adjusted', 'fresh')
        """,
        run_id, json.dumps(weights), json.dumps(payload),
    )
    row = await pool.fetchrow(
        "SELECT * FROM rating_snapshot WHERE run_id=$1 AND ticker='AAPL'", run_id
    )
    assert row["rank"] == 1
    assert row["tier"] == "BUY"
    assert row["price_source"] == "yfinance"
    assert json.loads(row["user_visible_payload_json"]) == payload
    assert json.loads(row["effective_weight_json"]) == weights

    run = await pool.fetchrow("SELECT * FROM research_run WHERE id=$1", run_id)
    assert run["weight_policy_id"] == "STATIC_V2"
    assert run["registry_hash"] == "reg-hash-1"
    assert run["tier_threshold_version"] == "tiers-v1"
    assert run["code_version"] == "abc1234"


@pytest.mark.asyncio
async def test_one_snapshot_per_ticker_per_run(pool):
    run_id = await _insert_run(pool)
    await pool.execute(
        "INSERT INTO rating_snapshot (run_id, ticker) VALUES ($1, 'MSFT')", run_id
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await pool.execute(
            "INSERT INTO rating_snapshot (run_id, ticker) VALUES ($1, 'MSFT')", run_id
        )


@pytest.mark.asyncio
async def test_status_check_constraint_rejects_unknown(pool):
    with pytest.raises(asyncpg.CheckViolationError):
        await _insert_run(pool, status="bogus")


@pytest.mark.asyncio
async def test_snapshot_requires_existing_run(pool):
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await pool.execute(
            "INSERT INTO rating_snapshot (run_id, ticker) VALUES (999999, 'NVDA')"
        )
