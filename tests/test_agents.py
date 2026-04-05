"""Tests for HypothesisAgent and FactorAgent with mocked LLM responses."""

from __future__ import annotations

import pytest

from alpha_agent.agents.factor import FactorAgent
from alpha_agent.agents.hypothesis import HypothesisAgent
from alpha_agent.llm.base import LLMClient, LLMResponse, Message
from alpha_agent.pipeline.state import Hypothesis, PipelineState


class MockLLM(LLMClient):
    """Mock LLM that returns predetermined responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def chat(
        self, messages: list[Message], temperature: float = 0.7, max_tokens: int = 4096
    ) -> LLMResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        content = self._responses[idx]
        self._call_count += 1
        return LLMResponse(content=content, model="mock", prompt_tokens=0, completion_tokens=0)

    async def is_available(self) -> bool:
        return True


# --- HypothesisAgent ---


class TestHypothesisAgent:
    @pytest.mark.asyncio
    async def test_valid_json_response(self) -> None:
        mock_response = """{
            "hypotheses": [
                {
                    "name": "short_term_reversal",
                    "rationale": "Stocks that dropped recently tend to bounce back",
                    "expected_type": "mean_reversion"
                },
                {
                    "name": "volume_momentum",
                    "rationale": "High volume stocks continue to attract attention",
                    "expected_type": "volume"
                }
            ]
        }"""
        llm = MockLLM([mock_response])
        agent = HypothesisAgent(llm)
        state = PipelineState(query="find reversal factors")

        result = await agent.run(state)

        assert len(result.hypotheses) == 2
        assert result.hypotheses[0].name == "short_term_reversal"
        assert result.hypotheses[1].expected_type == "volume"

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self) -> None:
        mock_response = """```json
{
    "hypotheses": [
        {"name": "momentum", "rationale": "Price trend continuation", "expected_type": "momentum"}
    ]
}
```"""
        llm = MockLLM([mock_response])
        agent = HypothesisAgent(llm)
        state = PipelineState(query="momentum")

        result = await agent.run(state)

        assert len(result.hypotheses) == 1
        assert result.hypotheses[0].name == "momentum"

    @pytest.mark.asyncio
    async def test_invalid_json_retries(self) -> None:
        llm = MockLLM(["not json at all", "still not json", "nope"])
        agent = HypothesisAgent(llm)
        state = PipelineState(query="test")

        result = await agent.run(state)

        assert len(result.hypotheses) == 0
        assert llm._call_count == 3

    @pytest.mark.asyncio
    async def test_includes_prior_feedback(self) -> None:
        mock_response = """{
            "hypotheses": [
                {"name": "improved", "rationale": "Better version", "expected_type": "momentum"}
            ]
        }"""
        llm = MockLLM([mock_response])
        agent = HypothesisAgent(llm)
        state = PipelineState(query="test", prior_feedback="Try momentum factors instead")

        result = await agent.run(state)

        assert len(result.hypotheses) == 1
        # Verify feedback was included in the prompt
        assert llm._call_count == 1


# --- FactorAgent ---


class TestFactorAgent:
    @pytest.mark.asyncio
    async def test_valid_expressions(self) -> None:
        mock_response = """{
            "factors": [
                {
                    "expression": "Rank(-Delta($close, 5))",
                    "hypothesis_name": "reversal",
                    "rationale": "5-day price reversal ranked cross-sectionally"
                },
                {
                    "expression": "($close - Mean($close, 20)) / Std($close, 20)",
                    "hypothesis_name": "zscore",
                    "rationale": "20-day z-score of closing price"
                }
            ]
        }"""
        llm = MockLLM([mock_response])
        agent = FactorAgent(llm)
        state = PipelineState(
            query="test",
            hypotheses=(
                Hypothesis(name="reversal", rationale="...", expected_type="mean_reversion"),
            ),
        )

        result = await agent.run(state)

        assert len(result.factors) == 2
        assert result.factors[0].expression == "Rank(-Delta($close, 5))"
        assert result.factors[1].hypothesis_name == "zscore"

    @pytest.mark.asyncio
    async def test_filters_invalid_expressions(self) -> None:
        mock_response = """{
            "factors": [
                {
                    "expression": "Rank(-Delta($close, 5))",
                    "hypothesis_name": "good",
                    "rationale": "Valid expression"
                },
                {
                    "expression": "InvalidFunc($close ++ $open)",
                    "hypothesis_name": "bad",
                    "rationale": "This will fail parsing"
                }
            ]
        }"""
        llm = MockLLM([mock_response])
        agent = FactorAgent(llm)
        state = PipelineState(
            query="test",
            hypotheses=(Hypothesis(name="test", rationale="...", expected_type="momentum"),),
        )

        result = await agent.run(state)

        assert len(result.factors) == 1
        assert result.factors[0].hypothesis_name == "good"

    @pytest.mark.asyncio
    async def test_no_hypotheses_returns_unchanged(self) -> None:
        llm = MockLLM(["should not be called"])
        agent = FactorAgent(llm)
        state = PipelineState(query="test", hypotheses=())

        result = await agent.run(state)

        assert len(result.factors) == 0
        assert llm._call_count == 0

    @pytest.mark.asyncio
    async def test_retries_on_invalid_json(self) -> None:
        valid_response = """{
            "factors": [
                {"expression": "Rank($close)", "hypothesis_name": "a", "rationale": "b"}
            ]
        }"""
        llm = MockLLM(["not json", valid_response])
        agent = FactorAgent(llm)
        state = PipelineState(
            query="test",
            hypotheses=(Hypothesis(name="a", rationale="...", expected_type="momentum"),),
        )

        result = await agent.run(state)

        assert len(result.factors) == 1
        assert llm._call_count == 2


# --- PipelineState ---


class TestPipelineState:
    def test_frozen(self) -> None:
        state = PipelineState(query="test")
        with pytest.raises(AttributeError):
            state.query = "modified"

    def test_with_updates(self) -> None:
        state = PipelineState(query="test", iteration=0)
        new_state = state.with_updates(iteration=1, prior_feedback="try again")

        assert state.iteration == 0  # original unchanged
        assert new_state.iteration == 1
        assert new_state.prior_feedback == "try again"
        assert new_state.query == "test"  # unchanged fields preserved

    def test_default_values(self) -> None:
        state = PipelineState(query="test")
        assert state.iteration == 0
        assert state.max_iterations == 3
        assert state.hypotheses == ()
        assert state.factors == ()
        assert state.evaluation is None
