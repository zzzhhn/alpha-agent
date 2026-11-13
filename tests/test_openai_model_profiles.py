from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from alpha_agent.api.byok import _build_byok_client
from alpha_agent.llm._legacy.openai import OpenAIClient
from alpha_agent.llm.base import LLMResponse, Message
from alpha_agent.llm.model_profiles import estimate_standard_cost


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
async def test_explicit_sol_effort_preserves_total_budget_and_usage(monkeypatch, effort):
    response = SimpleNamespace(
        model="gpt-6.1-sol",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=12000, completion_tokens=4096,
            prompt_tokens_details=SimpleNamespace(cached_tokens=8000),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=3000)),
    )
    request = AsyncMock(return_value=response)
    monkeypatch.setattr("alpha_agent.llm.litellm_client.litellm.acompletion", request)
    client = _build_byok_client("openai", "fake", None, "gpt-6.1-sol", reasoning_effort=effort)
    result = await client.chat([Message("user", "hi")], max_tokens=4096)
    assert result == LLMResponse("ok", "gpt-6.1-sol", 12000, 4096, "stop", 8000, 3000)
    sent = request.call_args.kwargs
    assert sent["reasoning_effort"] == effort
    assert sent["max_completion_tokens"] == 4096
    assert sent["num_retries"] == 0
    assert "temperature" not in sent
    request.assert_awaited_once()


@pytest.mark.parametrize(("provider", "base", "model", "effort"), [
    ("openai", None, "gpt-6.1-sol", "none"),
    ("openai", None, "gpt-6.1-sol", "typo"),
    ("openai", None, "unknown-model", "high"),
    ("openai", "https://api.kimi.com/coding/v1", "kimi-for-coding", "high"),
])
def test_invalid_effort_rejected_before_request(provider, base, model, effort):
    with pytest.raises(ValueError):
        _build_byok_client(provider, "fake", base, model, reasoning_effort=effort)


def test_cached_cost_does_not_double_count_reasoning():
    result = LLMResponse("ok", "gpt-6.1-sol", 12000, 4096, "stop", 8000, 3000)
    cost = estimate_standard_cost(result, api_base="https://api.openai.com/v1")
    assert cost["amount_usd"] == pytest.approx(0.04976)
    assert cost["basis"] == "standard_cache_adjusted_estimate"
    assert cost["pricing_as_of"] == "2026-11-13"
    uncached = estimate_standard_cost(
        LLMResponse("ok", "gpt-6.1-sol", 12000, 4096), api_base="https://api.openai.com/v1",
    )
    assert uncached["amount_usd"] == pytest.approx(0.06496)
    assert uncached["basis"] == "standard_uncached_estimate"


@pytest.mark.parametrize(("response", "base"), [
    (LLMResponse("ok", "unknown-model", 12000, 1000), "https://api.openai.com/v1"),
    (LLMResponse("ok", "gpt-6.1-sol", 12000, 1000), "https://compatible.example/v1"),
    (LLMResponse("ok", "gpt-6.1-sol", 0, 0), "https://api.openai.com/v1"),
    (LLMResponse("ok", "gpt-6.1-sol", 12000, 1000, cached_prompt_tokens=13000), "https://api.openai.com/v1"),
    (LLMResponse("ok", "gpt-6.1-sol", 300000, 1000), "https://api.openai.com/v1"),
])
def test_unknown_or_out_of_scope_cost_stays_unknown(response, base):
    assert estimate_standard_cost(response, api_base=base) is None


async def test_legacy_openai_kill_switch_uses_same_sol_contract():
    import json
    received = []

    async def respond(request):
        received.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "gpt-6.1-sol", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8,
                      "prompt_tokens_details": {"cached_tokens": 4},
                      "completion_tokens_details": {"reasoning_tokens": 6}},
        })

    client = OpenAIClient("fake", model="gpt-6.1-sol")
    await client.close()
    client._client = httpx.AsyncClient(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(respond))
    try:
        result = await client.chat([Message("user", "hi")], temperature=0.3, max_tokens=4096)
    finally:
        await client.close()
    assert received[0]["max_completion_tokens"] == 4096
    assert "temperature" not in received[0] and "max_tokens" not in received[0]
    assert result == LLMResponse("ok", "gpt-6.1-sol", 12, 8, "stop", 4, 6)
