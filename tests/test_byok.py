"""Tests for the BYOK (Bring Your Own Key) FastAPI dependency.

Locks the per-request resolution semantics so future refactors can't
silently re-introduce the operator-pays-for-everyone bug.

Phase 4 server-side model (M5 E3b):
  - get_llm_client is now an async FastAPI dependency gated by require_user.
  - It reads user_byok from Postgres, decrypts with BYOK_MASTER_KEY, and
    calls _build_byok_client.
  - The old X-LLM-* header path and platform-fallback path are gone.

_build_byok_client provider-construction tests are unchanged.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from alpha_agent.api.byok import _build_byok_client
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


# ── FastAPI dependency resolution (Phase 4 server-side BYOK) ──
# The old X-LLM-* header path is gone. get_llm_client is now an async
# dependency that reads user_byok from Postgres, decrypts with BYOK_MASTER_KEY,
# and calls _build_byok_client. The tests below cover the key behaviors via
# a full-stack TestClient fixture, matching test_alpha_translate_auth.py.
#
# Note: test_alpha_translate_auth.py is the canonical integration-level test
# for the dependency resolution contract. These unit-style tests below add
# coverage for the decrypt path and missing-master-key edge case.

import base64
import time

import pytest as _pytest
from fastapi.testclient import TestClient as _TC
from jose import jwt as _jwt
from unittest.mock import AsyncMock as _AsyncMock, MagicMock as _MagicMock

_DEP_SECRET = "test-dep-secret-9876543210abcdef"
_DEP_MASTER = base64.b64encode(b"fedcba9876543210fedcba9876543210").decode()


def _dep_auth(sub="99"):
    now = int(time.time())
    tok = _jwt.encode(
        {"sub": sub, "iat": now, "exp": now + 3600},
        _DEP_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


@_pytest.fixture
def dep_client(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _DEP_SECRET)
    monkeypatch.setenv("BYOK_MASTER_KEY", _DEP_MASTER)
    from api.index import app
    return _TC(app, raise_server_exceptions=False)


def test_dep_builds_client_from_decrypted_byok(dep_client, monkeypatch) -> None:
    """get_llm_client decrypts the stored row and passes plaintext to _build_byok_client.

    Regression guard: the M5 E3b migration. Mirrors test_alpha_translate_auth.py
    but at the _build_byok_client level to confirm the LiteLLMClient gets the
    correct key and api_base.
    """
    from alpha_agent.auth.crypto_box import encrypt

    ciphertext, nonce = encrypt("sk-dep-test-key", _DEP_MASTER.encode())
    byok_row = {
        "provider": "openai",
        "ciphertext": ciphertext,
        "nonce": nonce,
        "model": "gpt-4o",
        "base_url": None,
    }
    pool = _MagicMock()
    pool.fetchrow = _AsyncMock(return_value=byok_row)
    monkeypatch.setattr(
        "alpha_agent.api.byok.get_db_pool",
        _AsyncMock(return_value=pool),
    )

    captured = {}

    def fake_build(provider, api_key, api_base, model):
        captured["api_key"] = api_key
        captured["provider"] = provider
        raise HTTPException(status_code=503, detail="sentinel")

    monkeypatch.setattr("alpha_agent.api.byok._build_byok_client", fake_build)

    # Use the translate endpoint as a probe - any LLM-burning route works.
    r = dep_client.post(
        "/api/v1/alpha/translate",
        headers=_dep_auth(),
        json={"text": "test hypothesis", "universe": "SP500"},
    )
    assert captured.get("api_key") == "sk-dep-test-key", (
        f"Plaintext key not passed to _build_byok_client; got {captured.get('api_key')!r}"
    )
    assert captured.get("provider") == "openai"
    assert r.status_code == 503


def test_dep_400_when_no_byok_row(dep_client, monkeypatch) -> None:
    """No user_byok row -> 400 mentioning /settings."""
    pool = _MagicMock()
    pool.fetchrow = _AsyncMock(return_value=None)
    monkeypatch.setattr(
        "alpha_agent.api.byok.get_db_pool",
        _AsyncMock(return_value=pool),
    )
    r = dep_client.post(
        "/api/v1/alpha/translate",
        headers=_dep_auth(),
        json={"text": "test", "universe": "SP500"},
    )
    assert r.status_code == 400
    assert "settings" in r.json()["detail"].lower()


def test_dep_500_when_master_key_missing(monkeypatch) -> None:
    """If BYOK_MASTER_KEY is not set, the dependency returns 500."""
    monkeypatch.setenv("NEXTAUTH_SECRET", _DEP_SECRET)
    monkeypatch.delenv("BYOK_MASTER_KEY", raising=False)
    from api.index import app
    client = _TC(app, raise_server_exceptions=False)

    from alpha_agent.auth.crypto_box import encrypt
    # Dummy encrypt under a throwaway key just to produce a row shape.
    _throwaway = base64.b64encode(b"x" * 32).decode()
    ciphertext, nonce = encrypt("sk-x", _throwaway.encode())
    byok_row = {
        "provider": "openai",
        "ciphertext": ciphertext,
        "nonce": nonce,
        "model": None,
        "base_url": None,
    }
    pool = _MagicMock()
    pool.fetchrow = _AsyncMock(return_value=byok_row)
    monkeypatch.setattr(
        "alpha_agent.api.byok.get_db_pool",
        _AsyncMock(return_value=pool),
    )
    r = client.post(
        "/api/v1/alpha/translate",
        headers=_dep_auth(),
        json={"text": "test", "universe": "SP500"},
    )
    assert r.status_code == 500
    assert "BYOK_MASTER_KEY" in r.json()["detail"]
