"""Pure fill-simulation logic for the paper-trading feature.

No I/O, no database calls — all functions are synchronous and deterministic.
The cron handler and API layer call these and own the DB mutations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite

from alpha_agent.market_session import next_xnys_session, xnys_sessions


MARKET_QUOTE_GRACE_SESSIONS = 1
MARKET_AWAITING_QUOTE = 'market_awaiting_exact_t1_close'


def market_order_window(signal_date: date) -> tuple[date, date]:
    target = next_xnys_session(signal_date)
    deadline = target
    for _ in range(MARKET_QUOTE_GRACE_SESSIONS):
        deadline = next_xnys_session(deadline)
    return target, deadline


@dataclass(frozen=True)
class MarketReview:
    status: str
    reason: str


def review_market_fill(
    signal_date: date, prices: dict[date, float], *, as_of: date, identity_verified: bool,
) -> tuple[date, float] | MarketReview | None:
    target, deadline = market_order_window(signal_date)
    if as_of < target:
        return None
    if not identity_verified:
        return MarketReview('failed', 'market_identity_unresolved')
    if as_of <= deadline:
        fill = compute_market_fill(signal_date, prices, as_of=as_of)
        if fill is not None:
            return fill
    if as_of >= deadline:
        return MarketReview('expired', 'market_expired_missing_t1_close')
    return MarketReview('pending', MARKET_AWAITING_QUOTE)


def compute_market_fill(
    signal_date: date,
    prices: dict[date, float],
    *,
    as_of: date,
) -> tuple[date, float] | None:
    """Fill at the exact next completed XNYS close, not a substitute quote."""
    if as_of <= signal_date:
        return None
    fill_date = next_xnys_session(signal_date)
    price = prices.get(fill_date)
    if fill_date > as_of or price is None or not isfinite(price) or price <= 0:
        return None
    return fill_date, price


@dataclass(frozen=True)
class LimitExpiry:
    missing_quote_dates: tuple[date, ...]


def compute_limit_fill(
    side: str,
    limit_price: float,
    signal_date: date,
    prices: dict[date, float | None],
    expire_after_days: int,
    *,
    as_of: date,
) -> tuple[date, float] | LimitExpiry | None:
    """Evaluate a limit order over completed XNYS sessions after the signal.

    Returns:
        (fill_date, limit_price)  — if the close strictly crossed limit_price
        None                      — fewer than expire_after_days sessions elapsed
        LimitExpiry                — the window elapsed, with missing sessions listed

    Cross rule (not touch):
        buy:  daily_prices.close < limit_price  (strictly below)
        sell: daily_prices.close > limit_price  (strictly above)

    Fill price is always limit_price (not the close), because the close already
    crossed, making a limit-price execution plausible intraday.
    """
    first_calendar_day = signal_date + timedelta(days=1)
    if first_calendar_day > as_of:
        return None
    window = max(expire_after_days, 1)
    sessions = xnys_sessions(first_calendar_day, as_of)[:window]
    missing = []
    for d in sessions:
        close = prices.get(d)
        if close is None or not isfinite(close) or close <= 0:
            missing.append(d)
            continue
        crossed = (
            close < limit_price if side == "buy" else close > limit_price
        )
        if crossed:
            return d, limit_price
    return LimitExpiry(tuple(missing)) if len(sessions) >= window else None


def new_avg_cost(
    old_qty: int,
    old_avg_cost: float,
    fill_qty: int,
    fill_price: float,
) -> float:
    """Weighted average cost after adding fill_qty shares at fill_price."""
    total_qty = old_qty + fill_qty
    if total_qty == 0:
        return 0.0
    return (old_qty * old_avg_cost + fill_qty * fill_price) / total_qty


def unrealized_pnl(qty: int, avg_cost: float, current_close: float) -> float:
    """Mark-to-market unrealized PnL for a position."""
    return (current_close - avg_cost) * qty


def realized_pnl_delta(avg_cost: float, fill_price: float, sold_qty: int) -> float:
    """Incremental realized PnL for a sell fill."""
    return (fill_price - avg_cost) * sold_qty


def has_sufficient_cash(cash: float, fill_price: float, qty: int) -> bool:
    """True if cash covers a buy fill of qty shares at fill_price.

    Called at fill time (not just order time) because cash charged by an
    earlier fill in the same batch can make a later, already-pending order
    unaffordable even though it passed the order-time estimate.
    """
    return cash >= fill_price * qty
