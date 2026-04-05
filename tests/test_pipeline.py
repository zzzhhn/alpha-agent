"""Tests for the pipeline orchestrator and individual M3 agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from alpha_agent.agents.backtest import BacktestAgent
from alpha_agent.agents.evaluation import EvalAgent
from alpha_agent.llm.base import LLMResponse, Message
from alpha_agent.pipeline.state import (
    EvaluationDecision,
    FactorCandidate,
    FactorResult,
    Hypothesis,
    PipelineState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(content: str) -> AsyncMock:
    """Create a mock LLM that returns fixed content."""
    llm = AsyncMock()
    llm.chat = AsyncMock(
        return_value=LLMResponse(
            content=content,
            model="test",
            prompt_tokens=10,
            completion_tokens=20,
        )
    )
    llm.is_available = AsyncMock(return_value=True)
    return llm


def _sample_candidate(expr: str = "Rank(-Delta($close, 5))") -> FactorCandidate:
    return FactorCandidate(
        expression=expr,
        hypothesis_name="reversal",
        rationale="5-day return reversal",
    )


def _sample_result(
    expr: str = "Rank(-Delta($close, 5))",
    ic: float = 0.04,
    icir: float = 1.2,
) -> FactorResult:
    return FactorResult(
        candidate=_sample_candidate(expr),
        ic_mean=ic,
        icir=icir,
        rank_ic_mean=0.035,
        sharpe_ratio=0.8,
        max_drawdown=-0.15,
        turnover=0.3,
        alpha_decay=(0.04, 0.03, 0.02, 0.01, 0.005),
    )


# ---------------------------------------------------------------------------
# EvalAgent tests
# ---------------------------------------------------------------------------

class TestEvalAgent:
    @pytest.mark.asyncio
    async def test_accept_decision(self) -> None:
        response_json = json.dumps({
            "decision": "ACCEPT",
            "feedback": "Strong IC signal",
            "best_factor_expression": "Rank(-Delta($close, 5))",
            "suggestions": [],
        })
        llm = _mock_llm(response_json)
        agent = EvalAgent(llm)

        state = PipelineState(
            query="test",
            results=(_sample_result(),),
        )
        new_state = await agent.run(state)

        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "accept"
        assert new_state.evaluation.best_factor is not None

    @pytest.mark.asyncio
    async def test_refine_decision(self) -> None:
        response_json = json.dumps({
            "decision": "REFINE",
            "feedback": "Try longer lookback window",
            "best_factor_expression": "",
            "suggestions": ["Use 20-day window instead of 5"],
        })
        llm = _mock_llm(response_json)
        agent = EvalAgent(llm)

        state = PipelineState(
            query="test",
            results=(_sample_result(ic=0.015, icir=0.4),),
        )
        new_state = await agent.run(state)

        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "refine"
        assert "longer lookback" in new_state.prior_feedback

    @pytest.mark.asyncio
    async def test_reject_decision(self) -> None:
        response_json = json.dumps({
            "decision": "REJECT",
            "feedback": "No predictive power",
            "suggestions": [],
        })
        llm = _mock_llm(response_json)
        agent = EvalAgent(llm)

        state = PipelineState(
            query="test",
            results=(_sample_result(ic=0.001, icir=0.1),),
        )
        new_state = await agent.run(state)

        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "reject"

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        llm = _mock_llm("")
        agent = EvalAgent(llm)

        state = PipelineState(query="test", results=())
        new_state = await agent.run(state)

        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "reject"

    @pytest.mark.asyncio
    async def test_markdown_fence_stripping(self) -> None:
        fenced = '```json\n' + json.dumps({
            "decision": "ACCEPT",
            "feedback": "Good",
            "best_factor_expression": "Rank(-Delta($close, 5))",
            "suggestions": [],
        }) + '\n```'
        llm = _mock_llm(fenced)
        agent = EvalAgent(llm)

        state = PipelineState(query="test", results=(_sample_result(),))
        new_state = await agent.run(state)

        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "accept"

    @pytest.mark.asyncio
    async def test_invalid_json_retries(self) -> None:
        llm = _mock_llm("not json at all")
        agent = EvalAgent(llm)

        state = PipelineState(query="test", results=(_sample_result(),))
        new_state = await agent.run(state)

        # Falls back to reject after all retries
        assert new_state.evaluation is not None
        assert new_state.evaluation.decision == "reject"
        assert llm.chat.call_count == 3  # 3 retries


# ---------------------------------------------------------------------------
# PipelineState immutability and with_updates
# ---------------------------------------------------------------------------

class TestPipelineState:
    def test_with_updates_returns_new_state(self) -> None:
        state = PipelineState(query="test")
        new_state = state.with_updates(iteration=1)
        assert new_state.iteration == 1
        assert state.iteration == 0  # original unchanged

    def test_with_updates_preserves_other_fields(self) -> None:
        state = PipelineState(
            query="test",
            hypotheses=(Hypothesis(name="h1", rationale="r1", expected_type="momentum"),),
        )
        new_state = state.with_updates(iteration=2)
        assert len(new_state.hypotheses) == 1
        assert new_state.query == "test"

    def test_accumulate_results(self) -> None:
        state = PipelineState(query="test")
        r1 = _sample_result("expr1")
        r2 = _sample_result("expr2")
        state = state.with_updates(all_results=(r1,))
        state = state.with_updates(all_results=state.all_results + (r2,))
        assert len(state.all_results) == 2

    def test_frozen(self) -> None:
        state = PipelineState(query="test")
        with pytest.raises((AttributeError, TypeError)):
            state.query = "mutated"  # type: ignore[misc]
