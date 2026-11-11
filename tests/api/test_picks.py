"""Tests for GET /api/picks/lean."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import asyncpg


async def _seed_fast_rows(applied_db, n: int = 5) -> None:
    conn = await asyncpg.connect(applied_db)
    today = date.today()
    try:
        ratings = ["BUY", "OW", "HOLD", "UW", "SELL"]
        for i, rating in enumerate(ratings[:n]):
            await conn.execute(
                "INSERT INTO daily_signals_fast "
                "(ticker, date, composite, rating, confidence, breakdown, partial) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
                f"T{i}",
                today,
                2.0 - 0.5 * i,
                rating,
                0.8,
                '{"breakdown": []}',
                False,
            )
    finally:
        await conn.close()


async def test_picks_lean_returns_sorted_by_composite(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert "picks" in body
    composites = [p["composite_score"] for p in body["picks"]]
    assert composites == sorted(composites, reverse=True)


async def test_picks_lean_respects_limit(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=2")
    assert r.status_code == 200
    assert len(r.json()["picks"]) == 2


async def test_picks_lean_empty_db_returns_empty_list(client_with_db):
    r = client_with_db.get("/api/picks/lean")
    assert r.status_code == 200
    body = r.json()
    assert body["picks"] == []
    assert body["stale"] is False


async def _seed_fresh_and_dead(applied_db) -> None:
    """TFRESH: fresh signal + closes through today. TDEAD: fresh signal but a
    dead price feed (last close ~30 days ago)."""
    today = date.today()
    conn = await asyncpg.connect(applied_db)
    try:
        for tk, comp in [("TFRESH", 2.0), ("TDEAD", 1.9)]:
            await conn.execute(
                "INSERT INTO daily_signals_fast "
                "(ticker, date, composite, rating, confidence, breakdown, partial) "
                "VALUES ($1, $2, $3, 'BUY', 0.8, '{\"breakdown\": []}', false)",
                tk, today, comp,
            )
        for i in range(5):
            await conn.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3)",
                "TFRESH", today - timedelta(days=4 - i), 100.0 + i,
            )
        for i in range(5):
            await conn.execute(
                "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3)",
                "TDEAD", today - timedelta(days=34 - i), 50.0 + i,
            )
    finally:
        await conn.close()


async def test_picks_lean_excludes_dead_price_feed_from_default(client_with_db, applied_db):
    """A dead-price-feed ticker is dropped from the default ranking."""
    await _seed_fresh_and_dead(applied_db)
    default = [p["ticker"] for p in client_with_db.get("/api/picks/lean?limit=20").json()["picks"]]
    assert "TFRESH" in default
    assert "TDEAD" not in default


async def test_picks_lean_search_still_surfaces_dead_feed(client_with_db, applied_db):
    """An explicit search bypasses the freshness guard so a dead ticker is still
    findable (one app request per test: TestClient runs each on its own loop and
    asyncpg pool connections are loop-bound)."""
    await _seed_fresh_and_dead(applied_db)
    searched = [p["ticker"] for p in client_with_db.get("/api/picks/lean?search=TDEAD").json()["picks"]]
    assert searched == ["TDEAD"]


async def _seed_canonical_run(
    applied_db, *, market_date: date, generated_at: datetime | None = None
) -> int:
    conn = await asyncpg.connect(applied_db)
    try:
        generated_at = generated_at or datetime.now(UTC)
        run_id = await conn.fetchval(
            """
            INSERT INTO research_run
                (scheduled_for_date, run_type, status, started_at, finished_at,
                 data_asof, input_data_cutoff, weight_policy_id, health_json)
            VALUES ($1, 'daily_close', 'complete', $2, $2, $2, $2,
                    'policy-test', '{"passed": true}'::jsonb)
            RETURNING id
            """,
            market_date,
            generated_at,
        )
        for rank, (ticker, score) in enumerate((("AAA", 2.0), ("BBB", 1.0)), 1):
            payload = {
                "ticker": ticker,
                "latest_price": 100.0,
                "price_date": market_date.isoformat(),
                "rating": "BUY" if rank == 1 else "OW",
                "confidence": 0.51,
                "agreement": 0.7,
                "composite_score": score,
                "as_of": datetime.now(UTC).isoformat(),
                "top_drivers": [],
                "top_drags": [],
            }
            await conn.execute(
                """
                INSERT INTO rating_snapshot
                    (run_id, ticker, eligible, composite_z, rank, tier,
                     user_visible_payload_json, feed_status)
                VALUES ($1, $2, true, $3, $4, $5, $6::jsonb, 'fresh')
                """,
                run_id,
                ticker,
                score,
                rank,
                payload["rating"],
                json.dumps(payload),
            )
        return int(run_id)
    finally:
        await conn.close()


async def test_picks_default_reads_one_canonical_run(client_with_db, applied_db):
    from alpha_agent.market_session import latest_completed_xnys_session

    run_id = await _seed_canonical_run(
        applied_db, market_date=latest_completed_xnys_session()
    )
    body = client_with_db.get("/api/picks/lean?limit=20").json()
    assert body["canonical"] is True
    assert body["ranked"] is True
    assert body["tradable"] is True
    assert body["run"]["run_id"] == run_id
    assert {card["run_id"] for card in body["picks"]} == {run_id}
    assert {card["market_date"] for card in body["picks"]} == {
        body["run"]["market_date"]
    }


async def test_session_valid_snapshot_does_not_expire_by_wall_clock(
    client_with_db, applied_db
):
    """A healthy latest-session snapshot remains valid over weekends/holidays."""
    from alpha_agent.market_session import latest_completed_xnys_session

    await _seed_canonical_run(
        applied_db,
        market_date=latest_completed_xnys_session(),
        generated_at=datetime.now(UTC) - timedelta(days=3),
    )

    body = client_with_db.get("/api/picks/lean?limit=20").json()
    assert body["stale"] is False
    assert body["tradable"] is True


async def test_legacy_long_payload_is_not_mislabeled_as_strategic(
    client_with_db, applied_db
):
    from alpha_agent.market_session import latest_completed_xnys_session

    await _seed_canonical_run(
        applied_db, market_date=latest_completed_xnys_session()
    )

    body = client_with_db.get("/api/picks/lean?mode=long&limit=20").json()

    assert body["canonical"] is False
    assert body["ranked"] is False
    assert body["tradable"] is False


async def test_old_canonical_run_is_frozen_not_replaced_by_live_rows(
    client_with_db, applied_db
):
    await _seed_canonical_run(applied_db, market_date=date(2026, 7, 23))
    await _seed_fast_rows(applied_db, n=1)
    body = client_with_db.get("/api/picks/lean?limit=20").json()
    assert body["canonical"] is True
    assert body["tradable"] is False
    assert body["stale"] is True
    assert [card["ticker"] for card in body["picks"]] == ["AAA", "BBB"]


async def test_search_is_unranked_and_not_tradable(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=1)
    body = client_with_db.get("/api/picks/lean?search=T0").json()
    assert body["canonical"] is False
    assert body["ranked"] is False
    assert body["tradable"] is False


async def test_rank_and_grade_http_contract(client_with_db, applied_db):
    from alpha_agent.market_session import latest_completed_xnys_session
    await _seed_canonical_run(applied_db, market_date=latest_completed_xnys_session())
    body = client_with_db.get('/api/picks/lean?side=short&limit=1').json()
    assert body['picks'][0]['rank_score'] == 0
    assert body['rank_score_method']['population'] == 2
    assert body['rank_score_method']['version'] == 'xs_pct_avg_rank_v1'
    assert body['grade_method']['min_universe'] == 20
    assert body['picks'][0]['dimension_scores'] is None


async def test_changes_dates_skip_different_policy_run(client_with_db, applied_db):
    prior_date = date(2026, 11, 6)
    prior_id = await _seed_canonical_run(applied_db, market_date=prior_date)
    different_id = await _seed_canonical_run(applied_db, market_date=date(2026, 11, 9))
    conn = await asyncpg.connect(applied_db)
    try:
        # Test-fixture setup only: the read path must skip this policy.
        await conn.execute("UPDATE research_run SET weight_policy_id='different' WHERE id=$1", different_id)
    finally:
        await conn.close()
    await _seed_canonical_run(applied_db, market_date=date(2026, 11, 10))
    body = client_with_db.get('/api/picks/lean').json()
    assert body['changes']['prior_run_id'] == prior_id
    assert body['changes']['prior_market_date'] == '2026-11-06'
    assert body['changes']['current_market_date'] == '2026-11-10'
    assert body['changes']['prior_generated_at'] is not None


async def test_search_has_no_percentile_population(client_with_db, applied_db):
    await _seed_fast_rows(applied_db)
    body = client_with_db.get('/api/picks/lean?search=T0').json()
    assert body['rank_score_method']['status'] == 'unavailable_exploratory_view'
    assert all(card['rank_score'] is None for card in body['picks'])
    assert all(card['dimension_scores'] is not None for card in body['picks'])
