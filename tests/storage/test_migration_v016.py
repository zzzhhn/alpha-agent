import json
import pytest
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_factor_proposals_table_shape(pool):
    pid = await pool.fetchval(
        "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
        "VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb) RETURNING id",
        "rank(ts_mean(returns, 12))",
        json.dumps([]),
        json.dumps({"sharpes": [0.8, 0.7], "ic_oos": 0.04, "deflated_sharpe": 0.5,
                    "baseline_sharpe": 0.3, "n_folds": 3, "n_trials": 5, "llm_rationale": "test"}),
        json.dumps({"weak_signal": "news_24h", "weak_signal_ic": 0.005,
                    "symptom_summary": "news IC dropped"}),
    )
    row = await pool.fetchrow(
        "SELECT status, expression, new_operators, evidence FROM factor_proposals WHERE id=$1", pid,
    )
    assert row["status"] == "pending"
    assert row["expression"] == "rank(ts_mean(returns, 12))"


@pytest.mark.asyncio
async def test_factor_proposals_status_check_rejects_garbage(pool):
    with pytest.raises(Exception):
        await pool.execute(
            "INSERT INTO factor_proposals (status, expression, new_operators, evidence, diagnostic) "
            "VALUES ('half-baked', 'x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb)"
        )


@pytest.mark.asyncio
async def test_extended_operators_table_shape(pool):
    pid = await pool.fetchval(
        "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
        "VALUES ('x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb) RETURNING id"
    )
    await pool.execute(
        "INSERT INTO extended_operators (name, signature, python_impl, doc, registered_by, source_proposal_id) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "lf_demo_test", "(x: ndarray) -> ndarray", "def lf_demo_test(x): return x", "demo", 0, pid,
    )
    n = await pool.fetchval("SELECT count(*) FROM extended_operators WHERE name='lf_demo_test'")
    assert n == 1
    with pytest.raises(Exception):
        await pool.execute(
            "INSERT INTO extended_operators (name, signature, python_impl, doc, registered_by, source_proposal_id) "
            "VALUES ('lf_demo_test', 's', 'i', 'd', 0, $1)", pid,
        )
