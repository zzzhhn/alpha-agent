"""Pure next-unit planning. Receipts are cron_runs.details, never provider data.

The research scope stays on the UTC day: fast rows use that date and the
priority universe ranks with before_date=UTC date, even though prices use XNYS.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal

Job = Literal[
    "daily_close", "slow_daily", "fast_tech", "news_per_ticker", "news_macro",
    "minute_bars", "ic_backtest_monthly",
]
FAST_OFFSETS = tuple(range(0, 240, 40))
BUDGET_SECONDS = 240
FAILURE_BUDGET = 3
# Same settle delay as the old 22:00 UTC price pull (one hour after the EST
# close): yfinance daily bars right at the bell are not reliably final.
PRICE_SETTLE_MINUTES = 60
# A new price pass waits for the previous one to age, so a provider outage is
# not burned through three passes in fifteen minutes.
PRICE_PASS_SPACING_MINUTES = 20
PRICE_SLICE = 75


@dataclass(frozen=True)
class Unit:
    name: str
    offset: int | None = None
    limit: int | None = None
    estimate: int = 60
    cooldown: int = 0
    price_pass: int | None = None


@dataclass(frozen=True)
class Plan:
    unit: Unit | None = None
    reason: str | None = None


def within_research_day(day: str, now: datetime) -> bool:
    instant = now.astimezone(UTC)
    deadline = datetime.combine(datetime.fromisoformat(day).date() + timedelta(days=1), time(), UTC)
    return instant.date().isoformat() == day and (deadline - instant).total_seconds() >= 300


def _observed(receipt: dict) -> datetime | None:
    value = receipt.get("observed_at")
    try:
        return datetime.fromisoformat(value).astimezone(UTC) if value else None
    except (TypeError, ValueError):
        return None


def scheduled_slot(job: Job, now: datetime) -> str | None:
    """One slow slot spans both hours; other jobs have one slot per scheduled hour."""
    now = now.astimezone(UTC)
    day, hour, minute = now.date().isoformat(), now.hour, now.minute
    if job == "daily_close":
        return day
    if job == "ic_backtest_monthly":
        return f"{day}:04" if now.day == 1 and hour == 4 else None
    if job == "news_macro" and hour == 2:
        return f"{day}:02"
    if now.weekday() >= 5:
        return None
    if job == "slow_daily":
        return f"{day}:13:30" if (hour == 13 and minute >= 30) or (hour == 14 and minute <= 25) else None
    hours = {"fast_tech": (15, 19), "news_per_ticker": (15, 19),
             "news_macro": (12, 16, 20), "minute_bars": (18,)}
    minimum = {"fast_tech": 30, "minute_bars": 15}.get(job, 0)
    return f"{day}:{hour:02}" if hour in hours.get(job, ()) and minute >= minimum else None


def next_unit(
    job: Job, *, now: datetime, research_day: str, slot: str,
    receipts: list[dict], market_close: datetime | None = None,
    ready: bool = False, price_universe_count: int = 0,
) -> Plan:
    """Choose exactly one unit, or explain why no work may start.

    Failed/unfinished units consume a shared daily failure budget; control
    receipts (unit=None) and a publication rejected by its health gate do not.
    daily_close order: settled prices (full first pass, at most three passes
    spaced apart) -> IC -> six full shards -> one publication attempt -> L2.
    L2 still runs once when the chain stops early (prices never ready, failure
    budget spent), because it only values holdings and fills pending intents.
    """
    today = [r for r in receipts if r.get("research_day") == research_day]
    exhausted = sum(
        r.get("unit") not in (None, "publish_recommendation") and r.get("ok") is False
        for r in today
    ) >= FAILURE_BUDGET
    rows = [r for r in today if r.get("slot") == slot]

    def done(name, offset=None, price_pass=None):
        return any(r.get("unit") == name and r.get("offset") == offset
                   and r.get("price_pass") == price_pass and r.get("ok") is True for r in rows)

    def attempted(name):
        return any(r.get("unit") == name for r in rows)

    if job != "daily_close":
        if exhausted:
            return Plan(reason="failure_budget_exhausted")
        if job == "slow_daily":
            units = [Unit("slow_daily", o, 80, 150, 30) for o in range(0, 481, 80)]
            units.append(Unit("compute_ic_annotations", estimate=90))
        elif job == "fast_tech":
            units = [Unit("fast_tech", 0, 40, 170)]
        elif job == "news_per_ticker":
            units = [Unit("news_per_ticker", o, 75, 100, 10) for o in (0, 75)]
        elif job == "minute_bars":
            units = [Unit(job, 0, 75, 180)]
        else:
            units = [Unit(job, estimate=180 if job == "ic_backtest_monthly" else 60)]
        return next((Plan(u) for u in units if not done(u.name, u.offset)), Plan(reason="complete"))

    if not within_research_day(research_day, now):
        return Plan(reason="research_day_window_ended")
    # latest_completed_session returns yesterday before today's close.
    # Reject it, rather than publishing yesterday under today's UTC scope.
    if market_close is None or market_close.date().isoformat() != research_day or now < market_close:
        return Plan(reason="before_market_close")
    if done("l2_cycle"):
        return Plan(reason="complete")
    if attempted("l2_cycle"):
        return Plan(reason="l2_attempted")
    l2 = Plan(Unit("l2_cycle", estimate=120))
    if attempted("publish_recommendation") or exhausted:
        return l2
    if now < market_close + timedelta(minutes=PRICE_SETTLE_MINUTES):
        return Plan(reason="awaiting_settled_close")
    if not 1 <= price_universe_count <= 600:
        return Plan(reason="price_universe_outside_bounded_scope")
    offsets = range(0, price_universe_count, PRICE_SLICE)
    # The first pass always covers the whole price universe: IC, L2 and the bot
    # value more names than the research set that `ready` measures.
    if not ready or not all(done("daily_prices", o, 1) for o in offsets):
        for price_pass in range(1, 4):
            missing = [o for o in offsets if not done("daily_prices", o, price_pass)]
            if not missing:
                continue
            if price_pass > 1 and ready:
                break
            previous = [_observed(r) for r in rows
                        if r.get("unit") == "daily_prices" and r.get("price_pass") == price_pass - 1]
            previous = [t for t in previous if t is not None]
            if previous and now - max(previous) < timedelta(minutes=PRICE_PASS_SPACING_MINUTES):
                return Plan(reason="awaiting_next_price_pass")
            return Plan(Unit("daily_prices", missing[0], PRICE_SLICE, 60, 10, price_pass))
        if not ready:
            # Three passes spent and coverage still short: no research today,
            # but existing holdings are still valued.
            return l2
    if not done("ic_backtest_monthly"):
        return Plan(Unit("ic_backtest_monthly", estimate=180))
    for offset in FAST_OFFSETS:
        if not done("fast_intraday", offset):
            return Plan(Unit("fast_intraday", offset, 40, 170, 30))
    return Plan(Unit("publish_recommendation", estimate=60))
