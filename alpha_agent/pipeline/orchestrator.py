"""AlphaResearchPipeline — orchestrates the 4-agent feedback loop.

Flow: HypothesisAgent → FactorAgent → BacktestAgent → EvalAgent
If EvalAgent returns REFINE, loop back to FactorAgent (max 3 iterations).
Accepted factors are registered in FactorRegistry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from alpha_agent.agents.backtest import BacktestAgent
from alpha_agent.agents.evaluation import EvalAgent
from alpha_agent.agents.factor import FactorAgent
from alpha_agent.agents.hypothesis import HypothesisAgent
from alpha_agent.config import Settings
from alpha_agent.factor_engine.parser import ExprParser
from alpha_agent.factor_engine.regularizer import ASTRegularizer
from alpha_agent.llm.factory import create_llm_client
from alpha_agent.pipeline.registry import FactorRegistry
from alpha_agent.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """Immutable result of a complete pipeline execution."""

    query: str
    accepted_factors: tuple
    rejected_factors: tuple
    total_iterations: int
    all_states: tuple[PipelineState, ...]


class AlphaResearchPipeline:
    """Orchestrates HypothesisAgent → FactorAgent → BacktestAgent → EvalAgent.

    Supports a refinement loop: if EvalAgent returns "refine", the feedback
    is fed back to FactorAgent for up to ``max_iterations`` rounds.
    """

    def __init__(
        self,
        settings: Settings,
        data: pd.DataFrame,
        registry: FactorRegistry | None = None,
        max_iterations: int = 3,
    ) -> None:
        llm = create_llm_client(settings)
        self._hypothesis_agent = HypothesisAgent(llm)
        self._factor_agent = FactorAgent(llm)
        self._backtest_agent = BacktestAgent(llm, data=data)
        self._eval_agent = EvalAgent(llm)
        self._registry = registry
        self._regularizer = ASTRegularizer()
        self._parser = ExprParser()
        self._max_iterations = max_iterations

    async def run(self, query: str) -> PipelineResult:
        """Execute the full pipeline and return results."""
        state = PipelineState(
            query=query,
            max_iterations=self._max_iterations,
        )
        states: list[PipelineState] = []

        try:
            # Phase 1: Generate hypotheses (runs once)
            state = await self._hypothesis_agent.run(state)
            logger.info("Generated %d hypotheses", len(state.hypotheses))

            if not state.hypotheses:
                return self._build_result(query, states)

            # Phase 2: Factor generation → backtest → evaluation loop
            for iteration in range(self._max_iterations):
                state = state.with_updates(iteration=iteration)
                logger.info("=== Iteration %d/%d ===", iteration + 1, self._max_iterations)

                # Generate factors
                state = await self._factor_agent.run(state)
                logger.info("Generated %d factor candidates", len(state.factors))

                if not state.factors:
                    logger.warning("No factors generated, stopping")
                    break

                # Backtest
                state = await self._backtest_agent.run(state)
                logger.info("Backtested %d factors", len(state.results))

                if not state.results:
                    logger.warning("No backtest results, stopping")
                    break

                # Evaluate
                state = await self._eval_agent.run(state)
                states.append(state)

                if state.evaluation is None:
                    logger.warning("No evaluation returned, stopping")
                    break

                decision = state.evaluation.decision
                logger.info("Evaluation: %s", decision)

                if decision == "accept":
                    self._register_accepted(state)
                    break
                elif decision == "reject":
                    break
                # decision == "refine": loop continues with prior_feedback set

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)

        return self._build_result(query, states)

    def _register_accepted(self, state: PipelineState) -> None:
        """Register the best factor from an accepted evaluation."""
        if self._registry is None or state.evaluation is None:
            return

        best = state.evaluation.best_factor
        if best is None:
            return

        try:
            ast = self._parser.parse(best.candidate.expression)
            tree_hash = self._regularizer.tree_hash(ast)
            metrics = {
                "ic_mean": best.ic_mean,
                "icir": best.icir,
                "rank_ic_mean": best.rank_ic_mean,
                "sharpe_ratio": best.sharpe_ratio,
                "max_drawdown": best.max_drawdown,
                "turnover": best.turnover,
            }
            row_id = self._registry.add(
                expression=best.candidate.expression,
                hypothesis_name=best.candidate.hypothesis_name,
                rationale=best.candidate.rationale,
                metrics=metrics,
                tree_hash=tree_hash,
            )
            if row_id > 0:
                logger.info("Registered factor #%d: %s", row_id, best.candidate.expression)
            else:
                logger.info("Factor already registered (dedup): %s", best.candidate.expression)
        except Exception as e:
            logger.warning("Failed to register factor: %s", e)

    def _build_result(
        self, query: str, states: list[PipelineState]
    ) -> PipelineResult:
        """Build the final pipeline result from accumulated states."""
        accepted = []
        rejected = []

        for s in states:
            if s.evaluation and s.evaluation.decision == "accept" and s.evaluation.best_factor:
                accepted.append(s.evaluation.best_factor)
            for r in s.results:
                if r not in accepted:
                    rejected.append(r)

        return PipelineResult(
            query=query,
            accepted_factors=tuple(accepted),
            rejected_factors=tuple(rejected),
            total_iterations=len(states),
            all_states=tuple(states),
        )
