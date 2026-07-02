"""Phase A: the LLM factor proposer becomes memory-aware — its prompt injects
recent lessons + already-tried expressions so it stops repeating rejects and
adjusts direction. These tests pin the injection contract on the pure
_build_prompt (no DB, no LLM)."""
import json
from unittest.mock import AsyncMock

import pytest

from alpha_agent.evolution.diagnostics import Diagnostic
from alpha_agent.evolution.llm_factor_proposer import (
    _build_prompt,
    propose_factors,
)
from alpha_agent.llm.base import LLMResponse


@pytest.fixture
def diagnostic():
    return Diagnostic(
        current_expression="rank(ts_mean(returns, 12))",
        weak_signal="news_24h", weak_signal_ic=0.003,
        worst_fold_sharpe=None, worst_fold_window=None,
        symptom_summary="News IC dropped below 0.01.",
    )


def test_build_prompt_injects_lessons_and_tried(diagnostic):
    p = _build_prompt(
        diagnostic, 3,
        lessons=[
            "KEEP `rank(ts_corr(close, volume, 20))` — OOS Sharpe 2.10, IC 0.031",
            "AVOID `divide(close, close)` — rejected: degenerate",
        ],
        tried_expressions=[
            "rank(ts_mean(returns, 8))",
            "rank(ts_mean(returns, 12))",
        ],
    )
    # lessons block present and verbatim
    assert "LESSONS FROM PRIOR ROUNDS" in p
    assert "OOS Sharpe 2.10" in p
    assert "divide(close, close)" in p
    # tried block present with an explicit do-not-repeat instruction
    assert "ALREADY TRIED" in p
    assert "rank(ts_mean(returns, 8))" in p


def test_build_prompt_omits_memory_when_empty(diagnostic):
    """No lessons / no tried → the memory sections are omitted entirely, so a
    fresh install behaves exactly as before (backward compatible)."""
    p = _build_prompt(diagnostic, 3)
    assert "LESSONS FROM PRIOR ROUNDS" not in p
    assert "ALREADY TRIED" not in p
    # the original diagnostic contract is untouched
    assert "rank(ts_mean(returns, 12))" in p


@pytest.mark.asyncio
async def test_propose_factors_accepts_memory_kwargs(diagnostic):
    client = AsyncMock()
    client.chat.return_value = LLMResponse(
        content=json.dumps({"proposals": [
            {"expression": "rank(ts_mean(returns, 8))", "new_operators": [], "rationale": "x"},
        ]}),
        model="", prompt_tokens=0, completion_tokens=0,
    )
    out = await propose_factors(
        client, diagnostic, n=1,
        lessons=["AVOID `foo` — rejected: degenerate"],
        tried_expressions=["bar"],
    )
    assert len(out) == 1
    # the injected memory reached the LLM prompt
    sent = client.chat.call_args.kwargs["messages"][0].content
    assert "AVOID `foo`" in sent
    assert "bar" in sent
