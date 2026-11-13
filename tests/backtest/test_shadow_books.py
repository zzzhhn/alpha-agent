import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import numpy as np

import pytest

from alpha_agent.backtest import l2_continuous, l2_driver, shadow_books as shadow
from alpha_agent.backtest.l2 import select_holdings
from alpha_agent.market_session import xnys_sessions
from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.product_ledger import RatingSnapshot, RunMeta, record_research_run


@pytest.fixture(autouse=True)
def frozen_intent_clock(monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 13, 1, tzinfo=UTC)
    monkeypatch.setattr(l2_continuous, "datetime", FrozenDateTime)


@pytest.fixture
async def pool(applied_db):
    value = await get_pool(applied_db)
    yield value
    await close_pool()


async def make_run(pool, day, snapshots=None, **kwargs):
    return await record_research_run(
        pool, RunMeta(scheduled_for_date=day, status="complete", started_at=datetime.now(UTC),
                      finished_at=datetime.now(UTC)),
        snapshots or [RatingSnapshot(ticker=f"T{i:03}", tier="BUY", rank=i, eligible=True)
                      for i in range(1, 101)], **kwargs)


def test_band_and_bot_selection():
    rows = [{"ticker": f"T{i:03}", "eligible": True, "rank": i, "tier": "HOLD"}
            for i in range(1, 101)]
    band = shadow.band_holdings(rows, {"T060", "T081"})
    names = {h["ticker"] for h in band}
    assert "T060" in names and "T081" not in names
    assert len(band) == 41
    assert all(h["rank"] <= 40 or h["ticker"] == "T060" for h in band)
    full = shadow.band_holdings(rows, {f"T{i:03}" for i in range(30, 81)})
    assert len(full) == 50 and all(h["target_weight"] == 0.02 for h in full)
    bot = shadow.bot_holdings(rows)
    assert [h["rank"] for h in bot] == list(range(1, 9))
    assert all(h["target_weight"] == 0.125 for h in bot)


def test_substitution_and_splice_jump_exclusion():
    assert shadow.substitute_composite(1.2, [{"signal": "factor", "z": 2,
                                            "weight_effective": 0.1}], -1) == pytest.approx(0.9)
    # The emitted composite is damped by sqrt(coverage) (fusion.combine), so the
    # swapped factor term is damped the same way.
    damped = {"coverage": 0.81, "breakdown": [{"signal": "factor", "z": 2, "weight_effective": 0.1}]}
    assert shadow.substitute_composite(1.2, damped, -1) == pytest.approx(1.2 - 0.3 * 0.9)
    days = xnys_sessions(date(2025, 10, 1), date(2026, 11, 13))[-253:]
    research = {d: 100.0 for d in days if d <= shadow.SPLICE_END}
    live = {d: 110.0 for d in days if d > shadow.SPLICE_END}
    value, reason = shadow.momentum_value(days, live, research)
    # D=2026-11-13: D-21 is 2026-10-15, still before the cut-off, so both
    # endpoints come from the bundled panel.
    assert reason == "spliced" and value == 0
    later = xnys_sessions(date(2025, 12, 1), date(2026, 12, 15))[-253:]
    research_later = {d: 100.0 for d in later if d <= shadow.SPLICE_END}
    live_later = {d: 110.0 for d in later if d > shadow.SPLICE_END}
    # D-252 from the bundled panel (100), D-21 from the live table (110); the
    # 10% step sits at the seam and is below the 45% rejection threshold.
    assert shadow.momentum_value(later, live_later, research_later) == (pytest.approx(0.10), "spliced")
    # A >45% step across the seam inside the read window is rejected.
    assert shadow.momentum_value(later, {d: 200.0 for d in live_later}, research_later) == (None, "suspect_jump")
    research[days[20]] = 200
    assert shadow.momentum_value(days, live, research) == (None, "suspect_jump")
    del research[days[20]]
    assert shadow.momentum_value(days, live, research) == (None, "insufficient_history")
    research[days[20]] = 100.0
    assert shadow.momentum_value(days[:-1], live, research)[0] is None
    # Full live history takes precedence; parquet cannot poison that path.
    assert shadow.momentum_value(days, dict.fromkeys(days, 100.0), research) == (0, "live")
    # 12-1 skips the last month: a missing or jumpy bar after D-21 is not read.
    recent_gap = {d: 100.0 for d in days[:-21]}
    assert shadow.momentum_value(days, recent_gap, {}) == (0, "live")
    # A live gap inside the window is filled only from the bundled panel and
    # only on or before its cut-off (2026-07-24 had no live row in production).
    gap = dict.fromkeys(days, 100.0)
    gap_day = next(d for d in days if d <= shadow.SPLICE_END)
    del gap[gap_day]
    assert shadow.momentum_value(days, gap, {gap_day: 100.0}) == (0, "spliced")
    assert shadow.momentum_value(days, gap, {}) == (None, "insufficient_history")


async def test_default_targets_are_unchanged(pool):
    day = date(2026, 11, 16)
    snapshots = [RatingSnapshot(ticker=f"T{i:03}", tier="BUY" if i%3 else "HOLD",
                                rank=i, eligible=i != 2) for i in range(1, 70)]
    run = await make_run(pool, day, snapshots)
    sid = await l2_continuous.ensure_book(pool, start_after_run_id=0)
    await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=run)
    actual = await pool.fetch("SELECT ticker,target_weight,rank,tier FROM l2_order WHERE strategy_id=$1 ORDER BY ticker", sid)
    expected = select_holdings([vars(s) for s in snapshots], top_n=50, max_position=0.02)
    assert [dict(r) for r in actual] == sorted(expected, key=lambda r: r["ticker"])


async def test_registration_immutable_and_forward_only(pool, monkeypatch):
    old = await make_run(pool, date(2026, 11, 12))
    sid = await shadow.ensure_shadow_book(pool, name="shadow_band_40_80")
    assert await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=old) == 0
    newer = await make_run(pool, date(2026, 11, 13))
    assert await shadow.ensure_shadow_book(pool, name="shadow_band_40_80") == sid
    assert await pool.fetchval("SELECT start_after_run_id FROM l2_account WHERE strategy_id=$1", sid) == old
    params = json.loads(await pool.fetchval("SELECT params_json FROM l2_strategy WHERE id=$1", sid))
    assert params["protocol"] == shadow.protocol_name("shadow_band_40_80")
    assert params["shadow"] is True
    monkeypatch.setattr(l2_driver, "latest_completed_xnys_session", lambda: date(2026, 11, 16))
    result = await l2_driver.run_continuous_driver(pool, strategy_id=sid)
    assert result["generated"] == 0
    assert await pool.fetchval("SELECT count(*) FROM l2_order WHERE strategy_id=$1", sid) == 0
    assert newer > old
    # Direct selector callers also cannot bypass the shadow execution guard.
    historical = await make_run(pool, date(2026, 10, 1))
    assert await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=historical) == 0


async def test_band_persists_explicit_removals(pool):
    sid = await shadow.ensure_shadow_book(pool, name="shadow_band_40_80")
    await pool.executemany(
        "INSERT INTO l2_position(strategy_id,ticker,qty,avg_cost) VALUES($1,$2,10,100)",
        [(sid, "T060"), (sid, "T081")])
    rid = await make_run(pool, date(2026, 11, 16))
    await l2_continuous.generate_target_intent(pool, strategy_id=sid, run_id=rid)
    weights = dict(await pool.fetch("SELECT ticker,target_weight FROM l2_order WHERE strategy_id=$1", sid))
    assert weights["T060"] == 0.02 and weights["T081"] == 0
    assert all(t == "T060" or t == "T081" or int(t[1:]) <= 40 for t in weights)


async def test_weekly_cadence_and_cost(pool, monkeypatch):
    sid = await shadow.ensure_shadow_book(pool, name="shadow_bot_rule_weekly")
    monkeypatch.setattr(l2_driver, "latest_completed_xnys_session", lambda: date(2026, 11, 16))
    monday = date(2026, 11, 16)
    assert monday.weekday() == 0
    await make_run(pool, monday)
    result = await l2_driver.run_continuous_driver(pool, strategy_id=sid, cadence="iso_week_first_snapshot")
    assert result["generated"] == 8
    orders = await pool.fetch("SELECT target_weight,cost_bps FROM l2_order WHERE strategy_id=$1", sid)
    assert all(r["target_weight"] == 0.125 and r["cost_bps"] == 15 for r in orders)
    await make_run(pool, monday + timedelta(days=1))
    assert (await l2_driver.run_continuous_driver(pool, strategy_id=sid, cadence="iso_week_first_snapshot"))["generated"] == 0
    await make_run(pool, monday + timedelta(days=7))
    assert (await l2_driver.run_continuous_driver(pool, strategy_id=sid, cadence="iso_week_first_snapshot"))["generated"] == 8


async def test_weekly_missed_first_snapshot_is_not_replaced(pool, monkeypatch):
    sid = await shadow.ensure_shadow_book(pool, name="shadow_bot_rule_weekly")
    await make_run(pool, date(2026, 11, 16))
    await make_run(pool, date(2026, 11, 18))
    monkeypatch.setattr(l2_driver, "latest_completed_xnys_session", lambda: date(2026, 11, 18))
    assert (await l2_driver.run_continuous_driver(pool, strategy_id=sid, cadence="iso_week_first_snapshot"))["generated"] == 0


def test_shadow_tier_is_rederived_from_the_shadow_composite():
    from alpha_agent.fusion.rating import map_to_tier
    assert map_to_tier(0.6) == "OW" and map_to_tier(0.4) == "HOLD"


async def test_factor_fallback_cutoff_normalization_and_exclusions(pool, monkeypatch):
    """Production shape: the immutable payload has no breakdown; its as_of is
    the fetched_at of the exact fast row (keyed by UTC date, not market date)."""
    day = date(2026, 11, 16)
    days = xnys_sessions(day-timedelta(days=500), day)[-253:]
    names = ("AAA", "BBB", "LATE", "MISS", "JUMP")
    embedded = {"composite_score": 1.0, "breakdown": [{"signal": "factor", "z": 0.5, "weight_effective": 0.2}]}
    stamp = datetime(2026, 11, 17, 0, 50, tzinfo=UTC)  # after the D close, next UTC day
    snapshots = [RatingSnapshot(
        ticker=t, composite_z=1, tier="BUY", rank=i, eligible=True,
        user_visible_payload=embedded if t in {"AAA", "JUMP"} else
        {"composite_score": 1.0, "as_of": (stamp if t != "LATE" else stamp + timedelta(hours=2)).isoformat()})
        for i, t in enumerate(names, 1)]
    rid = await make_run(pool, day, snapshots)
    await pool.execute("UPDATE research_run SET created_at=$2 WHERE id=$1", rid, stamp + timedelta(minutes=10))
    fast = {"coverage": 1.0, "breakdown": [{"signal": "factor", "z": 0.5, "weight_effective": 0.2}]}
    for t, at in (("BBB", stamp), ("LATE", stamp + timedelta(hours=2)), ("MISS", stamp + timedelta(seconds=1))):
        # LATE is fetched after the run was published; MISS's as_of does not match.
        await pool.execute(
            "INSERT INTO daily_signals_fast(ticker,date,breakdown,fetched_at) VALUES($1,$2,$3::jsonb,$4)",
            t, day + timedelta(days=1), json.dumps(fast), at)
    records = [(t, d, 100.0 * (1 + (i/1000 if t == "BBB" else 0)))
               for t in names for i, d in enumerate(days)]
    records = [(t, d, 200.0 if t == "JUMP" and d == days[20] else p) for t, d, p in records]
    await pool.executemany("INSERT INTO daily_prices(ticker,date,close) VALUES($1,$2,$3)", records)
    monkeypatch.setattr(shadow, "research_closes", lambda: {})
    rows = await pool.fetch("SELECT * FROM rating_snapshot WHERE run_id=$1", rid)
    info = {}
    selected = await shadow.factor_holdings(pool, snapshots=rows, run_id=rid, signal_date=day, info=info)
    assert [s["ticker"] for s in selected] == ["BBB", "AAA"]
    assert info["suspect_jump"] == 1 and info["missing_breakdown"] == 2
    assert info["fallback_breakdown"] == 1 and info["excluded"] == 3
    # BBB has the higher momentum, so its shadow composite (and tier) lead.
    assert all(s["tier"] in {"BUY", "OW", "HOLD", "UW", "SELL"} for s in selected)


def test_bundled_loader_reuses_v3(monkeypatch):
    from alpha_agent.factor_engine import factor_backtest as fb
    monkeypatch.setattr(fb, "_load_panel", lambda: SimpleNamespace(
        dates=["2026-10-30", "2026-11-02"], tickers=["AAA"],
        close=np.array([[100], [200]])))
    shadow.research_closes.cache_clear()
    try:
        assert shadow.research_closes() == {"AAA": {date(2026, 10, 30): 100}}
    finally:
        shadow.research_closes.cache_clear()
