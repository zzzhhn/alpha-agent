# tests/api/test_build_lean_view.py
"""Unit tests for build_lean_view — the picks-assembly extracted from the
/api/picks/lean endpoint so the product ledger can record the EXACT same view
the user saw (one shared code path, no drift). The endpoint is a thin wrapper
over this; test_picks.py pins the wrapper's HTTP behavior unchanged."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from alpha_agent.api.routes.picks import LeanCard, build_lean_view
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, rows):
    today = date.today()
    for tk, comp, rating in rows:
        await pool.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2, $3, $4, 0.8, '{\"breakdown\": []}'::jsonb, false)",
            tk, today, comp, rating,
        )


@pytest.mark.asyncio
async def test_build_lean_view_ranks_by_composite_desc(pool):
    await _seed(pool, [("AAA", 2.0, "BUY"), ("BBB", 1.0, "HOLD"), ("CCC", 1.5, "OW")])
    cards, as_of, stale = await build_lean_view(
        pool, limit=20, search=None, mode="short", side="long"
    )
    assert all(isinstance(c, LeanCard) for c in cards)
    assert [c.ticker for c in cards] == ["AAA", "CCC", "BBB"]
    assert as_of is not None


@pytest.mark.asyncio
async def test_build_lean_view_includes_latest_daily_price_context(pool):
    today = date.today()
    await _seed(pool, [("AAA", 2.0, "BUY")])
    await pool.execute(
        "INSERT INTO company_profiles (ticker, name, name_zh) "
        "VALUES ('AAA', 'Alpha Corp', '阿尔法公司')"
    )
    await pool.executemany(
        "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3)",
        [
            ("AAA", today - timedelta(days=1), 100.0),
            ("AAA", today, 105.0),
        ],
    )

    cards, _as_of, _stale = await build_lean_view(
        pool, limit=20, search=None, mode="short", side="long"
    )

    assert len(cards) == 1
    assert cards[0].company_name == "Alpha Corp"
    assert cards[0].company_name_zh == "阿尔法公司"
    assert cards[0].latest_price == pytest.approx(105.0)
    assert cards[0].price_date == today.isoformat()
    assert cards[0].daily_change_pct == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_build_lean_view_empty_db(pool):
    cards, as_of, stale = await build_lean_view(
        pool, limit=20, search=None, mode="short", side="long"
    )
    assert cards == []
    assert as_of is None
    assert stale is False
