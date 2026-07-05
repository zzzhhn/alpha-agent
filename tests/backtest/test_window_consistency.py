# tests/backtest/test_window_consistency.py
#
# Integration tests for per-ticker windowed directional consistency against the
# ephemeral Postgres. `applied_db` is a DSN string; build a pool via get_pool
# (mirrors tests/backtest/test_ic_engine_daily_prices.py).
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.consistency import compute_window_consistency
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_prices(pool, ticker, start: date, closes: list[float]) -> None:
    """One daily_prices row per consecutive day; LEAD(close) over these rows is
    the next-trading-day close the consistency query uses."""
    for i, c in enumerate(closes):
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2,$3) "
            "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
            ticker, start + timedelta(days=i), c,
        )


async def _seed_pred(pool, ticker, d: date, rating: str) -> None:
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker, date, composite, rating, breakdown, fetched_at) "
        "VALUES ($1,$2,0.0,$3,$4::jsonb, now()) "
        "ON CONFLICT (ticker, date) DO UPDATE SET rating = EXCLUDED.rating",
        ticker, d, rating, json.dumps({"breakdown": []}),
    )


@pytest.mark.asyncio
async def test_windows_dash_and_realized_only(pool):
    # 30 strictly-increasing trading days -> every next-day return is positive,
    # so every BUY is a hit. Predictions BUY on days 0..28; a SELL on the latest
    # day 29 which has NO next day -> must be excluded (realized-only), leaving
    # hist a clean 1.0 rather than being dragged down by the un-realized miss.
    base = date.today() - timedelta(days=60)
    closes = [100.0 + i for i in range(30)]
    await _seed_prices(pool, "AAA", base, closes)
    for i in range(29):
        await _seed_pred(pool, "AAA", base + timedelta(days=i), "BUY")
    await _seed_pred(pool, "AAA", base + timedelta(days=29), "SELL")  # latest -> excluded

    c = (await compute_window_consistency(pool, ["AAA"]))["AAA"]
    assert c["d5"] == 1.0          # 4 realized of the last 5 sessions, all hits, >=3
    assert c["m1"] == 1.0          # 20 realized, all hits, >=10
    assert c["hist"] == 1.0        # 29 realized BUY hits; the day-29 SELL excluded
    assert c["y1"] is None         # ~29 samples < 120 -> dash, NOT silently == hist


@pytest.mark.asyncio
async def test_hit_fraction_and_hold_excluded(pool):
    # Strictly increasing prices again (every next day is up). Among the realized
    # predictions: 6 BUY (hits) + 2 SELL (misses) + 2 HOLD (excluded).
    # hist hit-rate must be 6/8 = 0.75, proving HOLD is dropped (not 6/10).
    base = date.today() - timedelta(days=60)
    await _seed_prices(pool, "MIX", base, [100.0 + i for i in range(12)])
    ratings = ["BUY", "BUY", "BUY", "BUY", "BUY", "BUY",
               "SELL", "SELL", "HOLD", "HOLD"]  # days 0..9 (all realized)
    for i, r in enumerate(ratings):
        await _seed_pred(pool, "MIX", base + timedelta(days=i), r)

    c = (await compute_window_consistency(pool, ["MIX"]))["MIX"]
    assert c["hist"] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_below_min_samples_is_dash(pool):
    # Only 2 realized predictions -> below every window's MIN_SAMPLES (d5>=3,
    # m1>=10, y1>=120, hist>=5) -> all dashes.
    base = date.today() - timedelta(days=30)
    await _seed_prices(pool, "THIN", base, [100.0, 101.0, 102.0])  # day2 = latest
    await _seed_pred(pool, "THIN", base, "BUY")
    await _seed_pred(pool, "THIN", base + timedelta(days=1), "BUY")

    c = (await compute_window_consistency(pool, ["THIN"]))["THIN"]
    assert c == {"d5": None, "m1": None, "y1": None, "hist": None}


async def _seed_slow(pool, ticker, d: date, composite_partial: float) -> None:
    await pool.execute(
        "INSERT INTO daily_signals_slow (ticker, date, composite_partial, breakdown, fetched_at) "
        "VALUES ($1,$2,$3,$4::jsonb, now()) "
        "ON CONFLICT (ticker, date) DO UPDATE "
        "SET composite_partial = EXCLUDED.composite_partial",
        ticker, d, composite_partial, json.dumps({"breakdown": []}),
    )


@pytest.mark.asyncio
async def test_slow_only_history_counts(pool):
    """The all-dash bug: a long-tail ticker whose prediction history lives ONLY in
    daily_signals_slow (no fast rows) must still get consistency numbers — its
    tier derives from composite_partial via map_to_tier (default thresholds:
    >0.5 -> OW up-call). 10 slow OW days over rising prices = all hits."""
    base = date.today() - timedelta(days=40)
    await _seed_prices(pool, "SLOWY", base, [100.0 + i for i in range(12)])
    for i in range(10):
        await _seed_slow(pool, "SLOWY", base + timedelta(days=i), 1.0)  # OW

    c = (await compute_window_consistency(pool, ["SLOWY"]))["SLOWY"]
    assert c["hist"] == 1.0     # 10 realized OW hits (was all-None before the fix)
    assert c["m1"] == 1.0       # >= 10 samples inside the month window
    # near-zero partial composite maps to HOLD -> still excluded
    await _seed_slow(pool, "SLOWY", base + timedelta(days=10), 0.0)
    c2 = (await compute_window_consistency(pool, ["SLOWY"]))["SLOWY"]
    assert c2["hist"] == 1.0    # the HOLD day added no sample


@pytest.mark.asyncio
async def test_fast_preferred_over_slow_same_day(pool):
    """When BOTH tables have a row for the same (ticker, date), the fast row's
    stored rating is authoritative: 6 days where fast says SELL (all misses on
    rising prices) while slow says OW (would be hits) must score 0.0, not 1.0."""
    base = date.today() - timedelta(days=40)
    await _seed_prices(pool, "BOTH", base, [100.0 + i for i in range(8)])
    for i in range(6):
        d = base + timedelta(days=i)
        await _seed_pred(pool, "BOTH", d, "SELL")   # fast: down-call -> miss
        await _seed_slow(pool, "BOTH", d, 1.0)      # slow: would be OW hit

    c = (await compute_window_consistency(pool, ["BOTH"]))["BOTH"]
    assert c["hist"] == 0.0  # fast won the dedup; slow row did not double-count


@pytest.mark.asyncio
async def test_unknown_ticker_all_none(pool):
    c = await compute_window_consistency(pool, ["NOPE"])
    assert c["NOPE"] == {"d5": None, "m1": None, "y1": None, "hist": None}


@pytest.mark.asyncio
async def test_empty_tickers_returns_empty(pool):
    assert await compute_window_consistency(pool, []) == {}
