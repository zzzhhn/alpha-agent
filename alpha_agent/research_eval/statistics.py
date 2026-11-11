"""HAC mean inference and Bailey/Lopez de Prado (2014) DSR diagnostics."""
from dataclasses import dataclass
from datetime import date
from math import exp, floor, isfinite, prod, sqrt
from statistics import NormalDist, mean, stdev
from typing import Mapping, Sequence

from .metrics import calendar_dates, numbers


@dataclass(frozen=True)
class MeanTest:
    n: int
    lag: int
    mean: float | None
    se: float | None
    t: float | None


def newey_west(values: Sequence[float], *, horizon: int = 1, lag: int | None = None) -> MeanTest:
    """Intercept-only Bartlett HAC, autocovariances divided by n.

    No automatic p-value: normal approximation is poor for tiny samples.
    Daily excess and overlapping horizon excess have different lag floors.
    """
    x = numbers(values)
    n = len(x)
    if type(horizon) is not int or horizon < 1:
        raise ValueError("positive integer horizon required")
    bandwidth = max(horizon-1, floor(4*(n/100)**(2/9))) if lag is None else lag
    if type(bandwidth) is not int or bandwidth < horizon-1:
        raise ValueError("lag must be integer and at least horizon-1")
    average = mean(x) if x else None
    if n < max(3, bandwidth+2):
        return MeanTest(n, bandwidth, average, None, None)
    u = [value-average for value in x]
    long_run = sum(value*value for value in u)/n
    for k in range(1, bandwidth+1):
        covariance = sum(u[t]*u[t-k] for t in range(k, n))/n
        long_run += 2*(1-k/(bandwidth+1))*covariance
    if long_run <= 0:
        return MeanTest(n, bandwidth, average, None, None)
    se = sqrt(long_run/n)
    return MeanTest(n, bandwidth, average, se, average/se)


def non_overlapping(
    returns: Mapping[date, float | None], sessions: Sequence[date], horizon: int, *, offset: int = 0,
) -> dict[date, float | None]:
    """Compound daily intervals on the original calendar; missing block stays None.

    Anchor offset is fixed before results. Report all offsets as sensitivity,
    never select the most favorable one. Partial tail is not an h-day outcome.
    """
    days = calendar_dates(sessions)
    if type(horizon) is not int or type(offset) is not int or not 0 <= offset < horizon:
        raise ValueError("require horizon>0 and 0<=offset<horizon")
    result = {}
    for start in range(offset, len(days)-horizon+1, horizon):
        block = days[start:start+horizon]
        values = [returns.get(day) for day in block]
        if any(value is None or not isfinite(float(value)) for value in values):
            result[block[-1]] = None
        else:
            values = numbers(values)
            if any(value < -1 for value in values):
                raise ValueError("invalid simple return")
            result[block[-1]] = prod(1 + value for value in values) - 1
    return result


def deflated_sharpe(
    returns: Sequence[float], *, trial_sharpes: Sequence[float],
    independent_trials: int | None = None,
) -> dict:
    """DSR Eq. 1/3: all SRs must be unannualized and at the SAME frequency.

    Null mean across trials is zero, dispersion is sample SD of the FULL
    experiment registry, not the chosen winner's standard error. Pearson
    kurtosis (normal=3) and central moment skewness are used. For correlated
    trials N must be justified externally; default full count is conservative.
    DSR itself does NOT repair serial dependence: use nonoverlapping samples
    and report HAC separately. Unknown previous searches => DSR unverified.
    """
    x, trials = numbers(returns), numbers(trial_sharpes)
    count = len(trials) if independent_trials is None else independent_trials
    if type(count) is not int or count < 1 or count > len(trials):
        raise ValueError("trial count must be 1..len(full trial registry)")
    result = {"n": len(x), "trials": count, "probability": None,
              "sharpe": None, "benchmark_sharpe": None, "reason": None}
    if len(x) < 3:
        return {**result, "reason": "short_sample"}
    sd = stdev(x)
    if sd == 0:
        return {**result, "reason": "zero_variance"}
    sr = mean(x)/sd
    benchmark = 0.0
    if count > 1:
        normal, gamma = NormalDist(), 0.5772156649015329
        benchmark = stdev(trials) * (
            (1-gamma)*normal.inv_cdf(1-1/count)
            + gamma*normal.inv_cdf(1-1/(count*exp(1)))
        )
    centered = [value-mean(x) for value in x]
    m2 = mean(value**2 for value in centered)
    skew = mean(value**3 for value in centered)/m2**1.5
    kurt = mean(value**4 for value in centered)/m2**2
    variance = 1-skew*sr+(kurt-1)*sr*sr/4
    result.update(sharpe=sr, benchmark_sharpe=benchmark)
    if variance <= 0:
        return {**result, "reason": "invalid_moment_variance"}
    probability = NormalDist().cdf((sr-benchmark)*sqrt(len(x)-1)/sqrt(variance))
    return {**result, "probability": probability}


def holm(p_values: Sequence[float]) -> tuple[float, ...]:
    """Family-wise adjusted p-values, preserving input order, including failures."""
    p = numbers(p_values)
    if any(not 0 <= value <= 1 for value in p):
        raise ValueError("p-values must be in [0,1]")
    order, adjusted, prior = sorted(range(len(p)), key=p.__getitem__), [0.0]*len(p), 0.0
    for rank, index in enumerate(order):
        prior = max(prior, min(1, (len(p)-rank)*p[index]))
        adjusted[index] = prior
    return tuple(adjusted)
