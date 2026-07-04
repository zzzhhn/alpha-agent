"""F1: server-side paginated + filtered listing for the BRAIN UI."""
import asyncpg
import pytest

from alpha_agent.brain import store
from alpha_agent.brain.pnl import pnl_to_points


async def _seed(pool):
    rows = [
        ("group_rank(ts_rank(ebit, 60), subindustry)", "passed", 1.8, 1.1, 0.2),
        ("group_rank(divide(cashflow_op, assets), industry)", "rejected", 0.5, 0.3, 0.1),
        ("rank(ts_delta(volume, 20))", "rejected", -0.3, -0.1, 0.4),
        ("group_neutralize(ts_zscore(eps, 126), sector)", "flagged", 1.4, 0.9, 0.15),
    ]
    for expr, oc, sh, fi, to in rows:
        await store.record_brain_alpha(
            pool, user_id=1, expression=expr, settings={}, outcome=oc,
            alpha_id="A" if oc != "rejected" else None,
            sharpe=sh, fitness=fi, turnover=to,
        )


@pytest.mark.asyncio
async def test_query_filters_paginates_and_counts(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await _seed(pool)

        # outcome filter + total
        r = await store.query_brain_alphas(pool, 1, outcome="rejected")
        assert r["total"] == 2 and len(r["alphas"]) == 2

        # sharpe_min filter
        r = await store.query_brain_alphas(pool, 1, sharpe_min=1.0)
        assert r["total"] == 2  # 1.8 and 1.4
        assert all(a["sharpe"] >= 1.0 for a in r["alphas"])

        # text search
        r = await store.query_brain_alphas(pool, 1, q="cashflow_op")
        assert r["total"] == 1 and "cashflow_op" in r["alphas"][0]["expression"]

        # sort by sharpe desc
        r = await store.query_brain_alphas(pool, 1, sort="sharpe", descending=True)
        sharpes = [a["sharpe"] for a in r["alphas"]]
        assert sharpes == sorted(sharpes, reverse=True)

        # pagination
        r1 = await store.query_brain_alphas(pool, 1, limit=2, offset=0)
        r2 = await store.query_brain_alphas(pool, 1, limit=2, offset=2)
        assert r1["total"] == 4 and len(r1["alphas"]) == 2 and len(r2["alphas"]) == 2
        assert {a["id"] for a in r1["alphas"]}.isdisjoint({a["id"] for a in r2["alphas"]})
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_query_submitted_filter(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        rid = await store.record_brain_alpha(
            pool, user_id=1, expression="x", settings={}, outcome="passed",
            alpha_id="A1", sharpe=1.5,
        )
        await store.record_brain_alpha(
            pool, user_id=1, expression="y", settings={}, outcome="passed",
            alpha_id="A2", sharpe=1.6,
        )
        await store.mark_submitted(pool, rid, brain_status="ACTIVE")
        assert (await store.query_brain_alphas(pool, 1, submitted=True))["total"] == 1
        assert (await store.query_brain_alphas(pool, 1, submitted=False))["total"] == 1
    finally:
        await pool.close()


# ── PnL parser ────────────────────────────────────────────────────────────
def test_pnl_to_points_extracts_date_and_cumulative():
    rs = {"records": [["2020-01-02", 0.0], ["2020-01-03", 12.5], ["2020-01-06", 30.1]]}
    pts = pnl_to_points(rs)
    assert pts == [
        {"date": "2020-01-02", "pnl": 0.0},
        {"date": "2020-01-03", "pnl": 12.5},
        {"date": "2020-01-06", "pnl": 30.1},
    ]


def test_pnl_to_points_defensive():
    assert pnl_to_points({}) == []
    assert pnl_to_points({"records": [["d"], "bad", 3]}) == []  # malformed rows skipped
    assert pnl_to_points(None) == []
