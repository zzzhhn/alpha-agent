"""BacktestAgent — runs backtest on each factor candidate."""

from __future__ import annotations

import logging

import pandas as pd

from alpha_agent.agents.base import BaseAgent
from alpha_agent.backtest.engine import BacktestEngine
from alpha_agent.factor_engine.evaluator import ExprEvaluator
from alpha_agent.factor_engine.parser import ExprParser, ParseError
from alpha_agent.pipeline.state import FactorResult, PipelineState

logger = logging.getLogger(__name__)

# Thresholds for a factor to "pass"
_IC_THRESHOLD = 0.02
_ICIR_THRESHOLD = 0.5


class BacktestAgent(BaseAgent):
    """Runs backtest on each factor candidate and attaches results.

    This agent does not call the LLM — it wraps the computation engine.
    """

    def __init__(
        self,
        llm: object,
        data: pd.DataFrame,
        engine: BacktestEngine | None = None,
    ) -> None:
        super().__init__(llm)
        self._data = data
        self._engine = engine or BacktestEngine()
        self._parser = ExprParser()
        self._evaluator = ExprEvaluator()

    async def run(self, state: PipelineState) -> PipelineState:
        if not state.factors:
            logger.warning("No factor candidates to backtest")
            return state

        results: list[FactorResult] = []

        for candidate in state.factors:
            try:
                ast = self._parser.parse(candidate.expression)
                factor_values = self._evaluator.evaluate(ast, self._data)
                bt_result = self._engine.run(factor_values, self._data)

                passed = (
                    abs(bt_result.ic_mean) > _IC_THRESHOLD
                    and abs(bt_result.icir) > _ICIR_THRESHOLD
                )

                results.append(
                    FactorResult(
                        candidate=candidate,
                        ic_mean=bt_result.ic_mean,
                        icir=bt_result.icir,
                        rank_ic_mean=bt_result.rank_ic_mean,
                        sharpe_ratio=bt_result.sharpe_ratio,
                        max_drawdown=bt_result.max_drawdown,
                        turnover=bt_result.turnover,
                        alpha_decay=bt_result.alpha_decay,
                    )
                )
                logger.info(
                    "Backtested %s: IC=%.4f ICIR=%.4f passed=%s",
                    candidate.expression,
                    bt_result.ic_mean,
                    bt_result.icir,
                    passed,
                )
            except (ParseError, Exception) as e:
                logger.warning(
                    "Skipping factor %r: %s", candidate.expression, e
                )

        return state.with_updates(
            results=tuple(results),
            all_results=state.all_results + tuple(results),
        )
