from datetime import date, timedelta

import numpy as np
import pytest

from alpha_agent.evolution.candidates import ConfigDelta
from alpha_agent.evolution.validation import (
    CandidateResult,
    deflated_sharpe_lite,
    evaluate_candidate,
    purged_fold_indices,
)

# Fixtures (postgresql_proc, postgresql, test_db_url, applied_db) come from
# tests/evolution/conftest.py which re-exports them from tests/storage/conftest.py.


def test_purged_folds_embargo_excludes_overlap():
    folds = purged_fold_indices(n=100, n_folds=5, embargo=5)
    assert len(folds) == 5
    for train_idx, test_idx in folds:
        lo, hi = min(test_idx), max(test_idx)
        assert all(not (lo - 5 <= t <= hi + 5) for t in train_idx)


def test_deflated_sharpe_lite_penalizes_trial_count():
    s = [0.1, 0.2, 0.9]
    d_few = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=3)
    d_many = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=30)
    assert d_many < d_few
    assert deflated_sharpe_lite(best_sharpe=0.2, sharpes=[0.18, 0.2, 0.22], n_trials=20) <= 0.2


# ---------------------------------------------------------------------------
# SLICE B helpers
# ---------------------------------------------------------------------------

async def _seed_prices(pool, tickers: list[str], n_days: int, base_date: date) -> None:
    """Insert daily_prices rows for each ticker.

    Seeding mirrors the shape used by tests/backtest/test_ic_engine_daily_prices.py:
    one row per (ticker, date), close starts at 100 and walks randomly (seed
    is deterministic so test results are stable).

    We use only the `daily_prices` table because that is the sole source of
    close history queried by evaluate_candidate (same table ic_engine uses).
    """
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


@pytest.fixture
async def pool(applied_db):
    from alpha_agent.storage.postgres import close_pool, get_pool
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_evaluate_candidate_returns_none_when_history_too_short(pool):
    """Fewer days than needed for MIN_FOLDS folds -> returns None (dormant-when-starved)."""
    base = date(2024, 1, 2)
    tickers = [f"T{i:02d}" for i in range(12)]
    # Seed only 20 days -- not enough for 3 folds of ~20 rows each
    await _seed_prices(pool, tickers, n_days=20, base_date=base)

    delta = ConfigDelta(
        key="rating.no_trade_band",
        new_value=0.20,
        rationale="test delta",
    )
    result = await evaluate_candidate(pool, delta)
    assert result is None


@pytest.mark.asyncio
async def test_evaluate_candidate_returns_result_with_enough_history(pool):
    """With enough days, returns a CandidateResult with expected structure.

    Also verifies:
    - evaluate_candidate does NOT write to engine_config or call set_config
    - live config (config_store._CACHE) is untouched after the call
    """
    from alpha_agent import config_store

    base = date(2024, 1, 2)
    tickers = [f"T{i:02d}" for i in range(12)]
    # Seed enough days: MIN_FOLDS=3, min_rows_per_fold=15, embargo=5 -> ~90 days
    await _seed_prices(pool, tickers, n_days=120, base_date=base)

    # Capture config cache state before
    cache_snapshot = dict(config_store._CACHE)

    delta = ConfigDelta(
        key="rating.no_trade_band",
        new_value=0.20,
        rationale="test delta",
    )
    result = await evaluate_candidate(pool, delta)

    assert result is not None, "expected CandidateResult with sufficient history"
    assert isinstance(result, CandidateResult)
    assert result.n_folds >= 3
    assert len(result.sharpes) == result.n_folds
    assert isinstance(result.ic_oos, float)
    assert result.delta is delta

    # Config cache must be identical after the call (no set_config side effects)
    assert dict(config_store._CACHE) == cache_snapshot, (
        "evaluate_candidate must not mutate the live config cache"
    )

    # engine_config table must be empty (no DB writes by evaluate_candidate)
    row_count = await pool.fetchval("SELECT count(*) FROM engine_config")
    assert row_count == 0, "evaluate_candidate must not write to engine_config"
