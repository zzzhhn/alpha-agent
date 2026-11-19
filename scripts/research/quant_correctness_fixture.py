"""Run fixed, offline inputs through the actual factor kernel and API functions.

Run with ``python scripts/research/quant_correctness_fixture.py`` from the
checkout under test, or put another checkout first on ``PYTHONPATH``.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd

from alpha_agent.api.routes import screener, zoo
from alpha_agent.backtest.engine import _max_drawdown as legacy_max_drawdown
from alpha_agent.core.types import FactorSpec
from alpha_agent.factor_engine import factor_backtest
from alpha_agent.factor_engine.factor_backtest import _Panel
from alpha_agent.factor_engine.kernel import (
    KernelParams,
    max_drawdown,
    run_kernel,
    spearman_ic,
    window_ic,
)
from alpha_agent.scan.significance import cross_correlation_matrix


def spec(expression: str) -> FactorSpec:
    return FactorSpec(
        name=expression, expression=expression, hypothesis="", justification="",
        lookback=5, universe="SP500", operators_used=[],
    )


def fixture_panel() -> _Panel:
    days, names = 32, 12
    gradient = np.arange(names, dtype=float) - 5.5
    time = np.arange(1, days, dtype=float)
    # Daily stock returns are known, with descending order the whole time.
    returns = -gradient * (0.001 + 0.00001 * time[:, None])
    close = 100.0 * np.vstack([np.ones(names), np.cumprod(1 + returns, axis=0)])
    volume = np.broadcast_to(10_000 + gradient, (days, names)).copy()
    open_ = np.broadcast_to(100 + gradient, (days, names)).copy()
    open_[-1, -1] = np.nan  # absent active score on the latest day only
    volume[-1, -2] = np.nan  # absent inactive score on the latest day only
    return _Panel(
        dates=np.busday_offset("2025-02-03", np.arange(days)),
        tickers=tuple(f"T{i:02d}" for i in range(names)), close=close,
        open_=open_, high=close, low=close, volume=volume,
        benchmark_close=np.full(days, 100.0),
    )


def tidy(value):
    if isinstance(value, (float, np.floating)):
        return round(float(value), 10) if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return tidy(value.tolist())
    if isinstance(value, (tuple, list)):
        return [tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items()}
    return value


def run_fixture() -> dict:
    panel = fixture_panel()
    tied = np.array([1.0, 1.0, 2.0, 3.0, 3.0])
    order = np.arange(1.0, 6.0)
    constant = np.ones_like(order)
    result: dict = {
        "IC": {
            "ties": spearman_ic(tied, order),
            "untied_control": spearman_ic(order, order),
            "constant_factor": spearman_ic(constant, order),
            "constant_returns": spearman_ic(order, constant),
            "window_defined_and_constant": window_ic(
                np.stack([order, constant]), np.stack([order[::-1], order]), 0, 2,
            ),
        },
        "drawdown": {
            "initial_loss": max_drawdown(np.array([-0.1, 0.05])),
            "legacy_initial_loss": legacy_max_drawdown(pd.Series([-0.1, 0.05])),
            "first_period_gain_control": max_drawdown(np.array([0.1, -0.05])),
        },
    }
    for key, config in {
        "half_and_half": KernelParams(top_pct=0.50, bottom_pct=0.50),
        "half_and_half_with_10bps": KernelParams(
            top_pct=0.50, bottom_pct=0.50, transaction_cost_bps=10.0,
        ),
        "short_only_control": KernelParams(direction="short_only", bottom_pct=0.25),
    }.items():
        k = run_kernel(panel, spec("open"), config)
        w = k.weights[0]
        result[key] = {
            "n_long": int((w > 0).sum()), "n_short": int((w < 0).sum()),
            "long_gross": w[w > 0].sum(), "short_gross": -w[w < 0].sum(),
            "first_return": k.daily_ret[1], "last_return": k.daily_ret[-1],
            "final_nav": k.equity[-1], "train_ic": k.train_metrics.ic_spearman,
            "train_n_days": k.train_metrics.n_days,
        }
        if key == "half_and_half":
            result[key]["zoo_first_return"] = zoo._factor_daily_returns(
                k.factor, k.fwd_returns, config.top_pct, config.bottom_pct,
            )[1]

    bench = np.linspace(-0.025, 0.04, panel.close.shape[0])
    strategy = 0.001 + 2.0 * bench
    classed = np.full(len(bench), "bull")
    analysis_factor = np.broadcast_to(order, (len(bench), len(order)))
    for key, strategy_ret in {
        "complete_control": strategy,
        "interior_missing": np.where(np.arange(len(bench)) == 5, np.nan, strategy),
    }.items():
        r = factor_backtest._compute_regime_metrics(
            strategy_ret, analysis_factor, analysis_factor, bench, classed, slice(None),
        )[0]
        result.setdefault("regime", {})[key] = {"alpha": r.alpha_annualized, "days": r.n_days}

    # ρ(A,B)=0.6, ρ(A,C)=0 and constant D (undefined). The route still
    # performs real matrix/warning calculation, with series fixed at its input.
    series = (
        np.array([-1.0, -1.0, 1.0, 1.0]),
        np.array([-1.4, 0.2, -0.2, 1.4]),
        np.array([-1.0, 1.0, -1.0, 1.0]),
        np.zeros(4),
    )
    labels = ["A", "B", "C", "D"]
    _, corr, _ = cross_correlation_matrix(dict(zip(labels, series)))
    with patch.object(factor_backtest, "_load_panel", return_value=panel):
        with patch.object(zoo, "_factor_daily_returns", side_effect=series):
            zr = zoo.run_zoo_correlation(zoo.CorrelationRequest(
                factors=[{"spec": spec("open"), "label": s} for s in labels],
                warn_threshold=0.55,
            ))
        result["zoo"] = {
            "known_nonzero": corr[0, 1], "zero_control": zr.matrix[0][2],
            "constant_pair": zr.matrix[0][3],
            "identical_control": zr.matrix[0][0],
            "constant_diagonal": zr.matrix[3][3],
            "warnings": [[w.a, w.b] for w in zr.warnings],
        }
        signed = screener.run_screener(screener.ScreenerRequest(
            factors=[{"spec": spec("open"), "direction": "short_only"}],
            combine_method="ic_weighted",
        ))
        weighted = screener.run_screener(screener.ScreenerRequest(
            factors=[{"spec": spec("open"), "weight": 1}, {"spec": spec("volume"), "weight": 0}],
            combine_method="user_weighted",
        ))
        last_covered = next(r for r in weighted.recommendations if r.ticker == "T10")
        result["screener"] = {
            "short_direction_ic": signed.factor_diagnostics[0].in_window_ic,
            "short_direction_top_control": signed.recommendations[0].ticker,
            "only_available_score_is_zero_weight": any(
                r.ticker == "T11" for r in weighted.recommendations
            ),
            "missing_inactive_raw": last_covered.per_factor_scores[1].raw,
            "missing_inactive_z": last_covered.per_factor_scores[1].z,
            "missing_inactive_contribution_control": last_covered.per_factor_scores[1].contribution,
        }
    return tidy(result)


if __name__ == "__main__":
    print(json.dumps(run_fixture(), indent=2, allow_nan=False))
