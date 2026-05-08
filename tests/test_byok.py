"""Tests for the BYOK (Bring Your Own Key) FastAPI dependency.

Locks the per-request resolution semantics so future refactors can't
silently re-introduce the operator-pays-for-everyone bug.

Resolution order under test:
  1. BYOK headers present → per-request LiteLLMClient
  2. No headers, REQUIRE_BYOK=false, platform LLM exists → platform fallback
  3. No headers, REQUIRE_BYOK=true → 401
  4. No headers, no platform LLM → 401
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from alpha_agent.api.byok import _build_byok_client, get_llm_client
from alpha_agent.llm.litellm_client import LiteLLMClient


# ── Direct provider construction (no FastAPI machinery) ──


def test_build_kimi_client_uses_legacy_path_for_ua_gate() -> None:
    """Kimi For Coding gates access via User-Agent. LiteLLM's anthropic
    provider drops `extra_headers["User-Agent"]` (its underlying SDK
    sets its own UA), so we route Kimi through the legacy hand-rolled
    KimiClient, which sets the UA at the httpx layer where it actually
    reaches the server.

    Regression guard: this test exists because we tried LiteLLM-with-
    extra_headers first, it shipped, and Kimi started 502'ing with
    "currently only available for Coding Agents" — see commit history."""
    from alpha_agent.llm._legacy.kimi import KimiClient

    c = _build_byok_client(
        provider="kimi",
        api_key="sk-test-fake",
        api_base=None,
        model=None,
    )
    # MUST be the legacy KimiClient, NOT a LiteLLMClient.
    assert isinstance(c, KimiClient)
    # Verify the constructor wired through the user's key + the right
    # default endpoint.
    assert c._model == "kimi-for-coding"
    # The legacy client builds an httpx.AsyncClient internally with the
    # UA + anthropic-version headers baked in; that's the whole reason
    # we're using it. No public attribute exposes those, so we trust
    # the file-level constants of `_legacy/kimi.py`.


def test_build_openai_provider_pointed_at_kimi_url_routes_to_legacy() -> None:
    """Users frequently pick "OpenAI" provider as a generic OpenAI-compat
    shim and supply Kimi's URL via the Base URL override. We must detect
    the Kimi endpoint by URL (not just provider name) and route through
    the legacy KimiClient so the UA gate is satisfied. Without this, the
    user's reasonable config silently breaks with "Coding Agents only"."""
    from alpha_agent.llm._legacy.kimi import KimiClient

    c = _build_byok_client(
        provider="openai",
        api_key="sk-test-fake",
        api_base="https://api.kimi.com/coding/v1",
        model="kimi-for-coding",
    )
    assert isinstance(c, KimiClient), (
        f"openai+kimi.com URL must route to legacy KimiClient, got {type(c).__name__}"
    )


def test_build_openai_client_no_extra_headers() -> None:
    c = _build_byok_client(
        provider="openai",
        api_key="sk-fake",
        api_base=None,
        model=None,
    )
    assert c._model == "openai/gpt-4o"
    assert c._extra_headers is None


def test_build_ollama_client_enables_thinking_fallback() -> None:
    c = _build_byok_client(
        provider="ollama",
        api_key="ignored-by-ollama",
        api_base="http://example.com:11434",
        model=None,
    )
    assert c._model == "ollama/gemma4:26b"
    assert c._api_base == "http://example.com:11434"
    assert c._thinking_fallback is True


def test_build_unknown_provider_raises_400() -> None:
    with pytest.raises(HTTPException) as ei:
        _build_byok_client(
            provider="bogus_provider",
            api_key="sk-fake",
            api_base=None,
            model=None,
        )
    assert ei.value.status_code == 400
    assert "bogus_provider" in str(ei.value.detail)


def test_user_overrides_take_precedence_over_defaults() -> None:
    c = _build_byok_client(
        provider="openai",
        api_key="sk-fake",
        api_base="https://my-proxy.example.com/v1",
        model="gpt-4o-mini",
    )
    assert c._api_base == "https://my-proxy.example.com/v1"
    assert c._model == "openai/gpt-4o-mini"


# ── FastAPI dependency resolution ──


def _make_request(platform_llm) -> MagicMock:
    """Minimal Request mock — only `app.state.llm` is read by the dep."""
    req = MagicMock()
    req.app.state.llm = platform_llm
    return req


def test_dep_returns_byok_client_when_api_key_header_present(monkeypatch) -> None:
    """When X-LLM-API-Key arrives, build a per-request client regardless of
    platform fallback availability."""
    monkeypatch.delenv("ALPHACORE_REQUIRE_BYOK", raising=False)
    fake_platform = MagicMock(name="platform_llm")
    req = _make_request(fake_platform)

    out = get_llm_client(
        request=req,
        x_llm_provider="openai",
        x_llm_api_key="sk-user-key",
        x_llm_base_url=None,
        x_llm_model=None,
    )
    # Per-request LiteLLMClient, NOT the platform fallback object.
    assert isinstance(out, LiteLLMClient)
    assert out is not fake_platform
    # Verify the user's key landed in the constructed client (kept private,
    # but accessed via the same attribute the production code reads).
    assert out._api_key == "sk-user-key"


def test_dep_falls_back_to_platform_when_no_byok_headers_and_not_required(
    monkeypatch,
) -> None:
    """Local dev convenience — admin's .env-configured platform LLM still
    works when ALPHACORE_REQUIRE_BYOK is unset."""
    monkeypatch.delenv("ALPHACORE_REQUIRE_BYOK", raising=False)
    fake_platform = MagicMock(name="platform_llm")
    req = _make_request(fake_platform)

    out = get_llm_client(
        request=req,
        x_llm_provider=None,
        x_llm_api_key=None,
        x_llm_base_url=None,
        x_llm_model=None,
    )
    assert out is fake_platform


def test_dep_rejects_when_no_byok_headers_and_require_byok_true(monkeypatch) -> None:
    """Public deploys set ALPHACORE_REQUIRE_BYOK=true → platform fallback
    is disabled even when a platform LLM is configured."""
    monkeypatch.setenv("ALPHACORE_REQUIRE_BYOK", "true")
    fake_platform = MagicMock(name="platform_llm")
    req = _make_request(fake_platform)

    with pytest.raises(HTTPException) as ei:
        get_llm_client(
            request=req,
            x_llm_provider=None,
            x_llm_api_key=None,
            x_llm_base_url=None,
            x_llm_model=None,
        )
    assert ei.value.status_code == 401
    assert "byok_required" in str(ei.value.detail)


def test_dep_rejects_when_no_byok_headers_and_no_platform_llm(monkeypatch) -> None:
    """The pure BYOK deploy: no platform LLM at all + no caller headers
    → 401, no surprise 500 from None.chat()."""
    monkeypatch.delenv("ALPHACORE_REQUIRE_BYOK", raising=False)
    req = _make_request(None)

    with pytest.raises(HTTPException) as ei:
        get_llm_client(
            request=req,
            x_llm_provider=None,
            x_llm_api_key=None,
            x_llm_base_url=None,
            x_llm_model=None,
        )
    assert ei.value.status_code == 401
    assert ei.value.detail["error"] == "byok_required"
    assert "X-LLM-API-Key" in str(ei.value.detail)
