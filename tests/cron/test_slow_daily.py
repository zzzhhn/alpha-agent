"""Cron tests use a real Postgres (applied_db fixture) but mock all signal
fetches so external APIs aren't hit."""
from unittest.mock import patch

import asyncpg
import pytest

from alpha_agent.signals.base import SignalScore

pytestmark = pytest.mark.asyncio


def _patch_slow_signals():
    targets = ["factor", "analyst", "earnings", "insider", "macro"]

    def make(name):
        def _f(t, a):
            return SignalScore(
                ticker=t,
                z=1.0,
                raw=1.0,
                confidence=0.9,
                as_of=a,
                source=name,
                error=None,
            )

        return _f

    return [
        patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=make(n))
        for n in targets
    ]


async def test_slow_daily_writes_one_row_per_ticker(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.SP500_UNIVERSE",
        ["AAPL", "MSFT", "GOOG"],
    )
    patches = _patch_slow_signals()
    for p in patches:
        p.start()
    try:
        from api.cron.slow_daily import handler

        result = await handler()
    finally:
        for p in patches:
            p.stop()

    assert result["ok"] is True
    assert result["rows_written"] == 3

    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT ticker, composite_partial FROM daily_signals_slow ORDER BY ticker"
        )
        assert [r["ticker"] for r in rows] == ["AAPL", "GOOG", "MSFT"]
        assert all(r["composite_partial"] is not None for r in rows)
    finally:
        await conn.close()


async def test_slow_daily_records_cron_run(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr("alpha_agent.universe.SP500_UNIVERSE", ["AAPL"])
    patches = _patch_slow_signals()
    for p in patches:
        p.start()
    try:
        from api.cron.slow_daily import handler

        await handler()
    finally:
        for p in patches:
            p.stop()

    conn = await asyncpg.connect(applied_db)
    try:
        run = await conn.fetchrow(
            "SELECT * FROM cron_runs WHERE cron_name='slow_daily' "
            "ORDER BY started_at DESC LIMIT 1"
        )
        assert run["ok"] is True
        assert run["error_count"] == 0
    finally:
        await conn.close()


async def test_slow_daily_logs_errors_per_failing_ticker(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr("alpha_agent.universe.SP500_UNIVERSE", ["AAPL", "BAD"])

    def fake_factor(t, a):
        if t == "BAD":
            return SignalScore(
                ticker=t,
                z=0.0,
                raw=None,
                confidence=0.0,
                as_of=a,
                source="factor_engine",
                error="ConnectionError: simulated",
            )
        return SignalScore(
            ticker=t,
            z=1.0,
            raw=1.0,
            confidence=0.9,
            as_of=a,
            source="factor_engine",
            error=None,
        )

    other_patches = [
        patch(
            f"alpha_agent.signals.{n}.fetch_signal",
            side_effect=lambda t, a, name=n: SignalScore(
                ticker=t,
                z=0.5,
                raw=0.5,
                confidence=0.8,
                as_of=a,
                source=name,
                error=None,
            ),
        )
        for n in ["analyst", "earnings", "insider", "macro"]
    ]
    patches = [patch("alpha_agent.signals.factor.fetch_signal", side_effect=fake_factor)]
    patches.extend(other_patches)
    for p in patches:
        p.start()
    try:
        from api.cron.slow_daily import handler

        result = await handler()
    finally:
        for p in patches:
            p.stop()

    # Both rows still written; BAD row has factor with confidence=0
    assert result["ok"] is True
    assert result["rows_written"] == 2
