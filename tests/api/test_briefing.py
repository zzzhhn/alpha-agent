"""Phase D compressed briefing: pending proposals split into validated vs
flagged (by skeptic risk / self-correlation), and journal rejects collapsed into
counted recurring failure categories."""
import json

import asyncpg
import pytest

from alpha_agent.api.routes import factor_lab


async def _add_pending(pool, expression, evidence):
    await pool.execute(
        "INSERT INTO factor_proposals "
        "(status, expression, new_operators, evidence, diagnostic) "
        "VALUES ('pending', $1, '[]'::jsonb, $2::jsonb, '{}'::jsonb)",
        expression, json.dumps(evidence),
    )


@pytest.mark.asyncio
async def test_briefing_buckets_and_counts(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        # clean survivor -> validated
        await _add_pending(pool, "ts_mean(vwap, 20)", {
            "source": "ga", "deflated_sharpe": 1.2, "ic_oos": 0.03,
            "self_correlation": 0.1,
            "skeptic": {"risk_level": "low", "concerns": []},
        })
        # skeptic-flagged -> flagged
        await _add_pending(pool, "rank(volume)", {
            "source": "llm", "deflated_sharpe": 0.9, "self_correlation": 0.2,
            "skeptic": {"risk_level": "high", "concerns": ["overfit smell"]},
        })
        # correlation-flagged (no skeptic, but high self-corr) -> flagged
        await _add_pending(pool, "zscore(returns)", {
            "source": "ga", "deflated_sharpe": 1.0, "self_correlation": 0.7,
            "skeptic": None,
        })
        # three rejects that collapse to one category
        for _ in range(3):
            await pool.execute(
                "INSERT INTO factor_lessons (expression, outcome, reject_reason, lesson) "
                "VALUES ($1, 'rejected', $2, 'x')",
                "divide(x, x)", "degenerate expression (x/x)",
            )

        b = await factor_lab.get_briefing(pool=pool)

        assert [i["expression"] for i in b["validated"]] == ["ts_mean(vwap, 20)"]
        assert sorted(i["expression"] for i in b["flagged"]) == [
            "rank(volume)", "zscore(returns)",
        ]
        assert b["validated"][0]["source"] == "ga"       # source tag surfaced
        assert b["failure_insights"][0]["count"] == 3
        assert "degenerate" in b["failure_insights"][0]["pattern"]
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_briefing_empty_is_well_formed(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        b = await factor_lab.get_briefing(pool=pool)
        assert b == {"validated": [], "flagged": [], "failure_insights": []}
    finally:
        await pool.close()
