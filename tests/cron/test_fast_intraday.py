"""Fast intraday cron tests. Mocks all signal fetches; uses real ephemeral Postgres."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from alpha_agent.signals.base import SignalScore
from alpha_agent.signals.registry import all_signal_names, module_path

pytestmark = pytest.mark.asyncio


async def test_fast_intraday_alerts_use_daily_state_and_half_hour_event_buckets(applied_db, monkeypatch):
    from api.cron import fast_intraday

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.storage.queries.get_priority_universe",
        AsyncMock(return_value=["AAPL"]),
    )
    alert_types = ["news_velocity", "iv_spike", "rating_change", "gap_3sigma", "score_spike"]
    monkeypatch.setattr(fast_intraday, "detect_alerts", lambda prev, curr: [
        {"type": kind, "payload": {}} for kind in alert_types
    ])
    current = datetime(2026, 11, 11, 12, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current

    monkeypatch.setattr(fast_intraday, "datetime", Clock)
    patches = _patch_all_signals()
    for p in patches:
        p.start()
    try:
        for minutes in (0, 30, 1440):
            current = datetime(2026, 11, 11, 12, tzinfo=UTC) + timedelta(minutes=minutes)
            result = await fast_intraday.handler()
            assert result["ok"] is True
    finally:
        for p in patches:
            p.stop()

    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch("SELECT type, count(*) AS n FROM alert_queue GROUP BY type")
        assert {row["type"]: row["n"] for row in rows} == {
            "news_velocity": 2, "iv_spike": 2,
            "rating_change": 3, "gap_3sigma": 3, "score_spike": 3,
        }
    finally:
        await conn.close()


def _patch_all_signals():
    # Match the runtime registry so new signals cannot leak live market data
    # into a deterministic alert/weight test.
    targets = all_signal_names()

    def _score(t, a, name):
        return SignalScore(
            ticker=t, z=0.8, raw=0.8, confidence=0.85,
            as_of=a, source=name, error=None,
        )

    def make(name):
        def _f(t, a):
            return _score(t, a, name)

        return _f

    def amake(name):
        async def _af(t, a):
            return _score(t, a, name)

        return _af

    import importlib

    patches = [patch("alpha_agent.signals.gex.compute_gex", return_value=None)]
    for n in targets:
        path = module_path(n)
        patches.append(
            patch(f"{path}.fetch_signal", side_effect=make(n))
        )
        # Async-native signals (e.g. news, political_impact) are invoked by the
        # cron via `await mod.afetch_signal`, not the sync fetch_signal; patch
        # both or the real (empty-DB) async fetch leaks a z=0 into the composite.
        mod = importlib.import_module(path)
        if hasattr(mod, "afetch_signal"):
            patches.append(
                patch(f"{path}.afetch_signal", side_effect=amake(n))
            )
    return patches


async def test_fast_intraday_writes_full_card(applied_db, monkeypatch):
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    # The handler selects its universe via get_priority_universe (async), not
    # the old get_watchlist stub; patch that so the cron builds exactly these.
    monkeypatch.setattr(
        "alpha_agent.storage.queries.get_priority_universe",
        AsyncMock(return_value=["AAPL", "MSFT"]),
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


async def test_fast_intraday_shard_does_not_publish_product_ledger(applied_db, monkeypatch):
    """A shard may update signals but cannot publish a half-finished board."""
    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None

    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.storage.queries.get_priority_universe",
        AsyncMock(return_value=["AAPL", "MSFT"]),
    )
    patches = _patch_all_signals()
    for p in patches:
        p.start()
    try:
        from api.cron.fast_intraday import handler

        result = await handler()  # tier="full" by default
    finally:
        for p in patches:
            p.stop()

    assert result["ok"] is True
    conn = await asyncpg.connect(applied_db)
    try:
        assert await conn.fetchval("SELECT count(*) FROM research_run") == 0
    finally:
        await conn.close()


async def test_fast_intraday_full_run_activates_guarded_weights(applied_db, monkeypatch):
    """A full run consumes the adaptive evidence via the guarded blend (step 5),
    resolving the inert subsystem: effective = 0.9*static + 0.1*adaptive for a
    signal with enough IC history, persisted as status='effective'."""
    from datetime import UTC, datetime, timedelta

    from alpha_agent.storage import postgres as pg_module

    pg_module._pool = None
    pg_module._pool_dsn = None
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.storage.queries.get_priority_universe",
        AsyncMock(return_value=["AAPL", "MSFT"]),
    )

    conn = await asyncpg.connect(applied_db)
    try:
        # adaptive 'live' evidence for factor (static prior 0.30) ...
        await conn.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated) "
            "VALUES ('factor', 'live', 0.50, now())"
        )
        # ... and enough IC history to clear the min-sample gate.
        base = datetime(2026, 6, 1, tzinfo=UTC)
        for i in range(12):
            await conn.execute(
                "INSERT INTO signal_ic_history "
                "(signal_name, window_days, horizon_days, computed_at, ic, n_observations) "
                "VALUES ('factor', 30, 5, $1, 0.05, 50)",
                base + timedelta(days=i),
            )
    finally:
        await conn.close()

    patches = _patch_all_signals()
    for p in patches:
        p.start()
    try:
        from api.cron.fast_intraday import handler

        await handler()  # full tier -> persist effective
    finally:
        for p in patches:
            p.stop()

    conn = await asyncpg.connect(applied_db)
    try:
        eff = await conn.fetchval(
            "SELECT weight FROM signal_weight_current "
            "WHERE signal_name='factor' AND status='effective'"
        )
        assert eff is not None
        assert float(eff) == pytest.approx(0.9 * 0.30 + 0.1 * 0.50)  # 0.32
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
        "alpha_agent.storage.queries.get_priority_universe",
        AsyncMock(return_value=["AAPL"]),
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
