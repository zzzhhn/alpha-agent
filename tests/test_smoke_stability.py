"""Smoke-test temporal-stability gauge (AlphaEval dimension 2).

AlphaEval's "Temporal Stability" asks whether a factor's cross-sectional ranking
is stable between adjacent time points — an unstable ranking churns the book,
drives turnover, and erodes returns through transaction costs. The paper measures
it with "Relative Rank Entropy" (formula not given in the source) and validates
that it correlates with annualized turnover (R^2=0.815).

This is the project's principled implementation: the mean adjacent-day Spearman
rank autocorrelation of the factor over the IC-tail window. 1.0 = the ranking is
preserved day to day (stable); ~0 = the ranking reshuffles randomly each day
(unstable); negative = day-over-day reversal. Unlike the existing turnover gauge
(which only sees the top/bottom 30% quantile book and maps to trading cost), this
covers the FULL cross-section and needs no re-evaluation — it just ranks the
already-computed factor. The two are correlated (as the paper shows) but the
rank-stability score is the more complete temporal-stability measure.
"""
from __future__ import annotations

import math

from alpha_agent.scan.smoke import smoke_test

_EP = "divide(net_income_adjusted,multiply(close,shares_outstanding))"
# Stable: a per-ticker-constant fundamental — its ranking never changes day to day.
_STABLE = "rank(equity)"
# Unstable: rank of raw daily returns — each day is iid, so the ranking reshuffles.
_UNSTABLE = "rank(returns)"


def test_stable_factor_has_high_rank_stability():
    r = smoke_test(_STABLE, lookback=60)
    assert math.isfinite(r.rank_stability)
    assert r.rank_stability > 0.8, (
        f"a constant-fundamental rank should be perfectly stable day to day, got "
        f"{r.rank_stability:.3f}"
    )


def test_unstable_factor_has_low_rank_stability():
    r = smoke_test(_UNSTABLE, lookback=60)
    assert r.rank_stability < 0.5, (
        f"a rank-of-iid-returns factor should reshuffle daily, got "
        f"{r.rank_stability:.3f}"
    )


def test_rank_stability_separates_stable_from_unstable():
    stable = smoke_test(_STABLE, lookback=60).rank_stability
    unstable = smoke_test(_UNSTABLE, lookback=60).rank_stability
    assert stable > unstable + 0.4, (
        f"separation too small: stable={stable:.3f} unstable={unstable:.3f}"
    )


def test_value_factor_is_temporally_stable():
    """The canonical E/P value factor drifts slowly (only `close` moves), so its
    ranking should be temporally stable — the gauge must not flag it."""
    r = smoke_test(f"rank({_EP})", lookback=60)
    assert r.rank_stability > 0.6, (
        f"E/P value factor flagged unstable: {r.rank_stability:.3f}"
    )
