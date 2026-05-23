import json
from unittest.mock import AsyncMock

import pytest

from alpha_agent.evolution.diagnostics import Diagnostic
from alpha_agent.evolution.llm_factor_proposer import RawProposal, propose_factors
from alpha_agent.llm.base import LLMResponse


def _llm_resp(content: str) -> LLMResponse:
    """Helper: LLMResponse requires model/prompt_tokens/completion_tokens."""
    return LLMResponse(content=content, model="", prompt_tokens=0, completion_tokens=0)


@pytest.fixture
def diagnostic():
    return Diagnostic(
        current_expression="rank(ts_mean(returns, 12))",
        weak_signal="news_24h", weak_signal_ic=0.003,
        worst_fold_sharpe=None, worst_fold_window=None,
        symptom_summary="News IC dropped below 0.01.",
    )


@pytest.fixture
def mock_llm():
    """LLMClient.chat returns an LLMResponse with .content holding JSON."""
    client = AsyncMock()
    client.chat.return_value = _llm_resp(json.dumps({
        "proposals": [
            {
                "expression": "rank(ts_mean(returns, 8))",
                "new_operators": [],
                "rationale": "Shorter window for faster-moving regime.",
            },
            {
                "expression": "rank(lf_decay_mean(returns, 12))",
                "new_operators": [{
                    "name": "lf_decay_mean",
                    "signature": "(x: ndarray, window: int) -> ndarray",
                    "python_impl": ("import numpy as np\ndef lf_decay_mean(x, window):\n"
                                    "    w = np.exp(-np.arange(window) / window)\n"
                                    "    out = np.full_like(x, np.nan)\n"
                                    "    for i in range(window, len(x)):\n"
                                    "        out[i] = np.sum(x[i-window:i] * w[::-1]) / w.sum()\n"
                                    "    return out"),
                    "doc": "Exponentially decayed mean over the last window samples.",
                }],
                "rationale": "Decay emphasis on recent returns.",
            },
        ],
    }))
    return client


@pytest.mark.asyncio
async def test_proposer_returns_n_raw_proposals(mock_llm, diagnostic):
    out = await propose_factors(mock_llm, diagnostic, n=2)
    assert len(out) == 2
    assert all(isinstance(p, RawProposal) for p in out)
    assert out[0].expression == "rank(ts_mean(returns, 8))"
    assert out[1].new_operators[0]["name"] == "lf_decay_mean"


@pytest.mark.asyncio
async def test_proposer_rejects_invalid_operator_names(mock_llm, diagnostic):
    """lf_ prefix + char class are server-side enforced; bad ops are dropped."""
    mock_llm.chat.return_value = _llm_resp(json.dumps({
        "proposals": [{
            "expression": "rank(returns)",
            "new_operators": [{
                "name": "BadName",  # uppercase, no lf_ prefix
                "signature": "(x) -> x", "python_impl": "def BadName(x): return x", "doc": "",
            }],
            "rationale": "test",
        }],
    }))
    out = await propose_factors(mock_llm, diagnostic, n=1)
    assert len(out) == 1
    assert out[0].new_operators == []  # invalid op stripped; expression kept


@pytest.mark.asyncio
async def test_proposer_retries_once_on_json_parse_failure(mock_llm, diagnostic):
    """Forgiveness UX: bad JSON gets one structured retry, not an immediate raise."""
    mock_llm.chat.side_effect = [
        _llm_resp("this is not JSON at all"),
        _llm_resp(json.dumps({"proposals": [
            {"expression": "rank(returns)", "new_operators": [], "rationale": "ok"}
        ]})),
    ]
    out = await propose_factors(mock_llm, diagnostic, n=1)
    assert len(out) == 1
    assert mock_llm.chat.call_count == 2


@pytest.mark.asyncio
async def test_proposer_raises_when_retry_also_fails(mock_llm, diagnostic):
    """After 2 failed parses, propose_factors raises so the endpoint can 502."""
    mock_llm.chat.side_effect = [
        _llm_resp("still not JSON"),
        _llm_resp("also not JSON"),
    ]
    with pytest.raises(ValueError, match="parse"):
        await propose_factors(mock_llm, diagnostic, n=1)


@pytest.mark.asyncio
async def test_proposer_caps_n_at_hard_limit(mock_llm, diagnostic):
    """n parameter is clamped to 1..8; passing n=15 reduces to 8 in the prompt."""
    await propose_factors(mock_llm, diagnostic, n=15)
    call_kwargs = mock_llm.chat.call_args
    # The prompt string should mention "8" (clamped n), not "15".
    # messages is passed as a keyword arg; args tuple may be empty.
    messages = call_kwargs.kwargs.get("messages") or (call_kwargs.args[0] if call_kwargs.args else [])
    prompt = messages[0].content
    assert "8" in prompt
