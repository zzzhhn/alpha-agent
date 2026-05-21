# tests/backtest/test_confidence_calibration_db.py
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.confidence_calibration import _hit, gather_confidence_hits
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def test_hit_direction_rules():
    assert _hit("BUY", 0.03) is True      # up call, up return
    assert _hit("OW", -0.01) is False     # up call, down return
    assert _hit("SELL", -0.02) is True    # down call, down return
    assert _hit("UW", 0.01) is False      # down call, up return
    assert _hit("HOLD", 0.05) is None     # excluded
    assert _hit("BUY", 0.0) is False      # exactly flat is not "up"


async def _seed(pool, ticker, as_of, rating, confidence, fwd_pct):
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker,date,composite,rating,confidence,breakdown,fetched_at) "
        "VALUES ($1,$2::date,0.0,$3,$4,$5::jsonb,now()) "
        "ON CONFLICT (ticker,date) DO UPDATE SET rating=EXCLUDED.rating, confidence=EXCLUDED.confidence",
        ticker, as_of, rating, confidence, json.dumps({"breakdown": []}),
    )
    closes = [100, 100, 100, 100, 100, 100 * (1 + fwd_pct)]
    for i, c in enumerate(closes):
        await pool.execute(
            "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, as_of + timedelta(days=i), c,
        )


@pytest.mark.asyncio
async def test_gather_excludes_hold_and_pairs_confidence_with_hit(pool):
    base = date.today() - timedelta(days=30)
    await _seed(pool, "AAA", base, "BUY", 0.8, 0.05)    # hit  (conf 0.8)
    await _seed(pool, "BBB", base, "SELL", 0.6, 0.04)   # miss (conf 0.6, up vs down call)
    await _seed(pool, "CCC", base, "HOLD", 0.9, 0.05)   # excluded
    pairs = await gather_confidence_hits(pool, window_days=90)
    by_conf = {round(c, 2): h for c, h in pairs}
    assert 0.8 in by_conf and by_conf[0.8] == 1   # BUY hit -> 1
    assert 0.6 in by_conf and by_conf[0.6] == 0   # SELL miss -> 0
    assert 0.9 not in by_conf                      # HOLD excluded


# ---------------------------------------------------------------------------
# T5: run_calibration orchestrator + load_active_calibration
# ---------------------------------------------------------------------------
from alpha_agent.backtest.confidence_calibration import (  # noqa: E402
    load_active_calibration,
    run_calibration,
)


@pytest.mark.asyncio
async def test_run_calibration_stores_applied_map_when_enough_pairs(pool):
    base = date.today() - timedelta(days=30)
    # 60 overconfident pairs: BUY at confidence 0.9 but only ~half hit.
    for i in range(60):
        rating = "BUY" if i % 2 == 0 else "SELL"
        # BUY with negative return = miss; SELL with negative = hit -> ~50% hit at conf 0.9
        await _seed(pool, f"T{i:02d}", base, rating, 0.9, -0.02)
    res = await run_calibration(pool)
    assert res["n_pairs"] >= 50 and res["applied"] is True
    cal = await load_active_calibration(pool)
    assert cal is not None and cal["x"]
    # The active map suppresses the overconfident 0.9 region.
    from alpha_agent.backtest.confidence_calibration import apply_calibration
    assert apply_calibration(0.9, cal) < 0.9


@pytest.mark.asyncio
async def test_run_calibration_identity_when_too_few_pairs(pool):
    base = date.today() - timedelta(days=30)
    await _seed(pool, "AAA", base, "BUY", 0.8, 0.05)  # 1 pair, < MIN_PAIRS
    res = await run_calibration(pool)
    assert res["applied"] is False
    assert await load_active_calibration(pool) is None  # nothing applied yet


# ---------------------------------------------------------------------------
# T6: calibrated_confidence on live read path
# ---------------------------------------------------------------------------
from alpha_agent.fusion.rating import calibrated_confidence, compute_confidence  # noqa: E402


@pytest.mark.asyncio
async def test_calibrated_confidence_suppresses_via_active_map(pool):
    base = date.today() - timedelta(days=30)
    for i in range(60):
        rating = "BUY" if i % 2 == 0 else "SELL"
        await _seed(pool, f"T{i:02d}", base, rating, 0.9, -0.02)
    await run_calibration(pool)
    cal = await load_active_calibration(pool)
    zs = [3.0, 3.0, 3.0]  # high-agreement z's -> high raw confidence
    raw = compute_confidence(zs)
    calibrated = calibrated_confidence(zs, cal)
    assert calibrated <= raw  # suppress-only: never inflates
