"""Tests for the methodology proposer orchestrator (Phase 2a).

Fixture pattern mirrors tests/evolution/test_validation.py SLICE B:
  - applied_db re-exported from tests.storage.conftest
  - pool fixture builds an asyncpg pool from the DSN
  - _seed_prices helper is the EXACT same seeding shape used in test_validation.py
"""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from tests.storage.conftest import postgresql_proc, postgresql, test_db_url, applied_db  # noqa: F401
from alpha_agent.storage.postgres import close_pool, get_pool


# ---------------------------------------------------------------------------
# Shared seeding helper (identical shape to test_validation.py)
# ---------------------------------------------------------------------------

async def _seed_prices(pool, tickers: list[str], n_days: int, base_date: date) -> None:
    """Insert daily_prices rows: one row per (ticker, date), close starts at 100
    and walks randomly with a deterministic seed so results are stable."""
    rng = np.random.default_rng(seed=42)
    for ticker in tickers:
        close = 100.0
        for day_offset in range(n_days):
            d = base_date + timedelta(days=day_offset)
            close = close * (1.0 + rng.normal(0.0, 0.005))
            await pool.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3) "
                "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
                ticker, d, float(close),
            )


# ---------------------------------------------------------------------------
# Pool fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


# ---------------------------------------------------------------------------
# Test 1: dormant when history is too short
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dormant_when_history_too_short(pool):
    """With fewer days than needed for MIN_FOLDS folds, run_proposer returns
    the dormant sentinel and writes zero pending rows."""
    from alpha_agent.evolution.proposer import run_proposer

    base = date(2024, 1, 2)
    tickers = [f"T{i:02d}" for i in range(12)]
    # 20 days is not enough for 3 folds of 15 rows each (need >= 45+embargo)
    await _seed_prices(pool, tickers, n_days=20, base_date=base)

    result = await run_proposer(pool)

    assert result == {"evaluated": 0, "proposed": 0, "dormant": True}

    pending_count = await pool.fetchval(
        "SELECT count(*) FROM config_change_log WHERE status = 'pending'"
    )
    assert pending_count == 0, (
        f"expected 0 pending rows when dormant, got {pending_count}"
    )


# ---------------------------------------------------------------------------
# Test 2: survivors are capped, shape is correct, engine_config untouched
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_proposes_only_survivors_capped_and_does_not_mutate_config(pool):
    """With enough history, run_proposer returns the expected shape and writes
    at most MAX_PROPOSALS_PER_DAY rows, each with the required evidence keys.
    engine_config must be completely untouched (run_proposer must NOT call
    set_config or write to engine_config).

    Because OOS Sharpe on synthetic random data may yield proposed==0
    legitimately, we assert invariants not a specific nonzero count.
    """
    from alpha_agent import config_store
    from alpha_agent.evolution.proposer import MAX_PROPOSALS_PER_DAY, run_proposer

    base = date(2024, 1, 2)
    tickers = [f"T{i:02d}" for i in range(12)]
    # 120 days: enough for MIN_FOLDS=3 folds of 15+ rows each with embargo=5
    await _seed_prices(pool, tickers, n_days=120, base_date=base)

    # Snapshot engine_config before (should be empty; captures count + values)
    engine_rows_before = await pool.fetch("SELECT key, value FROM engine_config ORDER BY key")

    # Snapshot the config cache before
    cache_before = dict(config_store._CACHE)

    result = await run_proposer(pool)

    # --- structural assertions on return dict ---
    assert "evaluated" in result
    assert "proposed" in result
    assert result.get("dormant") is False
    assert isinstance(result["evaluated"], int)
    assert isinstance(result["proposed"], int)
    assert result["evaluated"] >= 0
    assert 0 <= result["proposed"] <= MAX_PROPOSALS_PER_DAY

    # --- pending rows: cap holds and each row has the required shape ---
    pending_rows = await pool.fetch(
        "SELECT user_id, field, old_value, new_value, source, status, evidence "
        "FROM config_change_log WHERE status = 'pending'"
    )
    assert len(pending_rows) == result["proposed"]
    assert len(pending_rows) <= MAX_PROPOSALS_PER_DAY

    required_evidence_keys = {"sharpes", "ic_oos", "deflated_sharpe", "n_trials", "rationale"}
    for row in pending_rows:
        assert row["status"] == "pending"
        assert row["source"] == "proposer"
        assert row["evidence"] is not None, "evidence must be non-null for every pending row"
        # asyncpg returns jsonb as a Python dict already
        ev = row["evidence"] if isinstance(row["evidence"], dict) else json.loads(row["evidence"])
        missing = required_evidence_keys - set(ev.keys())
        assert not missing, f"evidence missing keys: {missing}"
        assert isinstance(ev["sharpes"], list)
        assert isinstance(ev["ic_oos"], float)
        assert isinstance(ev["deflated_sharpe"], float)
        assert isinstance(ev["n_trials"], int)
        assert isinstance(ev["rationale"], str)

    # --- engine_config must be completely untouched ---
    engine_rows_after = await pool.fetch("SELECT key, value FROM engine_config ORDER BY key")
    assert list(engine_rows_before) == list(engine_rows_after), (
        "run_proposer must not write to engine_config"
    )

    # --- config cache must be identical after run_proposer ---
    cache_after = dict(config_store._CACHE)
    assert cache_after == cache_before, (
        "run_proposer must not leave _CACHE dirty"
    )
