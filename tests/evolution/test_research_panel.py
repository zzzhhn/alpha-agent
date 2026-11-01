from dataclasses import replace

import numpy as np
import pytest

from alpha_agent.evolution.research_panel import (
    InvalidEvaluation, check_operands, context_from_panel, load_research_context,
    score_expression, slice_panel,
)


@pytest.fixture(scope="module")
def context():
    return load_research_context()


def test_real_dates_values_and_held_out_ranges(context):
    from alpha_agent.factor_engine.factor_backtest import _load_panel
    source = _load_panel()
    np.testing.assert_equal(context.panel.volume, source.volume[-504:])
    np.testing.assert_equal(context.panel.open_, source.open_[-504:])
    assert all(a > context.search_end and b > a for a, b in context.folds)
    assert all(b < a2 for (_, b), (a2, _) in zip(context.folds, context.folds[1:]))
    with pytest.raises(InvalidEvaluation, match="invalid_timeline"):
        context_from_panel(replace(context.panel, dates=context.panel.dates[::-1]))


def test_missing_fundamentals_are_invalid_not_zero(context):
    with pytest.raises(InvalidEvaluation, match="insufficient_operand_coverage"):
        check_operands(context, "rank(free_cash_flow)")


def test_held_out_metrics_match_same_main_kernel(context):
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.kernel import KernelParams, run_kernel, split_metrics
    expr = "rank(ts_mean(returns, 20))"
    sharpes, ic, actual = score_expression(context, expr)
    spec = FactorSpec(name="control", hypothesis="control", expression=expr,
                      operators_used=[], lookback=120, universe="SP500", justification="control")
    reference = run_kernel(context.panel, spec, KernelParams(
        train_ratio=0.6, transaction_cost_bps=10, short_borrow_bps=100,
        purge_days=5, embargo_days=5))
    np.testing.assert_allclose(actual.daily_ret, reference.daily_ret, equal_nan=True)
    expected = [split_metrics(reference.daily_ret, reference.factor, reference.fwd_returns,
                              reference.weights, start=a + 1, end=b, n_trials=1).sharpe
                for a, b in context.folds]
    np.testing.assert_allclose(sharpes, expected)
    assert np.isfinite(ic)


def test_kernel_exception_is_invalid(context, monkeypatch):
    def broken(*args, **kwargs):
        raise KeyError("sector")
    monkeypatch.setattr("alpha_agent.factor_engine.kernel.run_kernel", broken)
    with pytest.raises(InvalidEvaluation, match="kernel_exception"):
        score_expression(context, "rank(volume)")


def test_short_panel_cannot_manufacture_folds(context):
    with pytest.raises(InvalidEvaluation, match="invalid_timeline"):
        context_from_panel(slice_panel(context.panel, 0, 20))


@pytest.mark.asyncio
async def test_invalid_baseline_never_queues_a_proposal(context, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from alpha_agent.api.routes import factor_lab
    from alpha_agent.evolution.llm_factor_proposer import RawProposal
    pool = SimpleNamespace(execute=AsyncMock())
    monkeypatch.setattr(factor_lab, "evaluate_factor_candidate", AsyncMock(return_value=None))
    result = await factor_lab._evaluate_and_record(
        pool, [RawProposal(expression="rank(volume)")],
        SimpleNamespace(current_expression="rank(free_cash_flow)"), context=context)
    assert result["ok"] is False
    assert result["status"] == "invalid_evaluation"
    pool.execute.assert_not_called()
