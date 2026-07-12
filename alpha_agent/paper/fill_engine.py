"""Pure fill-simulation logic for the paper-trading feature.

No I/O, no database calls — all functions are synchronous and deterministic.
The cron handler and API layer call these and own the DB mutations.
"""
from __future__ import annotations

from datetime import date


def compute_market_fill(
    signal_date: date,
    prices: dict[date, float],
) -> tuple[date, float] | None:
    """Return (fill_date, fill_price) for a market order, or None if T+1 price
    is not yet available.

    fill_date = earliest date in prices that is strictly after signal_date.
    fill_price = that date's close.
    """
    candidates = sorted(d for d in prices if d > signal_date)
    if not candidates:
        return None
    fill_date = candidates[0]
    return fill_date, prices[fill_date]


def compute_limit_fill(
    side: str,
    limit_price: float,
    signal_date: date,
    prices: dict[date, float],
    expire_after_days: int,
) -> tuple[date, float] | None | str:
    """Evaluate a DAY-validity limit order against available close prices.

    Returns:
        (fill_date, limit_price)  — if the close strictly crossed limit_price
        None                      — still pending (fewer than expire_after_days
                                   days have elapsed without a cross)
        "expired"                 — expire_after_days days elapsed, no fill

    Cross rule (not touch):
        buy:  daily_prices.close < limit_price  (strictly below)
        sell: daily_prices.close > limit_price  (strictly above)

    Fill price is always limit_price (not the close), because the close already
    crossed, making a limit-price execution plausible intraday.
    """
    candidates = sorted(d for d in prices if d > signal_date)
    checked = 0
    for d in candidates:
        checked += 1
        close = prices[d]
        crossed = (
            close < limit_price if side == "buy" else close > limit_price
        )
        if crossed:
            return d, limit_price
        if checked >= expire_after_days:
            return "expired"
    return None  # still pending


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
