"""Small, read-only turnover study using already persisted pre-close targets.

This is retrospective research, never a replacement for the forward ledger.
Fractional shares, fixed costs, no dividends/taxes. No parameter optimizer.
"""
from __future__ import annotations

import math
from datetime import date


def replay_targets(
    sessions: list[date], targets: dict[date, dict[str, float]],
    prices: dict[tuple[date, str], float], *, mode: str, cost_bps: float,
) -> dict:
    cash = 1.0
    shares: dict[str, float] = {}
    fees = turnover = 0.0
    peak = 1.0
    drawdown = 0.0
    traded_batches = 0
    last_month = None
    rate = cost_bps / 10_000
    series = []
    for day in sessions:
        target = targets.get(day)
        if mode == "monthly" and last_month == (day.year, day.month):
            target = None
        if mode in ("spy", "rsp"):
            target = {mode.upper(): 1.0} if day == sessions[0] else None
        elif mode == "cash":
            target = None
        required = set(shares) | {t for t, w in (target or {}).items() if w > 0}
        missing = sorted(t for t in required if not math.isfinite(prices.get((day, t), 0)) or prices.get((day, t), 0) <= 0)
        if missing:
            return {"status": "missing_prices", "date": day.isoformat(), "tickers": missing[:10]}
        nav = cash + sum(q * prices[day, t] for t, q in shares.items())
        if target is not None:
            if any(w < 0 or not math.isfinite(w) for w in target.values()) or sum(target.values()) > 1.00001:
                return {"status": "invalid_targets", "date": day.isoformat()}
            desired = {t: nav * target.get(t, 0) / prices[day, t] for t in required}
            if mode == "band":
                for t in required:
                    current = shares.get(t, 0)
                    if abs(desired[t] - current) * prices[day, t] / nav < 0.01:
                        desired[t] = current
            gross = 0.0
            # Sell first, then pro-rate buys to available cash including fees.
            for t in sorted(required):
                sold = max(0.0, shares.get(t, 0) - desired[t])
                value = sold * prices[day, t]
                cash += value * (1 - rate)
                fees += value * rate
                gross += value
                shares[t] = shares.get(t, 0) - sold
            wanted = {t: max(0.0, desired[t] - shares.get(t, 0)) for t in required}
            needed = sum(q * prices[day, t] * (1 + rate) for t, q in wanted.items())
            scale = min(1.0, max(cash, 0.0) / needed) if needed else 0.0
            for t, qty in wanted.items():
                value = qty * scale * prices[day, t]
                cash -= value * (1 + rate)
                fees += value * rate
                gross += value
                shares[t] += qty * scale
            shares = {t: q for t, q in shares.items() if q > 1e-12}
            turnover += gross / nav
            traded_batches += int(gross > 1e-12)
            last_month = (day.year, day.month)
        nav = cash + sum(q * prices[day, t] for t, q in shares.items())
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
        series.append({"date": day.isoformat(), "nav": nav})
    return {"status": "ready", "net_return": series[-1]["nav"] - 1 if series else None,
            "max_drawdown": drawdown, "two_way_turnover": turnover,
            "cost_fraction_of_initial_capital": fees, "trade_batches": traded_batches,
            "observations": len(series)}
