# Portfolio-level picks scoreboard: daily top/bottom-K baskets from stored
# rankings (no lookahead) vs universe average + always-up base rate.
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.scoreboard import compute_picks_scoreboard
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, ticker, start: date, closes: list[float], score: float):
    for i, c in enumerate(closes):
        d = start + timedelta(days=i)
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2,$3) "
            "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
            ticker, d, c,
        )
        await pool.execute(
            "INSERT INTO daily_signals_slow (ticker, date, composite_partial, breakdown, fetched_at) "
            "VALUES ($1,$2,$3,$4::jsonb, now()) ON CONFLICT (ticker, date) DO NOTHING",
            ticker, d, score, json.dumps({"breakdown": []}),
        )


@pytest.mark.asyncio
async def test_scoreboard_separates_top_from_bottom(pool):
    """12 names, 6 price days (5 realized). Ranking is deterministic: the top-3
    by stored score rise 1%/day, the bottom-3 fall 1%/day, the middle 6 are
    flat. The scoreboard must show long > market > short, positive spread, long
    hit-rate 1.0, and base rate 15/60 (only the 3 risers' 5 realized days rose)."""
    base = date.today() - timedelta(days=30)
    n_days = 6
    for i in range(12):
        score = float(12 - i)  # T01 ranks top, T12 bottom
        if i < 3:
            closes = [100.0 * (1.01 ** k) for k in range(n_days)]      # +1%/day
        elif i >= 9:
            closes = [100.0 * (0.99 ** k) for k in range(n_days)]      # -1%/day
        else:
            closes = [100.0] * n_days                                   # flat
        await _seed(pool, f"T{i:02d}", base, closes, score)

    sb = await compute_picks_scoreboard(pool, top_n=3, days=21)
    assert sb is not None
    assert sb.days == 5 and sb.top_n == 3
    assert sb.long_cum == pytest.approx(1.01 ** 5 - 1, rel=1e-6)
    assert sb.short_cum == pytest.approx(0.99 ** 5 - 1, rel=1e-6)
    assert sb.market_cum == pytest.approx((1 + (0.01 * 3 - 0.01 * 3) / 12) ** 5 - 1, abs=1e-4)
    assert sb.spread_cum > 0.09          # ~ (1.02)^5 - 1
    assert sb.long_hit_rate == 1.0       # every long stock-day rose
    assert sb.base_rate == pytest.approx(15 / 60)


@pytest.mark.asyncio
async def test_scoreboard_none_without_history(pool):
    assert await compute_picks_scoreboard(pool, top_n=10, days=21) is None
