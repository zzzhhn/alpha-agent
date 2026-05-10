"""Fast intraday cron tests. Mocks all signal fetches; uses real ephemeral Postgres."""
from datetime import UTC, datetime
from unittest.mock import patch

import asyncpg
import pytest

from alpha_agent.signals.base import SignalScore

pytestmark = pytest.mark.asyncio


def _patch_all_signals():
    targets = [
        "factor",
        "technicals",
        "analyst",
        "earnings",
        "news",
        "insider",
        "options",
        "premarket",
        "macro",
        "calendar",
    ]

    def make(name):
        def _f(t, a):
            return SignalScore(
                ticker=t,
                z=0.8,
                raw=0.8,
                confidence=0.85,
                as_of=a,
                source=name,
                error=None,
            )

        return _f

    return [
        patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=make(n))
        for n in targets
    ]


async def test_fast_intraday_writes_full_card(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL", "MSFT"],
    )
    patches = _patch_all_signals()
    for p in patches:
        p.start()
    try:
        from api.cron.fast_intraday import handler

        result = await handler()
    finally:
        for p in patches:
            p.stop()

    assert result["ok"] is True
    assert result["rows_written"] == 2

    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT ticker, rating, confidence FROM daily_signals_fast ORDER BY ticker"
        )
        assert len(rows) == 2
        for r in rows:
            assert r["rating"] in {"BUY", "OW", "HOLD", "UW", "SELL"}
            assert 0.0 <= r["confidence"] <= 1.0
    finally:
        await conn.close()


async def test_fast_intraday_emits_alert_on_rating_change(applied_db, monkeypatch):
    """Pre-seed daily_signals_fast with HOLD; new run with z=0.8 → OW should
    enqueue a rating_change alert."""
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL"],
    )
    today = datetime.now(UTC).date().isoformat()

    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast "
            "(ticker, date, composite, rating, confidence, breakdown, partial) "
            "VALUES ($1, $2::text::date, $3, $4, $5, $6::jsonb, $7)",
            "AAPL",
            today,
            0.0,
            "HOLD",
            0.5,
            '{"breakdown": []}',
            False,
        )
    finally:
        await conn.close()

    patches = _patch_all_signals()  # all z=0.8 → composite ~0.8 → OW
    for p in patches:
        p.start()
    try:
        from api.cron.fast_intraday import handler

        await handler()
    finally:
        for p in patches:
            p.stop()

    conn = await asyncpg.connect(applied_db)
    try:
        alerts = await conn.fetch(
            "SELECT type, payload FROM alert_queue WHERE ticker='AAPL'"
        )
        assert any(a["type"] == "rating_change" for a in alerts)
    finally:
        await conn.close()
