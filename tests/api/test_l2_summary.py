from datetime import UTC, date, datetime

import asyncpg


async def test_l2_summary_reports_risk_costs_and_sector(
    client_with_db, applied_db
):
    conn = await asyncpg.connect(applied_db)
    try:
        strategy_id = await conn.fetchval(
            "INSERT INTO l2_strategy (name, version, params_json) "
            "VALUES ('canonical_top50', 1, '{}'::jsonb) RETURNING id"
        )
        run_id = await conn.fetchval(
            "INSERT INTO research_run "
            "(scheduled_for_date, status, started_at, finished_at) "
            "VALUES ($1, 'complete', $2, $2) RETURNING id",
            date(2026, 7, 1),
            datetime(2026, 7, 1, tzinfo=UTC),
        )
        await conn.execute(
            "INSERT INTO company_profiles (ticker, sector) VALUES ('AAPL', 'Technology')"
        )
        await conn.execute(
            "INSERT INTO l2_order "
            "(strategy_id, source_run_id, signal_date, ticker, target_weight, "
            "generated_at, status) VALUES ($1, $2, $3, 'AAPL', 0.02, $4, 'filled')",
            strategy_id, run_id, date(2026, 7, 1), datetime(2026, 7, 1, tzinfo=UTC),
        )
        for d, gross, net, spy, rsp in (
            (date(2026, 7, 8), 0.02, 0.019, 0.01, 0.008),
            (date(2026, 7, 15), -0.01, -0.011, -0.005, -0.004),
        ):
            await conn.execute(
                "INSERT INTO l2_equity_daily "
                "(strategy_id, as_of_date, gross_return, net_return, "
                "benchmark_return, rsp_return, turnover, n_positions, cost_bps) "
                "VALUES ($1, $2, $3, $4, $5, $6, 0.5, 1, 10)",
                strategy_id, d, gross, net, spy, rsp,
            )
    finally:
        await conn.close()

    response = client_with_db.get("/api/l2/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["periods"] == 2
    assert set(body["cost_sensitivity"]) == {"5", "10", "20"}
    assert body["max_drawdown"] < 0
    assert body["sector_exposure"][0]["sector"] == "Technology"


async def test_l2_summary_does_not_report_missing_rsp_as_flat(
    client_with_db, applied_db
):
    conn = await asyncpg.connect(applied_db)
    try:
        strategy_id = await conn.fetchval(
            "INSERT INTO l2_strategy (name, version, params_json) "
            "VALUES ('canonical_top50', 1, '{}'::jsonb) RETURNING id"
        )
        await conn.execute(
            "INSERT INTO l2_equity_daily "
            "(strategy_id, as_of_date, net_return, benchmark_return) "
            "VALUES ($1, $2, 0.01, 0.005)",
            strategy_id,
            date(2026, 7, 8),
        )
    finally:
        await conn.close()

    body = client_with_db.get("/api/l2/summary").json()
    assert body["rsp_return"] is None
    assert body["series"][0]["rsp"] is None


async def test_critical_dag_health_covers_each_required_node(
    client_with_db, applied_db
):
    conn = await asyncpg.connect(applied_db)
    try:
        now = datetime.now(UTC)
        required_runs = {
            "daily_prices": 8,
            "fast_intraday": 6,
            "l2_cycle": 1,
            "paper_fill": 1,
            "ic_backtest_monthly": 1,
        }
        for name, count in required_runs.items():
            await conn.executemany(
                "INSERT INTO cron_runs "
                "(cron_name, started_at, finished_at, ok, error_count) "
                "VALUES ($1, $2, $2, true, 0)",
                [(name, now)] * count,
            )
        await conn.execute(
            "INSERT INTO research_run "
            "(scheduled_for_date, status, started_at, finished_at) "
            "VALUES ($1, 'complete', $2, $2)",
            date.today(), now,
        )
    finally:
        await conn.close()

    response = client_with_db.get("/api/_health/dag")
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "healthy"
    assert {node["name"] for node in body["nodes"]} == {
        "daily_prices", "fast_intraday", "recommendation_publish",
        "l2_cycle", "paper_fill", "ic_backtest_monthly",
    }
    assert all(node["status"] == "healthy" for node in body["nodes"])


async def test_critical_dag_does_not_hide_a_failed_shard(client_with_db, applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        now = datetime.now(UTC)
        await conn.executemany(
            "INSERT INTO cron_runs "
            "(cron_name, started_at, finished_at, ok, error_count) "
            "VALUES ('daily_prices', $1, $1, $2, $3)",
            [(now, True, 0)] * 7 + [(now, False, 1)],
        )
    finally:
        await conn.close()

    response = client_with_db.get("/api/_health/dag")
    node = next(
        item for item in response.json()["nodes"] if item["name"] == "daily_prices"
    )
    assert node["status"] == "failed"
    assert node["observed_runs"] == 8
    assert node["required_runs"] == 8


async def test_shadow_read_shape_cache_and_same_date_comparison(client_with_db, applied_db):
    from alpha_agent.backtest.shadow_books import ensure_shadow_book
    conn = await asyncpg.connect(applied_db)
    try:
        # ensure_shadow_book requires the shared pool API; the route itself is read-only.
        pool = await asyncpg.create_pool(applied_db)
        try:
            ids = [await ensure_shadow_book(pool, name=n) for n in (
                "shadow_factor_12_1", "shadow_band_40_80", "shadow_bot_rule_weekly")]
        finally:
            await pool.close()
        live = await conn.fetchval(
            "INSERT INTO l2_strategy(name,version,params_json) "
            "VALUES('canonical_top50_continuous',3,'{}') RETURNING id")
        for sid, day, ret in (
            (live, date(2026, 11, 11), 0.5),
            (live, date(2026, 11, 12), 0.01), (live, date(2026, 11, 13), 0.02),
            (ids[0], date(2026, 11, 12), 0), (ids[0], date(2026, 11, 13), 0),
        ):
            await conn.execute(
                "INSERT INTO l2_equity_daily(strategy_id,as_of_date,net_return,nav) VALUES($1,$2,$3,1000000)",
                sid, day, ret)
        before = await conn.fetchval("SELECT count(*) FROM l2_strategy")
    finally:
        await conn.close()
    with client_with_db as client:
        response = client.get("/api/l2/shadow")
        assert response.status_code == 200
        assert "public, s-maxage=60" in response.headers["cache-control"]
        body = response.json()
        assert body["paper_only"] is True and body["personalized"] is False
        assert len(body["books"]) == 3
        book = body["books"][0]
        assert {"name", "protocol", "rule_summary", "start_date", "nav", "cash", "n_positions",
                "cumulative_return", "live_tactical_cumulative_return", "last_valuation_date",
                "pending_count", "unfilled_count"} <= book.keys()
        assert abs(book["live_tactical_cumulative_return"] - 0.0302) < 1e-9
        assert body["books"][1]["live_tactical_cumulative_return"] is None
        conn = await asyncpg.connect(applied_db)
        try:
            assert await conn.fetchval("SELECT count(*) FROM l2_strategy") == before
            await conn.execute("DELETE FROM l2_equity_daily WHERE strategy_id=$1 AND as_of_date=$2",
                               live, date(2026, 11, 12))
        finally:
            await conn.close()
        assert client.get("/api/l2/shadow").json()["books"][0]["live_tactical_cumulative_return"] is None
