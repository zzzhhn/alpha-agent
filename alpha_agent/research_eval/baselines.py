"""Share/cash replay of the two frozen offline controls; never a trading API.

Prices are adjusted research units, not a raw corporate-action cash ledger.
Only the diagnostic wrapper imports the existing local bundle loader.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from math import ceil, floor, isfinite, isnan
from pathlib import Path
from typing import Mapping, Sequence

from .metrics import calendar_dates, numbers
from .protocol import PROTOCOL, DateRange, FrozenProtocol


Matrix = Sequence[Sequence] | Mapping[date, Mapping[str, object]]
ARMS = ("ew_monthly", "momentum_12_1")


@dataclass(frozen=True)
class Trade:
    date: date
    ticker: str
    side: str
    qty: int  # executed shares; zero for unfilled orders
    price: float | None  # reference close, before slippage
    cost: float
    status: str
    reason: str | None
    requested_qty: int  # after turnover scaling and truncation


@dataclass(frozen=True)
class Rebalance:
    date: date
    signal_date: date
    nav_before: float
    requested_notional: float  # before scaling, including unavailable trades at last marks
    scale: float
    gross_notional: float  # actually executed, before costs
    turnover: float  # gross_notional / nav_before
    initial_build: bool


@dataclass(frozen=True)
class BaselineResult:
    arm: str
    nav: dict[date, float]
    cash: dict[date, float]
    holdings: dict[date, dict[str, int]]
    trades: list[Trade]
    rebalances: list[Rebalance]
    turnover: dict[date, float]
    total_costs: float
    stale_counts: dict[date, int]  # held names without today's close (stock-days)
    missing_counts: dict[date, int]  # all missing input closes, held or not
    protocol_version: str
    protocol_fingerprint: str
    initial_capital: float
    fee_bps: float
    slippage_bps: float


def _rows(matrix: Matrix, days: tuple[date, ...], tickers: tuple[str, ...]) -> tuple:
    if isinstance(matrix, Mapping):
        if set(matrix) != set(days) or any(set(row) != set(tickers) for row in matrix.values()):
            raise ValueError("matrix mappings must contain exactly the sessions and tickers")
        rows = tuple(tuple(matrix[day][ticker] for ticker in tickers) for day in days)
    else:
        # ndarray.tolist converts numpy scalars without making numpy a core dependency.
        rows = tuple(tuple(row) for row in (
            matrix.tolist() if hasattr(matrix, "tolist") else matrix
        ))
    if len(rows) != len(days) or any(len(row) != len(tickers) for row in rows):
        raise ValueError("matrix shape must be (sessions, tickers)")
    return rows


def _validate_protocol(protocol: FrozenProtocol) -> None:
    if (protocol.baseline_rebalance != "month_end_d1_close"
            or protocol.baseline_shares != "integer_sell_first_cash_constrained"
            or protocol.baseline_tie_break != "ticker_ascending"):
        raise ValueError("unsupported baseline execution convention")
    capital, position, initial_cap, later_cap = numbers((
        protocol.baseline_initial_capital, protocol.baseline_max_position,
        protocol.baseline_initial_turnover_cap, protocol.baseline_rebalance_turnover_cap,
    ))
    if capital <= 0 or not 0 < position <= 1 or not 0 <= later_cap <= initial_cap <= 1:
        raise ValueError("invalid baseline capital/position/turnover caps")
    lookback, skip, top = (protocol.momentum_lookback_sessions,
                           protocol.momentum_skip_sessions, protocol.momentum_top_n)
    if any(type(x) is not int for x in (lookback, skip, top)) or not 0 <= skip < lookback or top < 1:
        raise ValueError("invalid momentum lookback/skip/top_n")


def _targets(arm, index, prices, eligible, tickers, protocol):
    candidates = [j for j in range(len(tickers)) if eligible[index][j]]
    if arm == "ew_monthly":
        candidates = [j for j in candidates if not isnan(prices[index][j])]
        weight = min(1 / len(candidates), protocol.baseline_max_position) if candidates else 0
    else:
        if index < protocol.momentum_lookback_sessions:
            return {}
        older = prices[index - protocol.momentum_lookback_sessions]
        recent = prices[index - protocol.momentum_skip_sessions]
        candidates = [j for j in candidates if not isnan(older[j]) and not isnan(recent[j])]
        candidates.sort(key=lambda j: (-(recent[j] / older[j] - 1), tickers[j]))
        candidates = candidates[:protocol.momentum_top_n]
        weight = min(1 / protocol.momentum_top_n, protocol.baseline_max_position)
    return dict.fromkeys(candidates, weight)


def _rebalance(day, signal_day, targets, prices, marks, shares, cash, tickers,
               protocol, buy_rate, sell_rate, initial_build):
    nav = cash + sum(qty * mark for qty, mark in zip(shares, marks) if qty)
    if not isfinite(nav) or nav <= 0:
        raise ValueError("non-finite or insolvent baseline NAV")
    # Unavailable prices cannot be tradable. Their last marks still consume
    # the proportional budget, so missing orders never finance substitution.
    deltas = [targets.get(j, 0) * nav - shares[j] * marks[j] for j in range(len(tickers))]
    gross = sum(abs(delta) for delta in deltas)
    cap = (protocol.baseline_initial_turnover_cap if initial_build
           else protocol.baseline_rebalance_turnover_cap)
    scale = min(1, cap * nav / gross) if gross else 1.0
    orders, trades = {}, []
    for j, delta in enumerate(deltas):
        mark = marks[j]
        qty = floor(abs(delta) * scale / mark) if mark > 0 else 0
        if not qty:
            continue
        side = "buy" if delta > 0 else "sell"
        if isnan(prices[j]):
            trades.append(Trade(day, tickers[j], side, 0, None, 0.0,
                                "unfilled", "missing_price", qty))
        else:
            orders[j] = (side, qty)

    executed = 0.0
    for j in sorted(orders, key=lambda j: tickers[j]):
        side, qty = orders[j]
        if side != "sell":
            continue
        notional = qty * prices[j]
        cost = notional * sell_rate
        cash += notional - cost
        shares[j] -= qty
        executed += notional
        trades.append(Trade(day, tickers[j], side, qty, prices[j], cost, "filled", None, qty))

    buys = {j: qty for j, (side, qty) in orders.items() if side == "buy"}
    required = sum(qty * prices[j] * (1 + buy_rate) for j, qty in buys.items())
    # Literal ascending reduction priority: trim A before B, protecting later
    # tickers' planned quantities. Never add shares or a lower-ranked name.
    for j in sorted(buys, key=lambda j: tickers[j]):
        if required <= cash:
            break
        unit_cost = prices[j] * (1 + buy_rate)
        removed = min(buys[j], ceil((required - cash) / unit_cost))
        buys[j] -= removed
        required = sum(qty * prices[k] * (1 + buy_rate) for k, qty in buys.items())

    for j in sorted(buys, key=lambda j: tickers[j]):
        qty, requested = buys[j], orders[j][1]
        notional = qty * prices[j]
        cost = notional * buy_rate
        cash -= notional + cost
        shares[j] += qty
        executed += notional
        trades.append(Trade(day, tickers[j], "buy", qty, prices[j], cost,
                            "filled" if qty == requested else "partial" if qty else "unfilled",
                            None if qty == requested else "insufficient_cash", requested))
    if cash < -1e-8 or any(qty < 0 for qty in shares):
        raise ValueError("cash/share execution invariant violated")
    cash = max(0.0, cash)  # floating point residue only
    receipt = Rebalance(day, signal_day, nav, gross, scale, executed, executed / nav, initial_build)
    return cash, trades, receipt


def replay_baseline(
    arm: str, sessions: Sequence[date], tickers: Sequence[str],
    adjusted_close: Matrix, eligibility: Matrix, *, protocol: FrozenProtocol = PROTOCOL,
    fee_bps: float | None = None, slippage_bps: float | None = None,
    window: DateRange | None = None,
) -> BaselineResult:
    """Replay one arm from cash, with optional earlier sessions as signal warmup.

    Matrices are row-major arrays, or date -> ticker -> value mappings. NaN is
    the sole missing-price sentinel; other nonpositive/non-finite prices fail.
    The caller supplies a complete session calendar. Only in-window month-end
    signals trade, on the next in-window session's close; no block-start entry,
    retries, future-data filtering, or terminal liquidation is manufactured.

    Targets are fractions of pre-cost execution NAV. Missing executions use
    last marks for delta/budget calculation only. Initial 100% budget remains
    available until the first successful buy; later monthly budgets are 20%.
    Cash shortfalls reduce planned buys starting at the ascending-first ticker.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown baseline arm: {arm}")
    _validate_protocol(protocol)
    days, names = calendar_dates(sessions), tuple(tickers)
    if not days or not names or any(not isinstance(t, str) or not t for t in names):
        raise ValueError("nonempty sessions and ticker strings required")
    if len(set(names)) != len(names):
        raise ValueError("tickers must be unique")
    prices = tuple(tuple(float(value) for value in row)
                   for row in _rows(adjusted_close, days, names))
    if any(not isnan(p) and (not isfinite(p) or p <= 0) for row in prices for p in row):
        raise ValueError("prices must be positive finite or NaN")
    eligible = _rows(eligibility, days, names)
    if any(type(value) is not bool for row in eligible for value in row):
        raise ValueError("eligibility must be boolean")
    fee, slip = numbers((protocol.l2_fee_bps if fee_bps is None else fee_bps,
                         protocol.l2_extra_slippage_bps if slippage_bps is None else slippage_bps))
    if not 0 <= fee < 10000 or not 0 <= slip < 10000:
        raise ValueError("invalid fee/slippage bps")
    f, s = fee / 10000, slip / 10000
    buy_rate, sell_rate = f + s + f * s, f + s - f * s
    indices = [i for i, day in enumerate(days)
               if window is None or window.start <= day <= window.end]
    if not indices:
        raise ValueError("window absent from sessions")
    # The final observed month-end has no D+1 inside the window: no execution.
    month_ends = {i for i, nxt in zip(indices, indices[1:])
                  if (days[i].year, days[i].month) != (days[nxt].year, days[nxt].month)}
    nav_path, cash_path, holdings, stale_counts, missing_counts = {}, {}, {}, {}, {}
    shares, marks = [0] * len(names), [0.0] * len(names)
    cash, built, pending = float(protocol.baseline_initial_capital), False, None
    trades, rebalances = [], []
    for i in range(indices[-1] + 1):
        day, row = days[i], prices[i]
        for j, price in enumerate(row):
            if not isnan(price):
                marks[j] = price
        if i < indices[0]:
            continue
        if pending is not None:
            signal, targets = pending
            cash, fills, receipt = _rebalance(
                day, days[signal], targets, row, marks, shares, cash, names,
                protocol, buy_rate, sell_rate, not built,
            )
            trades.extend(fills)
            rebalances.append(receipt)
            built = built or any(trade.qty > 0 and trade.side == "buy" for trade in fills)
            pending = None
        nav_path[day] = cash + sum(qty * mark for qty, mark in zip(shares, marks) if qty)
        if not isfinite(nav_path[day]):
            raise ValueError("non-finite baseline NAV")
        cash_path[day] = cash
        holdings[day] = {ticker: qty for ticker, qty in zip(names, shares) if qty}
        stale_counts[day] = sum(qty > 0 and isnan(price) for qty, price in zip(shares, row))
        missing_counts[day] = sum(isnan(price) for price in row)
        if i in month_ends:
            pending = (i, _targets(arm, i, prices, eligible, names, protocol))
    return BaselineResult(
        arm, nav_path, cash_path, holdings, trades, rebalances,
        {item.date: item.turnover for item in rebalances}, sum(t.cost for t in trades),
        stale_counts, missing_counts, protocol.version, protocol.fingerprint,
        float(protocol.baseline_initial_capital), fee, slip,
    )


def run_historical_diagnostic(panel_path: str | Path | None = None) -> dict:
    """Load the local v3 bundle and replay the frozen historical block only.

    The existing cached loader has no path argument. An explicit local path
    temporarily overrides its price-path constant and bypasses its cache;
    neither the constant nor the cache is changed after this call. Missing
    PIT membership/required fields are reported, never fabricated.
    """
    from unittest.mock import patch

    from alpha_agent.data import membership
    from alpha_agent.factor_engine import factor_backtest

    base = {
        "label": "historical_diagnostic_not_forward_evidence",
        "protocol_version": PROTOCOL.version,
        "protocol_fingerprint": PROTOCOL.fingerprint,
        "start": PROTOCOL.historical_test.start.isoformat(),
        "end": PROTOCOL.historical_test.end.isoformat(),
        "price_basis": "adjusted_research_units",
        "entry": "first_in_window_month_end_d1_close",
        "buy_shortfall_priority": "reduce_ticker_ascending",
    }
    path = Path(panel_path) if panel_path is not None else factor_backtest.PARQUET_V3_PATH
    if not path.is_file():
        return {**base, "status": "unavailable", "reason": f"price bundle missing: {path}"}
    # Do not silently select v2/v1, or reuse a panel cached under another path.
    with patch.object(factor_backtest, "PARQUET_PATH", path):
        panel = factor_backtest._load_panel.__wrapped__()
    missing = [field for field in ("dates", "tickers", "close", "is_member")
               if getattr(panel, field, None) is None]
    if missing:
        return {**base, "status": "unavailable", "missing_fields": missing}
    days = tuple(date.fromisoformat(str(day)[:10]) for day in panel.dates)
    import exchange_calendars as xcals

    window = PROTOCOL.historical_test
    calendar = xcals.get_calendar("XNYS", start=window.start.isoformat(), end=window.end.isoformat())
    expected = tuple(session.date() for session in calendar.sessions_in_range(window.start, window.end))
    actual = tuple(day for day in days if window.start <= day <= window.end)
    if actual != expected:
        return {**base, "status": "unavailable", "reason": "incomplete historical session calendar"}
    summaries = {}
    for arm in ARMS:
        result = replay_baseline(arm, days, panel.tickers, panel.close, panel.is_member, window=window)
        final = result.nav[actual[-1]]
        summaries[arm] = {
            "initial_capital": result.initial_capital,
            "final_nav": final,
            "total_return": final / result.initial_capital - 1,
            "total_cost": result.total_costs,
            "rebalance_count": len(result.rebalances),
            "stale_stock_days": sum(result.stale_counts.values()),
            "stale_days": sum(count > 0 for count in result.stale_counts.values()),
            "max_stale_names": max(result.stale_counts.values()),
            "missing_price_cells": sum(result.missing_counts.values()),
            "missing_price_unfilled_orders": sum(t.reason == "missing_price" for t in result.trades),
            "gross_turnover_sum": sum(result.turnover.values()),
            "ending_cash": result.cash[actual[-1]],
            "ending_positions": len(result.holdings[actual[-1]]),
        }
    return {
        **base, "status": "complete", "sessions": len(actual),
        "warmup_sessions": sum(day < window.start for day in days),
        "price_sha256": sha256(path.read_bytes()).hexdigest(),
        "membership_sha256": sha256(membership._DEFAULT_CSV.read_bytes()).hexdigest(),
        "membership_note": "Uses loader is_member as supplied; loader does not apply membership_updates.json.",
        "arms": summaries,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel_path", nargs="?", type=Path)
    print(json.dumps(run_historical_diagnostic(parser.parse_args().panel_path), indent=2))
