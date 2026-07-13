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
async def test_query_search_matches_alpha_id(applied_db):
    """The search box matches the BRAIN alpha id, not only the expression text."""
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await store.record_brain_alpha(
            pool, user_id=1, expression="group_rank(ts_rank(ebit, 60), subindustry)",
            settings={}, outcome="passed", alpha_id="kRZ4p2A", sharpe=1.8,
        )
        await store.record_brain_alpha(
            pool, user_id=1, expression="rank(volume)", settings={}, outcome="rejected",
        )
        # by the BRAIN code
        r = await store.query_brain_alphas(pool, 1, q="kRZ4p2A")
        assert r["total"] == 1 and r["alphas"][0]["alpha_id"] == "kRZ4p2A"
        # still by expression text
        r = await store.query_brain_alphas(pool, 1, q="volume")
        assert r["total"] == 1 and "volume" in r["alphas"][0]["expression"]
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


@pytest.mark.asyncio
async def test_count_since_is_per_candidate_progress(applied_db):
    """The mining progress bar counts rows created after the dispatch anchor. Every
    candidate (any outcome) counts, and the anchor uses the DB clock."""
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        # anchor on the DB clock, exactly like /mine does
        anchor = await pool.fetchval("SELECT now()")
        # nothing recorded after the anchor yet
        assert await store.count_brain_alphas_since(pool, 1, since=anchor) == 0

        # a full round: passed + rejected + sim_error all count as processed
        await store.record_brain_alpha(
            pool, user_id=1, expression="a", settings={}, outcome="passed",
            alpha_id="A1", sharpe=1.9,
        )
        await store.record_brain_alpha(
            pool, user_id=1, expression="b", settings={}, outcome="rejected",
        )
        await store.record_brain_alpha(
            pool, user_id=1, expression="c", settings={}, outcome="sim_error",
            detail="boom",
        )
        assert await store.count_brain_alphas_since(pool, 1, since=anchor) == 3

        # scoped to the user, and to rows AFTER the anchor
        await store.record_brain_alpha(
            pool, user_id=2, expression="other", settings={}, outcome="passed",
            alpha_id="Z1",
        )
        assert await store.count_brain_alphas_since(pool, 1, since=anchor) == 3
        later = await pool.fetchval("SELECT now()")
        assert await store.count_brain_alphas_since(pool, 1, since=later) == 0
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_blend_parents_round_trip_and_is_blend_derivation(applied_db):
    """A blend candidate's parent expressions persist and come back with
    is_blend=True; a normal candidate has neither, and is_blend is derived
    (never a stored column) so it can't drift from blend_parents."""
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        parents = ["rank(volume)", "ts_rank(ebit, 60)"]
        blend_id = await store.record_brain_alpha(
            pool, user_id=1, expression="add(rank(volume), ts_rank(ebit, 60))",
            settings={}, outcome="passed", alpha_id="B1", sharpe=1.7,
            blend_parents=parents,
        )
        plain_id = await store.record_brain_alpha(
            pool, user_id=1, expression="rank(close)", settings={}, outcome="passed",
            alpha_id="B2", sharpe=1.2,
        )

        blend_row = await store.get_brain_alpha(pool, 1, blend_id)
        assert blend_row["is_blend"] is True
        assert blend_row["blend_parents"] == parents

        plain_row = await store.get_brain_alpha(pool, 1, plain_id)
        assert plain_row["is_blend"] is False
        assert plain_row["blend_parents"] is None

        # same guarantees through the paginated/filtered query path used by the API
        r = await store.query_brain_alphas(pool, 1, sort="created_at", descending=False)
        by_id = {a["id"]: a for a in r["alphas"]}
        assert by_id[blend_id]["is_blend"] is True
        assert by_id[blend_id]["blend_parents"] == parents
        assert by_id[plain_id]["is_blend"] is False
        assert by_id[plain_id]["blend_parents"] is None
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
