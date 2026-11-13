from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.scheduling.ticks import (
    FAST_OFFSETS,
    PRICE_PASS_SPACING_MINUTES,
    next_unit,
    scheduled_slot,
    within_research_day,
)

DAY = "2026-11-11"
NOW = datetime(2026, 11, 11, 22, 30, tzinfo=UTC)
CLOSE = NOW.replace(hour=21, minute=0)
OFFSETS = (0, 75, 150)


def prices_done(price_pass=1):
    return [receipt("daily_prices", o, price_pass=price_pass) for o in OFFSETS]


def receipt(unit, offset=None, *, ok=True, slot=DAY, **extra):
    return {"unit": unit, "offset": offset, "ok": ok, "slot": slot,
            "research_day": DAY, **extra}


def daily(rows=(), **kwargs):
    params = dict(now=NOW, research_day=DAY, slot=DAY, receipts=list(rows),
                  market_close=CLOSE, ready=True, price_universe_count=151)
    params.update(kwargs)
    return next_unit("daily_close", **params)


def test_daily_order_and_completed_offsets():
    # The first price pass always covers the whole universe, even when ready.
    assert (daily().unit.name, daily().unit.offset) == ("daily_prices", 0)
    rows = prices_done()
    assert daily(rows).unit.name == "ic_backtest_monthly"
    rows.append(receipt("ic_backtest_monthly"))
    for offset in FAST_OFFSETS:
        assert daily(rows).unit.offset == offset
        assert daily(rows).unit.name == "fast_intraday"
        rows.append(receipt("fast_intraday", offset))
    assert daily(rows).unit.name == "publish_recommendation"
    rows.append(receipt("publish_recommendation", ok=False))
    assert daily(rows).unit.name == "l2_cycle"
    rows.append(receipt("l2_cycle"))
    assert daily(rows).reason == "complete"


def test_l2_is_attempted_once_even_when_it_fails():
    rows = prices_done() + [receipt("ic_backtest_monthly")] + [
        receipt("fast_intraday", o) for o in FAST_OFFSETS] + [
        receipt("publish_recommendation"), receipt("l2_cycle", ok=False)]
    assert daily(rows).reason == "l2_attempted"


@pytest.mark.parametrize("missing", FAST_OFFSETS)
def test_publish_needs_all_six_successful_shards(missing):
    rows = prices_done() + [receipt("ic_backtest_monthly")] + [
        receipt("fast_intraday", o, ok=o != missing) for o in FAST_OFFSETS]
    assert daily(rows).unit.name == "fast_intraday"
    assert daily(rows).unit.offset == missing


def test_readiness_gate_is_not_bypassed_by_successful_shards():
    rows = prices_done() + [receipt("ic_backtest_monthly")] + [
        receipt("fast_intraday", o) for o in FAST_OFFSETS]
    plan = daily(rows, ready=False)
    assert (plan.unit.name, plan.unit.price_pass) == ("daily_prices", 2)


def test_prices_wait_for_settled_close():
    assert daily(now=CLOSE.replace(minute=30), ready=False).reason == "awaiting_settled_close"
    assert daily(now=CLOSE.replace(minute=30)).reason == "awaiting_settled_close"


def test_price_passes_are_spaced_and_capped_then_l2_still_values():
    rows = []
    at = NOW
    for pass_no in range(1, 4):
        for offset in OFFSETS:
            unit = daily(rows, ready=False, now=at).unit
            assert (unit.name, unit.offset, unit.limit, unit.price_pass) == (
                "daily_prices", offset, 75, pass_no)
            rows.append(receipt("daily_prices", offset, price_pass=pass_no,
                                observed_at=at.isoformat()))
        if pass_no < 3:
            soon = at + timedelta(minutes=PRICE_PASS_SPACING_MINUTES - 1)
            assert daily(rows, ready=False, now=soon).reason == "awaiting_next_price_pass"
            at = at + timedelta(minutes=PRICE_PASS_SPACING_MINUTES)
    # Coverage never arrived: no research, but holdings are still valued.
    assert daily(rows, ready=False, now=at).unit.name == "l2_cycle"
    assert daily(rows, now=at).unit.name == "ic_backtest_monthly"


def test_failure_budget_counts_units_across_slots_but_not_controls_or_other_days():
    rows = [receipt("fast_intraday", o, ok=False, slot=str(o)) for o in (0, 40, 80)]
    # daily_close: budget spent -> skip research, still value holdings once.
    assert daily(rows).unit.name == "l2_cycle"
    assert next_unit("fast_tech", now=NOW.replace(hour=15, minute=30), research_day=DAY,
                     slot="x", receipts=rows).reason == "failure_budget_exhausted"
    rows[-1]["research_day"] = "2026-11-10"
    rows.extend([receipt(None, ok=False) for _ in range(4)])
    rows.append(receipt("publish_recommendation", ok=False, slot="other"))
    assert daily(rows).unit.name == "daily_prices"


@pytest.mark.parametrize("instant", [NOW.replace(hour=20, minute=0), NOW.replace(hour=23, minute=56), NOW + timedelta(days=1)])
def test_close_and_utc_day_guard(instant):
    assert daily(now=instant).unit is None


def test_previous_completed_session_does_not_allow_a_preclose_run():
    assert daily(market_close=CLOSE - timedelta(days=1)).reason == "before_market_close"
    assert within_research_day(DAY, NOW.replace(hour=23, minute=55))
    assert not within_research_day(DAY, NOW.replace(hour=23, minute=55, second=1))


def test_slow_slot_crosses_hour_and_runs_all_seven_offsets_then_annotations():
    start = NOW.replace(hour=13, minute=30)
    slot = scheduled_slot("slow_daily", start)
    assert slot == scheduled_slot("slow_daily", start.replace(hour=14, minute=25))
    rows = []
    for offset in range(0, 481, 80):
        plan = next_unit("slow_daily", now=start, research_day=DAY, slot=slot, receipts=rows)
        assert (plan.unit.name, plan.unit.limit, plan.unit.offset) == ("slow_daily", 80, offset)
        rows.append(receipt("slow_daily", offset, slot=slot))
    assert next_unit("slow_daily", now=start, research_day=DAY, slot=slot, receipts=rows).unit.name == "compute_ic_annotations"


@pytest.mark.parametrize("job,hour,minute,expected", [
    ("fast_tech", 15, 30, [("fast_tech", 0, 40)]),
    ("news_per_ticker", 15, 0, [("news_per_ticker", 0, 75), ("news_per_ticker", 75, 75)]),
    ("news_macro", 16, 0, [("news_macro", None, None)]),
    ("minute_bars", 18, 15, [("minute_bars", 0, 75)]),
    ("ic_backtest_monthly", 4, 0, [("ic_backtest_monthly", None, None)]),
])
def test_slot_completion(job, hour, minute, expected):
    now = NOW.replace(day=1, hour=hour, minute=minute) if job == "ic_backtest_monthly" else NOW.replace(hour=hour, minute=minute)
    day = now.date().isoformat()
    slot = scheduled_slot(job, now)
    assert slot
    rows = []
    for name, offset, limit in expected:
        unit = next_unit(job, now=now, research_day=day, slot=slot, receipts=rows).unit
        assert (unit.name, unit.offset, unit.limit) == (name, offset, limit)
        rows.append({"unit": name, "offset": offset, "ok": True, "research_day": day, "slot": slot})
    assert next_unit(job, now=now, research_day=day, slot=slot, receipts=rows).reason == "complete"
    assert next_unit(job, now=now, research_day=day, slot=slot + "-next", receipts=rows).unit


def test_slot_windows():
    assert scheduled_slot("slow_daily", NOW.replace(hour=14, minute=26)) is None
    assert scheduled_slot("fast_tech", NOW.replace(hour=15, minute=29)) is None
    assert scheduled_slot("ic_backtest_monthly", NOW.replace(hour=4)) is None
    sunday = NOW.replace(day=15, hour=2)
    assert scheduled_slot("news_macro", sunday)
    assert scheduled_slot("news_per_ticker", sunday.replace(hour=15)) is None


def test_daily_prices_ticker_skip_list_is_not_an_overlap_skip():
    """Production 2026-11-12: daily_prices returned `skipped: [5 delisted
    tickers]` and the tick treated the non-empty list as an overlap no-op,
    failing three passes and skipping that night's research."""
    from alpha_agent.scheduling.runner import _unit_outcome
    from alpha_agent.scheduling.ticks import Unit

    prices = Unit("daily_prices", 0, 75, price_pass=1)
    real_shape = {"range": [0, 75], "errors": [], "skipped": ["ABC", "ANSS", "ATVI", "AVB", "BK"],
                  "updated": 350, "error_count": 0, "fresh_count": 70}
    assert _unit_outcome(prices, real_shape) == (True, None, 0)
    # A genuine overlap response still fails the unit.
    overlap = {"ok": True, "skipped": True, "reason": "duplicate_or_overlapping_shard"}
    assert _unit_outcome(Unit("fast_intraday", 0, 40), overlap) == (False, "UnitSkipped", 0)
    # The idempotent same-market-date publish stays a success.
    no_op = {"ok": True, "skipped": True, "reason": "no_op_same_market_date"}
    assert _unit_outcome(Unit("publish_recommendation"), no_op) == (True, None, 0)
