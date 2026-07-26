# tests/backtest/test_hold_inclusive_consistency.py
#
# Integration tests for the HOLD-inclusive consistency 口径
# (compute_hold_inclusive_consistency), alongside the existing
# directional-only compute_window_consistency. Mirrors
# tests/backtest/test_window_consistency.py's fixture/seeding pattern
# against the ephemeral Postgres.
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.consistency import (
    _fetch_live_outcomes,
    compute_hold_inclusive_consistency,
)
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_prices(pool, ticker, start: date, closes: list[float]) -> None:
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
async def test_hold_hit_within_band_miss_outside_band(pool):
    # 3 realized HOLD predictions: +0.4% (inside +-0.5% -> hit), ~+1.0% (outside
    # -> miss), 0% (inside -> hit). Combined rate must be 2/3, proving the band
    # is applied per-row rather than as an all-or-nothing gate.
    base = date.today() - timedelta(days=30)
    await _seed_prices(pool, "HOLDA", base, [100.0, 100.4, 101.4, 101.4])
    for i in range(3):
        await _seed_pred(pool, "HOLDA", base + timedelta(days=i), "HOLD")

    rates, ns = await compute_hold_inclusive_consistency(pool, ["HOLDA"])
    assert ns["HOLDA"]["d5"] == 3
    assert rates["HOLDA"]["d5"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_combined_directional_and_hold_rate(pool):
    # BUY (hit) + SELL (miss) + 2 HOLD (1 hit inside band, 1 miss outside) ->
    # combined 2 hits / 4 evaluated = 0.5, proving HOLD hits/misses are pooled
    # with directional hits/misses over ONE combined n, not tracked separately.
    base = date.today() - timedelta(days=30)
    await _seed_prices(
        pool, "MIXH", base, [100.0, 100.4, 101.4, 101.4, 102.4]
    )
    await _seed_pred(pool, "MIXH", base, "BUY")                          # +0.4% -> hit
    await _seed_pred(pool, "MIXH", base + timedelta(days=1), "HOLD")     # ~+1.0% -> miss (outside band)
    await _seed_pred(pool, "MIXH", base + timedelta(days=2), "HOLD")     # 0% -> hit (inside band)
    await _seed_pred(pool, "MIXH", base + timedelta(days=3), "SELL")     # ~+1.0% -> miss

    rates, ns = await compute_hold_inclusive_consistency(pool, ["MIXH"])
    assert ns["MIXH"]["d5"] == 4
    assert rates["MIXH"]["d5"] == pytest.approx(0.5)
    # Below MIN_SAMPLES["m1"]=10 with only 4 evaluated -> dash, not a number.
    assert ns["MIXH"]["m1"] == 4
    assert rates["MIXH"]["m1"] is None


@pytest.mark.asyncio
async def test_y1_and_hist_always_none(pool):
    # Even with plenty of realized HOLD hits, y1/hist are structurally
    # unavailable (no durable HOLD history + pruned raw signals past 30d) and
    # must always report None, never a computed number.
    base = date.today() - timedelta(days=30)
    await _seed_prices(pool, "LONGH", base, [100.0 + 0.1 * i for i in range(15)])
    for i in range(14):
        await _seed_pred(pool, "LONGH", base + timedelta(days=i), "HOLD")

    rates, ns = await compute_hold_inclusive_consistency(pool, ["LONGH"])
    assert rates["LONGH"]["y1"] is None
    assert rates["LONGH"]["hist"] is None
    assert ns["LONGH"]["y1"] == 0
    assert ns["LONGH"]["hist"] == 0


@pytest.mark.asyncio
async def test_below_min_samples_is_dash(pool):
    # Only 2 realized HOLD predictions -> below MIN_SAMPLES["d5"]=3 -> dash.
    base = date.today() - timedelta(days=20)
    await _seed_prices(pool, "THINH", base, [100.0, 100.2, 100.2])
    await _seed_pred(pool, "THINH", base, "HOLD")
    await _seed_pred(pool, "THINH", base + timedelta(days=1), "HOLD")

    rates, ns = await compute_hold_inclusive_consistency(pool, ["THINH"])
    assert ns["THINH"]["d5"] == 2
    assert rates["THINH"]["d5"] is None


@pytest.mark.asyncio
async def test_hold_band_none_keeps_hold_excluded_regression(pool):
    # Default hold_band=None must stay byte-identical to the pre-existing
    # directional-only behavior: HOLD rows are dropped entirely, not scored.
    base = date.today() - timedelta(days=20)
    await _seed_prices(pool, "REGR", base, [100.0, 100.4, 101.4])
    await _seed_pred(pool, "REGR", base, "HOLD")
    await _seed_pred(pool, "REGR", base + timedelta(days=1), "HOLD")

    out = await _fetch_live_outcomes(pool, ["REGR"])
    assert out == []


@pytest.mark.asyncio
async def test_empty_tickers_returns_empty(pool):
    rates, ns = await compute_hold_inclusive_consistency(pool, [])
    assert rates == {}
    assert ns == {}
