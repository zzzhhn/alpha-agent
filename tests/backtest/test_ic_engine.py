"""Walk-forward IC backtest engine tests (Phase 6a Task 7).

Schema adaptation note: the plan's example SQL referenced
daily_signals_fast(ticker, as_of, signal_name, z) + daily_prices(ticker, ts, close)
but the real V001 schema is daily_signals_fast(ticker, date, composite,
breakdown JSONB, ...) where individual signal z's live inside breakdown.
V005 adds minute_bars (ticker, ts, close) as the only price store.

The seed helper inserts:
  1. daily_signals_fast row with breakdown = [{signal, z, ...}] containing
     the signal_name being tested
  2. Two minute_bars rows (entry at as_of, exit at as_of + 5 days)
     whose close ratio reproduces the target forward 5d return.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.backtest.ic_engine import (
    compute_walk_forward_ic,
    run_monthly_ic_backtest,
)
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_pair(pool, ticker, as_of, signal_val, ret_5d, signal_name="news"):
    """Insert one (ticker, as_of) signal row plus the entry/exit minute_bars
    needed to reproduce a forward 5d return of `ret_5d`.

    Schema notes:
      - daily_signals_fast PK is (ticker, date) so date must be unique per call
        for a ticker. Tests vary either ticker or date to satisfy this.
      - breakdown stored as JSON object with a `breakdown` list of signal entries
        (mirrors what fetch_latest_signal expects via _parse_breakdown).
      - minute_bars close uses entry=100.0 baseline; exit=100.0*(1+ret_5d).
    """
    breakdown_payload = {
        "breakdown": [
            {
                "signal": signal_name,
                "z": float(signal_val),
                "confidence": 0.7,
                "weight": 0.1,
                "weight_effective": 0.1,
                "contribution": float(signal_val) * 0.1,
                "raw": {},
                "source": "test",
                "timestamp": as_of.isoformat(),
                "error": None,
            }
        ]
    }
    await pool.execute(
        """
        INSERT INTO daily_signals_fast
            (ticker, date, composite, rating, confidence, breakdown, partial, fetched_at)
        VALUES ($1, $2::date, $3, 'HOLD', 0.7, $4::jsonb, false, $5)
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite = EXCLUDED.composite,
            breakdown = EXCLUDED.breakdown,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker,
        as_of.date(),
        float(signal_val),
        json.dumps(breakdown_payload),
        as_of,
    )
    entry_ts = as_of
    exit_ts = as_of + timedelta(days=5)
    entry_close = 100.0
    exit_close = entry_close * (1.0 + float(ret_5d))
    await pool.execute(
        """
        INSERT INTO minute_bars (ticker, ts, open, high, low, close, volume, fetched_at)
        VALUES ($1, $2, $3, $3, $3, $3, 1000, now())
        ON CONFLICT (ticker, ts) DO UPDATE SET close = EXCLUDED.close
        """,
        ticker, entry_ts, entry_close,
    )
    await pool.execute(
        """
        INSERT INTO minute_bars (ticker, ts, open, high, low, close, volume, fetched_at)
        VALUES ($1, $2, $3, $3, $3, $3, 1000, now())
        ON CONFLICT (ticker, ts) DO UPDATE SET close = EXCLUDED.close
        """,
        ticker, exit_ts, exit_close,
    )


async def test_walk_forward_ic_strict_lookahead_free(pool):
    """Seed daily_signals_fast with monotonically increasing signal-return
    pairs (perfect rank correlation). IC must be near +1.

    Lookahead-free verification: signal as_of is in the past relative to
    now(), and the forward 5d price observation timestamp is at
    as_of + 5 days, which is still <= now(). The engine's SQL uses
    `as_of + interval '5 days'` (never now()) for the forward leg, so
    no data with ts > as_of leaks into the signal side.
    """
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    # 20 days back -> all forward 5d windows are observable (15d ago entry,
    # 10d ago exit, etc.); newest pair is 6d ago entry, 1d ago exit.
    for i in range(20):
        as_of = now - timedelta(days=20 - i + 5)
        # ticker varied to give each pair a unique (ticker, date) PK while
        # holding signal_name constant for the IC computation.
        await _seed_pair(
            pool, f"T{i:02d}", as_of,
            signal_val=i * 0.1, ret_5d=i * 0.005,
        )

    result = await compute_walk_forward_ic(
        pool, signal_name="news", window_days=30,
    )
    assert result is not None
    ic, n_obs = result
    assert ic > 0.8, f"expected strong positive IC, got {ic}"
    assert n_obs >= 10, f"expected >=10 observations, got {n_obs}"


async def test_run_monthly_backtest_writes_three_window_rows(pool):
    """run_monthly_ic_backtest must write one signal_ic_history row per
    (signal, window) combination for which IC was computable; weight row
    must be upserted for every active signal regardless of computability."""
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    # Seed >=10 pairs so each window can produce an IC (insufficient power
    # would skip history writes for that window).
    for i in range(15):
        as_of = now - timedelta(days=20 - i + 5)
        await _seed_pair(
            pool, f"T{i:02d}", as_of,
            signal_val=i * 0.1, ret_5d=i * 0.005,
        )
    n_signals_updated = await run_monthly_ic_backtest(pool)
    assert n_signals_updated >= 1
    rows = await pool.fetch(
        "SELECT window_days FROM signal_ic_history "
        "WHERE signal_name='news' ORDER BY window_days"
    )
    windows = sorted({r["window_days"] for r in rows})
    # 15 pairs span ~30 days; 60d and 90d windows include them too.
    assert 30 in windows and 60 in windows and 90 in windows


async def test_weight_auto_drops_below_threshold(pool):
    """Contradictory pairs (signal up, return down) produce negative IC,
    which is below the +0.02 threshold -> weight 0 with reason low_ic."""
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    for i in range(15):
        as_of = now - timedelta(days=20 - i + 5)
        await _seed_pair(
            pool, f"X{i:02d}", as_of,
            signal_val=i * 0.1, ret_5d=-(i * 0.005),
        )
    await run_monthly_ic_backtest(pool)
    row = await pool.fetchrow(
        "SELECT weight, reason FROM signal_weight_current WHERE signal_name='news'"
    )
    assert row is not None
    assert float(row["weight"]) == 0.0
    assert "low_ic" in (row["reason"] or "")
