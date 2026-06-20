"""Smoke-test turnover gauge.

A factor's expression should be the cross-sectional alpha LEVEL; "long/short"
is a backtest setting, not part of the expression. When the LLM instead emits a
day-over-day CHANGE of a level — e.g. sub(rank(X), ts_delay(rank(X), 1)) ≡
ts_delta(rank(X), 1) — the resulting portfolio churns its whole book every period
and is annihilated by transaction costs (observed live: turnover 274%, Sharpe
-6.8) even though the AST guard and the degeneracy (factor_std) check both pass.

smoke_test therefore estimates the factor's rebalance turnover on the synthetic
panel using the engine's own quantile-weight + L1-turnover definition
(kernel.py:493-511 build weights, :344-348 define turnover = mean_t Σ|Δw|). The
estimate UNDERSTATES real turnover (synthetic fundamentals are per-ticker
constants, only `close` moves) but cleanly DISCRIMINATES level vs change factors:
calibration showed level factors 0-41% vs change factors 104-275%.
"""
from __future__ import annotations

import math

from alpha_agent.scan.smoke import smoke_test

_EP = "divide(net_income_adjusted,multiply(close,shares_outstanding))"
_LEVEL = f"rank({_EP})"  # the correct Basu value factor
_CHANGE = f"sub(rank({_EP}),ts_delay(rank({_EP}),1))"  # the mistranslation


def test_level_factor_has_low_turnover():
    r = smoke_test(_LEVEL, lookback=60)
    assert math.isfinite(r.turnover)
    assert r.turnover < 0.5, (
        f"a cross-sectional value LEVEL should turn over slowly, got "
        f"{r.turnover:.0%}"
    )


def test_change_factor_has_high_turnover():
    r = smoke_test(_CHANGE, lookback=60)
    assert r.turnover > 0.8, (
        f"a day-over-day CHANGE factor should churn its book, got "
        f"{r.turnover:.0%}"
    )


def test_turnover_separates_level_from_change():
    """The gauge's whole point: the change factor must churn far more than the
    level factor, so a single threshold can flag the mistranslation."""
    level = smoke_test(_LEVEL, lookback=60).turnover
    change = smoke_test(_CHANGE, lookback=60).turnover
    assert change > 2.0 * level, (
        f"change/level turnover separation too small: change={change:.0%} "
        f"level={level:.0%}"
    )
