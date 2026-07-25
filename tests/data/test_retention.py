"""Retention prunes, and the interlock that keeps them from eating history."""
from __future__ import annotations

from datetime import date, timedelta

import asyncpg

from alpha_agent.data.retention import prune_daily_signals, prune_news_items


async def _seed_signals(pool, days_ago: list[int]) -> None:
    for d in days_ago:
        await pool.execute(
            "INSERT INTO daily_signals_fast (ticker, date, composite, rating) "
            "VALUES ($1, $2, 0.5, 'BUY') ON CONFLICT DO NOTHING",
            "AAPL",
            date.today() - timedelta(days=d),
        )


async def test_refuses_to_prune_when_nothing_materialized(applied_db):
    """consistency_outcomes empty => prune NOTHING.

    The durable outcomes table is the only reason pruning signals is safe. If it
    has never run, deleting old signals destroys consistency history that cannot
    be rebuilt, so the prune must fail safe rather than free space.
    """
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await _seed_signals(pool, [400, 300])
        status = await prune_daily_signals(pool, days=30)
        assert "SKIP" in status
        assert await pool.fetchval("SELECT count(*) FROM daily_signals_fast") == 2
    finally:
        await pool.close()


async def test_never_prunes_past_the_materializer(applied_db):
    """Rows older than the window but NOT yet materialized must survive.

    Guards the Postgres footgun this was written around: LEAST(d, NULL) returns
    d, so the obvious single-statement SQL would happily delete un-materialized
    history the moment the materializer lagged.
    """
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await _seed_signals(pool, [400, 300, 100])
        # Materializer has only covered up to 350 days ago.
        await pool.execute(
            "INSERT INTO consistency_outcomes (ticker, date, hit) VALUES ($1, $2, true)",
            "AAPL",
            date.today() - timedelta(days=350),
        )
        await prune_daily_signals(pool, days=30)

        remaining = {
            r["date"] for r in await pool.fetch("SELECT date FROM daily_signals_fast")
        }
        # 400d is older than the window AND materialized-through => gone.
        assert date.today() - timedelta(days=400) not in remaining
        # 300d is past the window but NOT materialized yet => kept.
        assert date.today() - timedelta(days=300) in remaining
        # 100d likewise un-materialized => kept.
        assert date.today() - timedelta(days=100) in remaining
    finally:
        await pool.close()


async def test_prune_news_items_drops_only_old_rows(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        for i, age in enumerate([90, 1]):
            await pool.execute(
                "INSERT INTO news_items (dedup_hash, ticker, source, headline, url, "
                "published_at) VALUES ($1,'AAPL','test','h','u', now() - make_interval(days => $2))",
                f"hash-{i}",
                age,
            )
        await prune_news_items(pool, days=30)
        rows = await pool.fetch("SELECT dedup_hash FROM news_items")
        assert [r["dedup_hash"] for r in rows] == ["hash-1"]
    finally:
        await pool.close()
