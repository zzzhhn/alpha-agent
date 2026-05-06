"""Tests for factor_engine.factor_backtest and POST /api/v1/factor/backtest.

Shape-first, not value-first: random market data makes exact Sharpe values
flaky, so we pin down structural invariants (curve length == panel length,
train_end_index == floor(T * ratio), currency/benchmark labels) and exercise
the documented error paths via FastAPI TestClient.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alpha_agent.core.types import FactorSpec

# Skip the whole module if the pre-cached parquet isn't checked in — tests
# become no-ops in that case rather than hard-failing CI on an env issue.
_PARQUET = (
    Path(__file__).resolve().parent.parent
    / "alpha_agent"
    / "data"
    / "factor_universe_1y.parquet"
)
pytestmark = pytest.mark.skipif(
    not _PARQUET.exists(),
    reason="factor_universe_1y.parquet not committed (run scripts/fetch_factor_universe.py)",
)


def _spec(expression: str = "sub(ts_mean(close, 5), close)") -> FactorSpec:
    return FactorSpec(
        name="mr_5d",
        hypothesis="short-term mean reversion vs 5-day moving average",
        expression=expression,
        operators_used=["sub", "ts_mean"],
        lookback=10,
        universe="SP500",
        justification="smoke test factor",
    )


# ── Engine-level tests ─────────────────────────────────────────────────────


def test_engine_shapes_and_split_index() -> None:
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    result = run_factor_backtest(_spec(), train_ratio=0.80)

    # equity and benchmark curves cover the full panel
    T = len(result.equity_curve)
    assert T > 50, f"panel too short for meaningful test: T={T}"
    assert len(result.benchmark_curve) == T

    # train_end_index == floor(T * train_ratio)
    assert result.train_end_index == int(T * 0.80)

    # curves carry {date, value} dicts (validated at the pydantic layer,
    # but engine-level shape check catches regressions pre-route)
    assert set(result.equity_curve[0].keys()) == {"date", "value"}
    assert set(result.benchmark_curve[0].keys()) == {"date", "value"}
    assert all(isinstance(p["value"], float) for p in result.equity_curve)

    # labels surface to the client so the chart can render currency + legend
    assert result.currency == "USD"
    assert result.benchmark_ticker == "SPY"
    assert result.factor_name == "mr_5d"


def test_engine_metrics_cover_both_splits() -> None:
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    result = run_factor_backtest(_spec(), train_ratio=0.80)

    # both splits must have at least a handful of realized days
    assert result.train_metrics.n_days > 10
    assert result.test_metrics.n_days > 10

    # metrics are finite (NaN would mean an empty slice or all-NaN returns)
    for m in (result.train_metrics, result.test_metrics):
        assert m.sharpe == m.sharpe, "sharpe must not be NaN"
        assert m.total_return == m.total_return, "total_return must not be NaN"
        assert m.ic_spearman == m.ic_spearman, "ic must not be NaN"


def test_engine_rejects_out_of_range_train_ratio() -> None:
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    with pytest.raises(ValueError, match="train_ratio"):
        run_factor_backtest(_spec(), train_ratio=0.05)
    with pytest.raises(ValueError, match="train_ratio"):
        run_factor_backtest(_spec(), train_ratio=0.99)


def test_engine_deterministic_given_same_spec() -> None:
    """Panel is pre-cached and factor is pure, so output must be stable."""
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    a = run_factor_backtest(_spec(), train_ratio=0.80)
    b = run_factor_backtest(_spec(), train_ratio=0.80)

    assert a.train_end_index == b.train_end_index
    assert a.train_metrics == b.train_metrics
    assert a.test_metrics == b.test_metrics
    # sample the tail in case early days are all-NaN and clamp to zero
    assert a.equity_curve[-1]["value"] == b.equity_curve[-1]["value"]


def test_transaction_cost_bps_reaches_pnl_end_to_end() -> None:
    """A6: confirm transaction_cost_bps actually subtracts from realized PnL
    via the wrapper, not just the kernel.

    Use a high-turnover mean-reversion spec so cost has bite. With cost=0 the
    test_metrics must equal the byte-equal pre-refactor numbers (verified
    via run-vs-run determinism); with cost=20 bps the same spec must show
    *strictly lower* total return on the same panel. Sharpe direction is
    not required to flip — high-turnover factors with weak edge can keep
    Sharpe sign while losing magnitude.
    """
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    # Mean-reversion at 5d → daily basket churns more than long-horizon factors.
    spec = _spec("sub(ts_mean(close, 5), close)")

    free = run_factor_backtest(spec, transaction_cost_bps=0.0)
    paid = run_factor_backtest(spec, transaction_cost_bps=20.0)

    assert paid.test_metrics.total_return < free.test_metrics.total_return, (
        f"cost did not reach PnL: free total_ret={free.test_metrics.total_return} "
        f"paid total_ret={paid.test_metrics.total_return}"
    )
    # Turnover is cost-invariant — only daily PnL changes, weights identical.
    assert (
        abs(free.test_metrics.turnover - paid.test_metrics.turnover) < 1e-12
    ), "turnover changed across cost levels — kernel pipeline order broken"


def test_walk_forward_returns_rolling_window_metrics() -> None:
    """A7: walk_forward mode populates result.walk_forward with one entry per
    rolling window. Static mode leaves it None. Same spec, two modes — the
    train/test SplitMetrics also live and are non-trivial in both cases.

    Expected window count: depends on panel length. 1y panel (~251 days)
    yields ~10 windows; 3y panel (~752 days) yields ~35. Bound generously
    so the test works on either checked-in panel.
    """
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    spec = _spec()

    static_r = run_factor_backtest(spec, mode="static")
    wf_r = run_factor_backtest(
        spec, mode="walk_forward", wf_window_days=60, wf_step_days=20,
    )

    assert static_r.walk_forward is None, "static mode must NOT populate walk_forward"
    assert wf_r.walk_forward is not None, "walk_forward mode must populate windows"
    assert 5 <= len(wf_r.walk_forward) <= 50, (
        f"unexpected window count {len(wf_r.walk_forward)} for 60d/20d on a 1-3y panel"
    )

    # Each window dict has the documented keys; sharpe is a real float.
    for w in wf_r.walk_forward:
        assert "window_start" in w and "window_end" in w
        assert "sharpe" in w and isinstance(w["sharpe"], float)
        assert "ic_spearman" in w and isinstance(w["ic_spearman"], float)
        assert w["sharpe"] == w["sharpe"], "window sharpe NaN — engine bug"

    # Static train/test still populated in walk_forward mode (back-compat).
    assert wf_r.train_metrics.n_days > 0
    assert wf_r.test_metrics.n_days > 0


def test_walk_forward_rejects_out_of_range_params() -> None:
    """A7 validation: window/step bounds enforced at the engine level."""
    from alpha_agent.factor_engine.factor_backtest import run_factor_backtest

    spec = _spec()
    with pytest.raises(ValueError, match="wf_window_days"):
        run_factor_backtest(spec, mode="walk_forward", wf_window_days=500)
    with pytest.raises(ValueError, match="wf_step_days"):
        run_factor_backtest(spec, mode="walk_forward", wf_window_days=60, wf_step_days=2)


# ── API-level tests (exercise pydantic + route glue) ───────────────────────


def _app_client() -> TestClient:
    # Build the same app api/index.py does so we cover the serverless entry
    import os

    os.environ.setdefault("SERVERLESS", "true")
    from fastapi import FastAPI

    from alpha_agent.api.routes.interactive import router as interactive_router

    app = FastAPI()
    app.include_router(interactive_router)
    return TestClient(app)


def _request_body(expression: str = "sub(ts_mean(close, 5), close)") -> dict:
    return {
        "spec": _spec(expression).model_dump(),
        "train_ratio": 0.80,
    }


def test_api_happy_path_returns_full_payload() -> None:
    client = _app_client()

    resp = client.post("/api/v1/factor/backtest", json=_request_body())
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["currency"] == "USD"
    assert body["benchmark_ticker"] == "SPY"
    assert body["factor_name"] == "mr_5d"
    assert body["train_end_index"] > 0
    assert len(body["equity_curve"]) == len(body["benchmark_curve"])
    assert body["equity_curve"][0].keys() == {"date", "value"}
    # Subset assertion — schema is additive (P4.1 turnover/MDD/hit_rate,
    # T1.4 ICIR/p-value, etc.). Strict equality breaks every additive PR.
    assert {"sharpe", "total_return", "ic_spearman", "n_days"} <= set(
        body["train_metrics"].keys()
    )


def test_api_rejects_unknown_operand_with_422() -> None:
    client = _app_client()

    # `foo` is not a whitelisted operand — AST walker must reject it with 422
    body = _request_body("sub(ts_mean(foo, 5), close)")
    # operators_used stays valid so pydantic accepts the spec; AST catches it
    resp = client.post("/api/v1/factor/backtest", json=body)
    assert resp.status_code == 422, resp.text
    assert "foo" in resp.text.lower() or "allowed" in resp.text.lower()


def test_api_rejects_out_of_range_train_ratio_with_422() -> None:
    client = _app_client()

    body = _request_body()
    body["train_ratio"] = 1.5
    resp = client.post("/api/v1/factor/backtest", json=body)
    assert resp.status_code == 422, resp.text


def test_api_rejects_malformed_spec_with_422() -> None:
    client = _app_client()

    body = _request_body()
    # operators_used contains a non-Literal value — pydantic should 422
    body["spec"]["operators_used"] = ["not_a_real_op"]
    resp = client.post("/api/v1/factor/backtest", json=body)
    assert resp.status_code == 422, resp.text
