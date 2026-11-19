"""Deterministic regressions for quantified research correctness fixes."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.routes import screener, zoo
from alpha_agent.backtest.engine import _max_drawdown as legacy_max_drawdown
from alpha_agent.backtest.ic_engine import _spearman_rho
from alpha_agent.factor_engine import factor_backtest
from alpha_agent.factor_engine.kernel import (
    KernelParams,
    max_drawdown,
    run_kernel,
    spearman_ic,
    split_metrics,
    window_ic,
)
from alpha_agent.factor_engine.portfolio import quantile_weights
from alpha_agent.scan.significance import cross_correlation_matrix
from scripts.research.quant_correctness_fixture import fixture_panel, spec


def test_spearman_ties_and_pairwise_missing_are_order_invariant() -> None:
    x = np.array([1.0, 1.0, 2.0, 3.0, 3.0, np.inf, np.nan])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, -10.0, 20.0])
    swap_within_ties = np.array([1, 0, 2, 4, 3, 6, 5])
    assert spearman_ic(x, y) == pytest.approx(np.sqrt(0.9))
    assert spearman_ic(x[swap_within_ties], y[swap_within_ties]) == pytest.approx(np.sqrt(0.9))
    assert _spearman_rho(x, y) == pytest.approx(np.sqrt(0.9))


def test_constant_ic_and_missing_ic_do_not_artificially_shift_the_window() -> None:
    increasing = np.arange(4, dtype=float)
    constant = np.ones(4)
    assert spearman_ic(constant, increasing) == 0.0
    assert spearman_ic(increasing, constant) == 0.0
    assert np.isnan(_spearman_rho(increasing, constant))
    assert window_ic(np.stack([increasing, constant]), np.stack([-increasing, increasing]), 0, 2) == -1.0
    # A real zero (not just a placeholder) must still count toward the mean.
    measured_zero = np.array([1.0, 3.0, 0.0, 2.0])
    assert spearman_ic(increasing, measured_zero) == pytest.approx(0.0)
    assert window_ic(np.stack([increasing, increasing]), np.stack([-increasing, measured_zero]), 0, 2) == -0.5


def test_drawdown_includes_opening_capital_in_both_engines() -> None:
    returns = np.array([-0.10, 0.05])
    assert max_drawdown(returns) == pytest.approx(-0.10)
    assert legacy_max_drawdown(pd.Series(returns)) == pytest.approx(-0.10)
    assert max_drawdown(np.array([0.10, -0.05])) == pytest.approx(-0.05)
    arrays = np.ones((1, 3))
    m = split_metrics(returns[:1], arrays, arrays, arrays, 0, 1)
    assert m.n_days == 1 and m.total_return == pytest.approx(-0.10)
    assert m.max_drawdown == pytest.approx(-0.10)


def test_kernel_and_zoo_share_equal_disjoint_baskets_on_same_returns() -> None:
    panel = fixture_panel()
    opts = KernelParams(top_pct=0.50, bottom_pct=0.50)
    free = run_kernel(panel, spec("open"), opts)
    paid = run_kernel(panel, spec("open"), replace(opts, transaction_cost_bps=10.0))
    np.testing.assert_allclose(free.weights[0], [-1.0 / 6] * 6 + [1.0 / 6] * 6)
    np.testing.assert_allclose(free.weights.clip(min=0).sum(axis=1), 1.0)
    np.testing.assert_allclose(free.weights.clip(max=0).sum(axis=1), -1.0)
    np.testing.assert_array_equal(paid.weights, free.weights)
    np.testing.assert_allclose(free.daily_ret[1:3] - paid.daily_ret[1:3], [0.002, 0.0])
    assert free.daily_ret[1] == pytest.approx(-0.00606)
    returns = zoo._factor_daily_returns(free.factor, free.fwd_returns, 0.5, 0.5)
    np.testing.assert_array_equal(returns, free.daily_ret)


def test_basket_sizes_with_odd_count_tiny_cutoff_and_constant_signal() -> None:
    row = np.array([[0.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 5.0, 5.0, 9.0, 10.0]])
    np.testing.assert_allclose(quantile_weights(row, 0.5, 0.5), [[-0.2] * 5 + [0.0] + [0.2] * 5])
    np.testing.assert_array_equal(quantile_weights(row, 0.01, 0.01), [[-1.0] + [0.0] * 9 + [1.0]])
    np.testing.assert_array_equal(quantile_weights(np.ones_like(row), 0.5, 0.5), 0.0)
    fwd = np.tile(row, (3, 1))
    assert np.isnan(zoo._factor_daily_returns(np.ones_like(fwd), fwd, 0.5, 0.5)).all()


def test_regime_regression_drops_missing_observations_by_date() -> None:
    bench = np.linspace(-0.025, 0.04, 32)
    strategy = 0.001 + 2 * bench
    strategy[5] = np.nan
    bench[14] = np.nan
    factor = np.tile(np.arange(4, dtype=float), (32, 1))
    [regime] = factor_backtest._compute_regime_metrics(
        strategy, factor, factor, bench, np.full(32, "bull"), slice(None),
    )
    assert regime.n_days == 31
    assert regime.alpha_annualized == pytest.approx(0.252, abs=1e-7)


def test_zoo_pearson_true_zero_undefined_and_request_threshold() -> None:
    series = {
        "A": np.array([-1.0, -1.0, 1.0, 1.0]),
        "B": np.array([-1.4, 0.2, -0.2, 1.4]),
        "C": np.array([-1.0, 1.0, -1.0, 1.0]),
        "D": np.zeros(4),
    }
    _, matrix, warnings = cross_correlation_matrix(series, warn_threshold=0.55)
    assert matrix[0, 1] == pytest.approx(0.6)
    assert matrix[0, 2] == 0.0
    assert np.isnan(matrix[0, 3]) and np.isnan(matrix[3, 3])
    assert {w[:2] for w in warnings} == {("A", "B"), ("B", "C")}
    _, matrix, _ = cross_correlation_matrix({
        "A": np.array([1.0, 2.0, np.nan, np.nan]),
        "B": np.array([np.nan, np.nan, 3.0, 4.0]),
    })
    assert np.isnan(matrix[0, 1])


def test_zoo_http_json_distinguishes_missing_fields_and_warns_from_actual_baskets(monkeypatch) -> None:
    panel = fixture_panel()
    panel = replace(panel, volume=np.ones_like(panel.volume))
    monkeypatch.setattr(factor_backtest, "_load_panel", lambda: panel)
    app = FastAPI()
    app.include_router(zoo.router)
    body = zoo.CorrelationRequest(factors=[
        {"spec": spec("open"), "label": "A"}, {"spec": spec("open"), "label": "B"},
        {"spec": spec("volume"), "label": "constant"},
    ], warn_threshold=0.55)
    response = TestClient(app).post("/api/v1/zoo/correlation", json=body.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["matrix"] == [[1.0, 1.0, None], [1.0, 1.0, None], [None, None, None]]
    assert data["warn_threshold"] == 0.55
    assert data["warnings"] == [{"a": "A", "b": "B", "corr": 1.0}]


@pytest.mark.parametrize("combine_method", ["ic_weighted", "user_weighted"])
def test_screener_http_only_nonzero_weights_confer_eligibility(monkeypatch, combine_method) -> None:
    monkeypatch.setattr(factor_backtest, "_load_panel", fixture_panel)
    app = FastAPI()
    app.include_router(screener.router)
    body = screener.ScreenerRequest(factors=[
        {"spec": spec("open"), "direction": "short_only", "weight": 1.0},
        {"spec": spec("volume"), "weight": 0.0},
    ], combine_method=combine_method)
    response = TestClient(app).post("/api/v1/screener/run", json=body.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert [d["in_window_ic"] for d in data["factor_diagnostics"]] == [1.0, -1.0]
    assert [d["used_weight"] for d in data["factor_diagnostics"]] == [1.0, 0.0]
    assert data["metadata"]["n_eligible_tickers"] == 11
    recs = data["recommendations"]
    assert recs[0]["ticker"] == "T00"
    assert not any(r["ticker"] == "T11" for r in recs)
    assert recs[-1]["per_factor_scores"][1] == {
        "factor_idx": 1, "raw": None, "z": None, "contribution": 0.0,
    }
