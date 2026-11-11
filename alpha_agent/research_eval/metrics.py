"""Explicit-calendar alignment and start-of-period-notional cost accounting."""
from dataclasses import dataclass
from datetime import date
from math import isfinite, prod, sqrt
from statistics import stdev
from typing import Mapping, Sequence


def calendar_dates(sessions: Sequence[date]) -> tuple[date, ...]:
    days = tuple(sessions)
    if any(type(day) is not date for day in days) or days != tuple(sorted(set(days))):
        raise ValueError("sessions must be unique, increasing dates")
    return days


def numbers(values: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if not all(isfinite(value) for value in result):
        raise ValueError("non-finite observation")
    return result


@dataclass(frozen=True)
class Alignment:
    expected: tuple[date, ...]
    dates: tuple[date, ...]
    values: dict[str, tuple[float, ...]]
    missing: dict[str, tuple[date, ...]]

    @property
    def complete(self) -> bool:
        return bool(self.expected) and self.dates == self.expected

    @property
    def coverage(self) -> float | None:
        return len(self.dates) / len(self.expected) if self.expected else None


def common_dates(
    series: Mapping[str, Mapping[date, float | None]], sessions: Sequence[date],
) -> Alignment:
    """Intersect all arms once; retain every missing date in the audit receipt.

    A sparse intersection is diagnostic only: do not compound it as a daily
    path. Dates outside the caller's frozen window are ignored explicitly.
    """
    days = calendar_dates(sessions)
    if not series:
        raise ValueError("at least one series required")
    missing = {}
    for name, observations in series.items():
        missing[name] = tuple(
            day for day in days
            if observations.get(day) is None or not isfinite(float(observations[day]))
        )
    absent = set().union(*missing.values())
    common = tuple(day for day in days if day not in absent)
    return Alignment(days, common, {
        name: tuple(float(observations[day]) for day in common)
        for name, observations in series.items()
    }, missing)


@dataclass(frozen=True)
class NavPath:
    nav: tuple[float, ...]  # includes pre-fee initial capital
    gross_nav: tuple[float, ...]
    net_returns: tuple[float, ...]
    traded_weight: tuple[float, ...]  # buys + sells, NOT half-turnover
    cost_rates: tuple[float, ...]

    @property
    def total_turnover(self) -> float:
        """Sum of two-sided interval notional / beginning NAV ratios."""
        return sum(self.traded_weight)

    @property
    def cost_drag(self) -> float:
        """Counterfactual compounded gross minus net, per initial capital."""
        return (self.gross_nav[-1] - self.nav[-1]) / self.nav[0]


def nav_from_returns(
    gross_returns: Sequence[float], buys: Sequence[float], sells: Sequence[float],
    *, fee_bps: float, slippage_bps: float = 0, initial: float = 100,
) -> NavPath:
    """Flows are reference-price notional / beginning NAV for each interval.

    Costs are subtracted from that interval's gross return. Buy cost is
    (1+s)(1+f)-1; sell cost is 1-(1-s)(1-f). This includes the fee on slipped
    notional. Entry/exit must be supplied explicitly; no invented liquidation.
    This calculator does not generate trades, enforce cash or simulate shares.
    """
    returns, buy, sell = numbers(gross_returns), numbers(buys), numbers(sells)
    fee, slip, capital = numbers((fee_bps, slippage_bps, initial))
    if len(returns) != len(buy) or len(returns) != len(sell):
        raise ValueError("flows and returns must have identical lengths")
    if not 0 <= fee < 10000 or not 0 <= slip < 10000 or capital <= 0:
        raise ValueError("invalid cost or capital")
    if any(r < -1 for r in returns) or any(x < 0 for x in buy + sell):
        raise ValueError("invalid long-only return or negative flow")
    f, s = fee / 10000, slip / 10000
    buy_cost, sell_cost = f + s + f*s, f + s - f*s
    nav, gross_nav, net_returns, costs = [capital], [capital], [], []
    for r, b, sale in zip(returns, buy, sell, strict=True):
        cost = b * buy_cost + sale * sell_cost
        net = r - cost
        if net < -1 or (nav[-1] == 0 and (r != 0 or b != 0 or sale != 0)):
            raise ValueError("insolvent or nonzero activity after bankruptcy")
        nav.append(nav[-1] * (1 + net))
        gross_nav.append(gross_nav[-1] * (1 + r))
        net_returns.append(net)
        costs.append(cost)
    return NavPath(tuple(nav), tuple(gross_nav), tuple(net_returns),
                   tuple(b + sale for b, sale in zip(buy, sell)), tuple(costs))


def max_drawdown(nav: Sequence[float]) -> float | None:
    """Negative peak-to-trough fraction; include initial pre-cost NAV."""
    path = numbers(nav)
    if not path:
        return None
    if path[0] <= 0 or any(value < 0 for value in path):
        raise ValueError("NAV requires positive origin and nonnegative values")
    peak, worst = path[0], 0.0
    for value in path:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def annualized_vol(returns: Sequence[float], periods: float = 252) -> float | None:
    values = numbers(returns)
    if not isfinite(periods) or periods <= 0:
        raise ValueError("periods must be positive")
    return stdev(values) * sqrt(periods) if len(values) >= 2 else None


def excess_returns(strategy: Sequence[float], benchmark: Sequence[float]) -> tuple[float, ...]:
    a, b = numbers(strategy), numbers(benchmark)
    if len(a) != len(b):
        raise ValueError("align dates before computing excess")
    return tuple(x - y for x, y in zip(a, b, strict=True))


def matched_summary(alignment: Alignment, strategy: str, benchmark: str) -> dict:
    """Fail closed on gaps: never compress missing sessions into a daily NAV."""
    base = {"expected_sessions": len(alignment.expected), "common_sessions": len(alignment.dates),
            "coverage": alignment.coverage, "missing": alignment.missing}
    if not alignment.complete:
        return {**base, "status": "incomplete_path", "metrics": None}
    a, b = alignment.values[strategy], alignment.values[benchmark]
    path = nav_from_returns(a, [0]*len(a), [0]*len(a), fee_bps=0)
    benchmark_path = nav_from_returns(b, [0]*len(b), [0]*len(b), fee_bps=0)
    ar, br = prod(1 + x for x in a) - 1, prod(1 + x for x in b) - 1
    return {**base, "status": "complete", "metrics": {
        "net_return": ar, "benchmark_return": br, "excess_return_pp": ar - br,
        "relative_wealth_return": (1 + ar)/(1 + br) - 1 if br > -1 else None,
        "max_drawdown": max_drawdown(path.nav),
        "benchmark_max_drawdown": max_drawdown(benchmark_path.nav),
        "annualized_vol": annualized_vol(a),
    }}


def exposure(weights: Sequence[float]) -> dict:
    values = numbers(weights)
    total = sum(values)
    if any(w < 0 for w in values) or total > 1 + 1e-12:
        raise ValueError("long-only, unlevered weights required")
    hhi = sum((w/total)**2 for w in values) if total else None
    return {"gross_exposure": total, "cash_weight": max(0, 1-total),
            "max_position": max(values, default=0), "invested_hhi": hhi,
            "effective_positions": 1/hhi if hhi else None}
