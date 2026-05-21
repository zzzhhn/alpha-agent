# tests/backtest/test_adaptive_weights_orchestration.py
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import apply_adaptive_weights
from alpha_agent.storage.postgres import close_pool, get_pool

SIGNALS = ("siga", "sigb")


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_ic(pool, signal, window, ics, start):
    for i, ic in enumerate(ics):
        await pool.execute(
            "INSERT INTO signal_ic_history (signal_name, window_days, ic, n_observations, computed_at) "
            "VALUES ($1,$2,$3,50,$4) ON CONFLICT DO NOTHING",
            signal, window, ic,
            datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i),
        )


async def _seed_market(pool):
    base = date.today() - timedelta(days=40)
    for k in range(12):
        za = (k - 5.5) / 6.0
        await pool.execute(
            "INSERT INTO daily_signals_fast (ticker,date,composite,breakdown,fetched_at) "
            "VALUES ($1,$2::date,0.0,$3::jsonb,now()) ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
            f"T{k:02d}", base,
            json.dumps({"breakdown": [{"signal": "siga", "z": za}, {"signal": "sigb", "z": 0.0}]}),
        )
        closes = [100, 100, 100, 100, 100, 100 * (1 + za * 0.1)]
        for i, c in enumerate(closes):
            await pool.execute(
                "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
                "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
                f"T{k:02d}", base + timedelta(days=i), c,
            )


@pytest.mark.asyncio
async def test_cold_start_seeds_live_from_candidate(pool):
    start = date.today() - timedelta(days=10)
    await _seed_ic(pool, "siga", 30, [0.10, 0.12, 0.11, 0.13, 0.12], start)
    await _seed_ic(pool, "sigb", 30, [0.01, -0.01, 0.0, 0.02, -0.02], start)
    await _seed_market(pool)
    res = await apply_adaptive_weights(pool, SIGNALS)
    assert res["promoted"] is True
    live = await pool.fetch("SELECT signal_name, weight FROM signal_weight_current WHERE status='live'")
    by = {r["signal_name"]: float(r["weight"]) for r in live}
    assert by["siga"] > by["sigb"]


@pytest.mark.asyncio
async def test_shadow_does_not_become_live_until_streak(pool):
    start = date.today() - timedelta(days=10)
    await _seed_ic(pool, "siga", 30, [0.10, 0.12, 0.11, 0.13, 0.12], start)
    await _seed_ic(pool, "sigb", 30, [0.05, 0.06, 0.05, 0.06, 0.05], start)
    await _seed_market(pool)
    await apply_adaptive_weights(pool, SIGNALS)  # cold start seeds live
    live_before = await pool.fetchval(
        "SELECT weight FROM signal_weight_current WHERE signal_name='siga' AND status='live'")
    res = await apply_adaptive_weights(pool, SIGNALS)  # streak now 1, < 5
    assert res["promoted"] is False
    live_after = await pool.fetchval(
        "SELECT weight FROM signal_weight_current WHERE signal_name='siga' AND status='live'")
    assert float(live_after) == pytest.approx(float(live_before))
    shadow_exists = await pool.fetchval(
        "SELECT count(*) FROM signal_weight_current WHERE signal_name='siga' AND status='shadow'")
    assert shadow_exists == 1


from alpha_agent.backtest.adaptive_weights import _maybe_rollback  # noqa: E402


async def _set_live(pool, weights):
    for sig, w in weights.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name,status,weight,last_updated,reason) "
            "VALUES ($1,'live',$2,now(),'seed') "
            "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight",
            sig, w,
        )


@pytest.mark.asyncio
async def test_rollback_fires_when_live_ic_degrades_below_baseline(pool):
    await _seed_market(pool)  # siga drives the return; sigb is noise
    # Live currently weights ONLY the noise signal -> low composite IC.
    await _set_live(pool, {"siga": 0.0, "sigb": 0.20})
    # A prior promotion claimed baseline_ic=0.95, old_value = the good weights.
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0,'signal_weights',$1,$2,'auto_promote')",
        json.dumps({"siga": 0.20, "sigb": 0.0}),
        json.dumps({"weights": {"siga": 0.0, "sigb": 0.20}, "baseline_ic": 0.95}),
    )
    rolled = await _maybe_rollback(pool)
    assert rolled is True
    live = {r["signal_name"]: float(r["weight"]) for r in await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status='live'")}
    assert live["siga"] == pytest.approx(0.20)  # restored to the good weights
    journ = await pool.fetchrow(
        "SELECT rollback_of, source FROM config_change_log WHERE source='auto_rollback'")
    assert journ is not None and journ["rollback_of"] is not None


@pytest.mark.asyncio
async def test_no_rollback_within_tolerance(pool):
    await _seed_market(pool)
    await _set_live(pool, {"siga": 0.20, "sigb": 0.0})  # good weights -> high IC
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0,'signal_weights',$1,$2,'auto_promote')",
        json.dumps({"siga": 0.10, "sigb": 0.0}),
        json.dumps({"weights": {"siga": 0.20, "sigb": 0.0}, "baseline_ic": 0.95}),
    )
    assert await _maybe_rollback(pool) is False
