"""Phase B2: the skeptic pass — a SEPARATE LLM review (not the proposer) that
reads a survivor + its backtest evidence and flags why the good-looking result
might be lying (overfit, cost-sensitivity, single-fold luck, correlation). It
never blocks a proposal; it only annotates risk for the human gate."""
import json
from unittest.mock import AsyncMock

import pytest

from alpha_agent.evolution.skeptic import assess_candidate
from alpha_agent.llm.base import LLMResponse


def _resp(content: str) -> LLMResponse:
    return LLMResponse(content=content, model="", prompt_tokens=0, completion_tokens=0)


@pytest.mark.asyncio
async def test_assess_parses_verdict():
    client = AsyncMock()
    client.chat.return_value = _resp(json.dumps({
        "risk_level": "high",
        "concerns": ["high turnover — cost-sensitive", "single strong fold"],
        "summary": "Looks regime-fit; verify OOS decay.",
    }))
    v = await assess_candidate(
        client, "rank(ts_mean(returns, 8))",
        {"sharpes": [2.1, 0.1, 0.2], "ic_oos": 0.03, "deflated_sharpe": 0.4},
    )
    assert v is not None
    assert v.risk_level == "high"
    assert "high turnover — cost-sensitive" in v.concerns
    assert v.summary.startswith("Looks regime-fit")
    # the evidence reached the skeptic prompt (separate reviewer, not generator)
    sent = client.chat.call_args.kwargs["messages"][0].content
    assert "rank(ts_mean(returns, 8))" in sent
    assert "skeptical" in sent.lower()


@pytest.mark.asyncio
async def test_assess_bad_json_returns_none():
    client = AsyncMock()
    client.chat.return_value = _resp("sorry, I cannot help with that")
    v = await assess_candidate(client, "rank(x)", {})
    assert v is None


@pytest.mark.asyncio
async def test_assess_clamps_unknown_risk_level():
    client = AsyncMock()
    client.chat.return_value = _resp(json.dumps({
        "risk_level": "catastrophic", "concerns": [], "summary": "x"
    }))
    v = await assess_candidate(client, "rank(x)", {})
    assert v is not None
    assert v.risk_level == "medium"  # unknown level clamps to medium
