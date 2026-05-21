# tests/storage/test_migration_v013.py
import json

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_confidence_calibration_table_upserts(pool):
    await pool.execute(
        """
        INSERT INTO confidence_calibration
            (as_of, isotonic_map, buckets, n_pairs, applied)
        VALUES (now(), $1::jsonb, $2::jsonb, 120, true)
        """,
        json.dumps({"x": [0.0, 0.5, 1.0], "y": [0.0, 0.4, 0.6]}),
        json.dumps([{"lo": 0.0, "hi": 0.1, "hit_rate": 0.0, "brier": 0.0, "n": 5}]),
    )
    row = await pool.fetchrow(
        "SELECT isotonic_map, n_pairs, applied FROM confidence_calibration "
        "ORDER BY as_of DESC LIMIT 1"
    )
    assert row["n_pairs"] == 120
    assert row["applied"] is True
    assert json.loads(row["isotonic_map"])["y"] == [0.0, 0.4, 0.6]
