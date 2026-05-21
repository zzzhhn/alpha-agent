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
