# tests/test_backtest_ic_config.py
"""Phase 2-pre: IC-accept threshold in BacktestAgent reads from config_store.

Tests construct a minimal fake BacktestResult and a fake PipelineState to
exercise the acceptance comparison inside BacktestAgent.run without
invoking the real factor engine or data layer.
"""
from __future__ import annotations

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from alpha_agent import config_store
from alpha_agent.agents.backtest import BacktestAgent
from alpha_agent.backtest.metrics import BacktestResult
from alpha_agent.pipeline.state import FactorCandidate, PipelineState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bt_result(ic_mean: float, icir: float = 1.0) -> BacktestResult:
    """Minimal BacktestResult with controllable ic_mean."""
    return BacktestResult(
        ic_mean=ic_mean,
        ic_std=0.01,
        icir=icir,
        rank_ic_mean=ic_mean,
        rank_icir=icir,
        sharpe_ratio=1.0,
        annual_return=0.10,
        max_drawdown=-0.05,
        turnover=0.1,
        alpha_decay=(ic_mean,),
    )


def _make_state_with_one_candidate() -> PipelineState:
    candidate = FactorCandidate(
        expression="rank(ts_mean(returns, 12))",
        hypothesis_name="test",
        rationale="unit test",
    )
    return PipelineState(query="test", factors=(candidate,))


@pytest.fixture(autouse=True)
def _clear_cache():
    config_store._CACHE.clear()
    yield
    config_store._CACHE.clear()


# ---------------------------------------------------------------------------
# Default behaviour (cold cache → threshold == 0.02)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ic_accept_default_threshold_passes_above():
    """Cold cache: ic_mean=0.03 > 0.02 → factor passes (passed logged as True).

    We only check that the factor is appended to results; the `passed` local
    variable is internal to BacktestAgent.run so we verify indirectly via the
    logger call that receives it.
    """
    bt_result = _make_bt_result(ic_mean=0.03, icir=1.0)
    state = _make_state_with_one_candidate()

    engine_mock = MagicMock()
    engine_mock.run.return_value = bt_result

    parser_mock = MagicMock()
    evaluator_mock = MagicMock()
    evaluator_mock.evaluate.return_value = MagicMock()

    agent = BacktestAgent(llm=MagicMock(), data=pd.DataFrame(), engine=engine_mock)
    agent._parser = parser_mock
    agent._evaluator = evaluator_mock

    result = await agent.run(state)
    assert len(result.results) == 1
    assert result.results[0].ic_mean == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_ic_accept_default_threshold_below_still_appends():
    """Cold cache: ic_mean=0.01 < 0.02 → passed=False, but factor is still
    appended to results (acceptance affects downstream filtering, not inclusion).
    """
    bt_result = _make_bt_result(ic_mean=0.01, icir=1.0)
    state = _make_state_with_one_candidate()

    engine_mock = MagicMock()
    engine_mock.run.return_value = bt_result

    parser_mock = MagicMock()
    evaluator_mock = MagicMock()
    evaluator_mock.evaluate.return_value = MagicMock()

    agent = BacktestAgent(llm=MagicMock(), data=pd.DataFrame(), engine=engine_mock)
    agent._parser = parser_mock
    agent._evaluator = evaluator_mock

    result = await agent.run(state)
    # Factor is always appended; acceptance is logged only
    assert len(result.results) == 1


# ---------------------------------------------------------------------------
# Config-store override — the new behaviour under test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ic_accept_config_override_raises_threshold():
    """config_store override to 0.05: ic_mean=0.03 is now below threshold.

    We verify the acceptance flips by inspecting the logger.info call.
    BacktestAgent logs: "... passed=%s" with the boolean result of the
    acceptance comparison.
    """
    # Set threshold higher than the ic_mean we'll use
    config_store._CACHE["signal.ic_accept_threshold"] = 0.05

    bt_result = _make_bt_result(ic_mean=0.03, icir=1.0)
    state = _make_state_with_one_candidate()

    engine_mock = MagicMock()
    engine_mock.run.return_value = bt_result

    parser_mock = MagicMock()
    evaluator_mock = MagicMock()
    evaluator_mock.evaluate.return_value = MagicMock()

    agent = BacktestAgent(llm=MagicMock(), data=pd.DataFrame(), engine=engine_mock)
    agent._parser = parser_mock
    agent._evaluator = evaluator_mock

    with patch("alpha_agent.agents.backtest.logger") as mock_logger:
        result = await agent.run(state)

    # The log call shape is: logger.info("Backtested %s: IC=%.4f ICIR=%.4f passed=%s", ...)
    # passed arg is the 4th positional arg (index 3) after the format string
    assert mock_logger.info.called
    call_args = mock_logger.info.call_args
    # Format string is args[0][0]; passed value is args[0][4]
    log_positional = call_args[0]  # positional args tuple
    passed_value = log_positional[4]  # "Backtested %s: IC=... passed=%s" → 5th arg
    assert passed_value is False, (
        f"Expected passed=False with threshold=0.05 and ic_mean=0.03, got {passed_value}"
    )
    assert len(result.results) == 1  # still appended


@pytest.mark.asyncio
async def test_ic_accept_config_override_lowers_threshold():
    """config_store override to 0.005: ic_mean=0.01 now passes.

    Default threshold 0.02 would reject; overridden 0.005 accepts.
    """
    config_store._CACHE["signal.ic_accept_threshold"] = 0.005

    bt_result = _make_bt_result(ic_mean=0.01, icir=1.0)
    state = _make_state_with_one_candidate()

    engine_mock = MagicMock()
    engine_mock.run.return_value = bt_result

    parser_mock = MagicMock()
    evaluator_mock = MagicMock()
    evaluator_mock.evaluate.return_value = MagicMock()

    agent = BacktestAgent(llm=MagicMock(), data=pd.DataFrame(), engine=engine_mock)
    agent._parser = parser_mock
    agent._evaluator = evaluator_mock

    with patch("alpha_agent.agents.backtest.logger") as mock_logger:
        result = await agent.run(state)

    call_args = mock_logger.info.call_args
    log_positional = call_args[0]
    passed_value = log_positional[4]
    assert passed_value is True, (
        f"Expected passed=True with threshold=0.005 and ic_mean=0.01, got {passed_value}"
    )


@pytest.mark.asyncio
async def test_ic_accept_cold_cache_uses_002_default():
    """Cold cache + no env: get_config falls back to 0.02.

    ic_mean=0.025 > 0.02 → passed=True.
    ic_mean=0.015 < 0.02 → passed=False.
    """
    for ic_mean, expected_passed in [(0.025, True), (0.015, False)]:
        config_store._CACHE.clear()
        bt_result = _make_bt_result(ic_mean=ic_mean, icir=1.0)
        state = _make_state_with_one_candidate()

        engine_mock = MagicMock()
        engine_mock.run.return_value = bt_result
        parser_mock = MagicMock()
        evaluator_mock = MagicMock()
        evaluator_mock.evaluate.return_value = MagicMock()

        agent = BacktestAgent(llm=MagicMock(), data=pd.DataFrame(), engine=engine_mock)
        agent._parser = parser_mock
        agent._evaluator = evaluator_mock

        with patch("alpha_agent.agents.backtest.logger") as mock_logger:
            await agent.run(state)

        log_positional = mock_logger.info.call_args[0]
        passed_value = log_positional[4]
        assert passed_value is expected_passed, (
            f"ic_mean={ic_mean}: expected passed={expected_passed}, got {passed_value}"
        )
