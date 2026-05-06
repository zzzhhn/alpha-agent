"""Structural validation of LiteLLMClient (A1).

These tests exercise the LiteLLMClient → litellm.acompletion call shape
without hitting real provider endpoints. We can't easily run live-API
tests in CI (no provider keys committed), so the value here is:

  1. Confirm `_kwargs()` constructs the right request envelope (model
     prefix, api_base, api_key, extra_headers all flow through)
  2. Confirm response unpacking handles OpenAI-compat shape (the common
     case) — content, model, usage all surface to LLMResponse correctly
  3. Confirm `thinking_fallback` branch fires only when content is empty
     and a reasoning_content / thinking field is present
  4. Confirm `is_available()` returns False on a network failure rather
     than propagating

Real-endpoint smoke is documented in scripts/smoke_litellm_live.py; run
it locally with the relevant API key set when validating a deploy.
"""
from __future__ import annotations

from unittest.mock import patch
from types import SimpleNamespace

import pytest

from alpha_agent.llm.base import Message
from alpha_agent.llm.litellm_client import LiteLLMClient


def _fake_response(content: str = "hello", reasoning: str = "") -> SimpleNamespace:
    """Minimal stand-in for a litellm ModelResponse."""
    msg = SimpleNamespace(content=content, reasoning_content=reasoning)
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=42, completion_tokens=7)
    return SimpleNamespace(
        choices=[choice], model="provider/whatever", usage=usage,
    )


@pytest.mark.asyncio
async def test_chat_forwards_kwargs_correctly() -> None:
    """Kimi-style construction sets all 4 knobs (model prefix, api_key,
    api_base, extra_headers) and they all flow into acompletion."""
    captured = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    client = LiteLLMClient(
        model="anthropic/kimi-for-coding",
        api_key="sk-test-fake",
        api_base="https://api.kimi.com/coding/v1",
        extra_headers={"User-Agent": "claude-cli/test", "anthropic-version": "2023-06-01"},
    )

    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_fake_acompletion):
        resp = await client.chat(
            [Message(role="user", content="hi")],
            temperature=0.5, max_tokens=128,
        )

    assert captured["model"] == "anthropic/kimi-for-coding"
    assert captured["api_key"] == "sk-test-fake"
    assert captured["api_base"] == "https://api.kimi.com/coding/v1"
    assert captured["extra_headers"] == {
        "User-Agent": "claude-cli/test",
        "anthropic-version": "2023-06-01",
    }
    assert captured["temperature"] == 0.5
    assert captured["max_tokens"] == 128
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert resp.content == "hello"
    assert resp.prompt_tokens == 42
    assert resp.completion_tokens == 7


@pytest.mark.asyncio
async def test_chat_omits_unset_optional_kwargs() -> None:
    """Ollama config has api_key=None; that field MUST NOT show up in the
    call (litellm would otherwise see api_key=None and try to auth)."""
    captured = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    client = LiteLLMClient(
        model="ollama/gemma4-26b",
        api_base="http://localhost:11434",
        api_key=None,
        extra_headers=None,
    )

    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_fake_acompletion):
        await client.chat([Message(role="user", content=".")])

    assert "api_key" not in captured
    assert "extra_headers" not in captured
    assert captured["api_base"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_thinking_fallback_fires_on_empty_content() -> None:
    """Gemma4 thinking-mode case: content="" but reasoning_content has the
    answer wrapped in a ```json block. Legacy OllamaClient extracted; new
    LiteLLMClient must replicate when thinking_fallback=True."""
    reasoning = (
        "I need to figure this out.\n"
        "```json\n"
        '{"answer": "extracted"}\n'
        "```\n"
    )

    async def _fake_acompletion(**kwargs):
        return _fake_response(content="", reasoning=reasoning)

    client = LiteLLMClient(model="ollama/gemma4-26b", thinking_fallback=True)
    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_fake_acompletion):
        resp = await client.chat([Message(role="user", content=".")])

    assert resp.content == '{"answer": "extracted"}'


@pytest.mark.asyncio
async def test_thinking_fallback_skipped_when_disabled() -> None:
    """Without thinking_fallback=True (e.g. OpenAI/Kimi), empty content
    stays empty rather than spelunking reasoning_content."""

    async def _fake_acompletion(**kwargs):
        return _fake_response(content="", reasoning="should be ignored")

    client = LiteLLMClient(model="openai/gpt-4o", api_key="sk-fake", thinking_fallback=False)
    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_fake_acompletion):
        resp = await client.chat([Message(role="user", content=".")])

    assert resp.content == ""


@pytest.mark.asyncio
async def test_is_available_returns_false_on_network_error() -> None:
    """is_available() must catch any exception and return False — never
    propagate a ConnectionError to the caller (which would crash a startup
    health-check)."""

    async def _explode(**kwargs):
        raise ConnectionError("upstream down")

    client = LiteLLMClient(model="ollama/gemma4-26b", api_base="http://localhost:11434")
    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_explode):
        assert await client.is_available() is False


@pytest.mark.asyncio
async def test_is_available_returns_true_on_success() -> None:
    """The probe completion succeeded (any 2xx) → True."""

    async def _ok(**kwargs):
        return _fake_response(content="ok")

    client = LiteLLMClient(model="ollama/gemma4-26b", api_base="http://localhost:11434")
    with patch("alpha_agent.llm.litellm_client.litellm.acompletion", new=_ok):
        assert await client.is_available() is True
