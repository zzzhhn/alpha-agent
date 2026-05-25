"""Phase 3c factor candidate validator tests. Uses the 2a synthetic-seeding
helper for daily_prices so the panel shape matches the kernel's real consumer."""
from datetime import date, timedelta

import numpy as np
import pytest

from alpha_agent.evolution.factor_validation import (
    FactorCandidateResult,
    MIN_FOLDS,
    evaluate_factor_candidate,
)
from alpha_agent.evolution.llm_factor_proposer import RawProposal
from alpha_agent.evolution.sandbox.runner import SandboxRunner
from alpha_agent.storage.postgres import close_pool, get_pool

# Fixtures (postgresql_proc, postgresql, test_db_url, applied_db) come from
# tests/evolution/conftest.py which re-exports them from tests/storage/conftest.py.


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.fixture(scope="module")
def runner():
    r = SandboxRunner()
    yield r
    r.close()


async def _seed_daily_prices(pool, n_tickers=12, n_days=120, seed=42):
    """Mirror tests/evolution/test_validation.py _seed_prices exactly.
    One row per (ticker, date), close walks randomly from a fixed seed.
    Uses datetime.date objects (not strings) so asyncpg encodes correctly."""
    rng = np.random.default_rng(seed)
    base = 100.0
    base_date = date(2024, 1, 2)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    for t in tickers:
        close = base
        for day_offset in range(n_days):
            d = base_date + timedelta(days=day_offset)
            close = close * (1.0 + rng.normal(0.0, 0.005))
            await pool.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3) "
                "ON CONFLICT (ticker, date) DO UPDATE SET close=EXCLUDED.close",
                t, d, float(close),
            )


@pytest.mark.asyncio
async def test_returns_none_when_history_below_min_folds(pool, runner):
    """Dormant-when-starved: too little history -> None."""
    proposal = RawProposal(expression="rank(ts_mean(returns, 12))", new_operators=[])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    assert result is None


@pytest.mark.asyncio
async def test_returns_result_with_built_in_ops_only(pool, runner):
    """Seed enough history; a proposal with NO new operators still validates
    cleanly because the kernel path works as before (backward compat via
    extra_ops=None defaults)."""
    await _seed_daily_prices(pool)
    proposal = RawProposal(expression="rank(ts_mean(returns, 12))", new_operators=[])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    assert isinstance(result, FactorCandidateResult)
    assert len(result.sharpes) == result.n_folds >= MIN_FOLDS
    assert isinstance(result.ic_oos, float)
    assert result.operator_test_results == []


@pytest.mark.asyncio
async def test_rejects_proposal_when_new_op_fails_canned_test(pool, runner):
    """A new operator that returns a scalar fails the shape canned test; the
    candidate is rejected (result is None). The operator never runs in the
    fold loop, so this is a fast rejection."""
    await _seed_daily_prices(pool)
    bad_op = {
        "name": "lf_scalar_op",
        "signature": "(x: ndarray) -> ndarray",
        "python_impl": "def lf_scalar_op(x):\n    return float(x.sum())",
        "doc": "broken; returns scalar",
    }
    proposal = RawProposal(expression="rank(lf_scalar_op(returns))", new_operators=[bad_op])
    result = await evaluate_factor_candidate(pool, runner, proposal)
    assert result is None
