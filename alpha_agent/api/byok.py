"""BYOK (Bring Your Own Key) FastAPI dependency.

Phase 4 server-side model: every authenticated route that calls an LLM uses
`get_llm_client` as a FastAPI dependency. The dependency resolves the
calling user's stored BYOK row from `user_byok`, decrypts the API key
server-side with BYOK_MASTER_KEY, and constructs a per-request LLMClient.

No LLM key ever leaves the server. The decrypted plaintext is only passed
to `_build_byok_client` and immediately discarded after the client object
is built - it is never logged, cached, or echoed in responses.

Failure modes:
  - No session -> 401 (from require_user dependency)
  - No user_byok row -> 400 with a /settings redirect hint
  - BYOK_MASTER_KEY missing -> 500
  - Ciphertext tampered / wrong key -> 400

_build_byok_client and the provider constants are unchanged from M4.
"""
from __future__ import annotations

import logging
import os

from fastapi import Depends, HTTPException

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.crypto_box import CryptoError, decrypt
from alpha_agent.auth.dependencies import require_user
from alpha_agent.llm.base import LLMClient
from alpha_agent.llm.litellm_client import LiteLLMClient

logger = logging.getLogger(__name__)


_KIMI_USER_AGENT = "claude-cli/1.0.0 (external, cli)"
_KIMI_ANTHROPIC_VERSION = "2023-06-01"

# Default api_base / model per provider when the BYOK headers omit them.
# These mirror the Settings model defaults in `alpha_agent/config.py` so the
# same provider strings produce identical clients regardless of source.
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "model_prefix": "openai",
    },
    "kimi": {
        "api_base": "https://api.kimi.com/coding/v1",
        "model": "kimi-for-coding",
        "model_prefix": "anthropic",  # Kimi For Coding uses Anthropic-compat
    },
    "ollama": {
        "api_base": "http://localhost:11434",
        "model": "gemma4:26b",
        "model_prefix": "ollama",
    },
    "anthropic": {
        "api_base": "https://api.anthropic.com",
        "model": "claude-sonnet-4-5",
        "model_prefix": "anthropic",
    },
}

_VALID_PROVIDERS = frozenset(_PROVIDER_DEFAULTS.keys())


def _build_byok_client(
    provider: str,
    api_key: str,
    api_base: str | None,
    model: str | None,
) -> LLMClient:
    """Construct a per-request LLM client from raw header values.

    Most providers route through LiteLLMClient. Kimi For Coding is a
    deliberate exception: its `/messages` endpoint gates access by
    User-Agent (only allow-listed coding agents like Claude Code / Kimi
    CLI / Roo Code can talk to it). LiteLLM's anthropic provider sets
    its own UA on the underlying SDK and silently drops `extra_headers`
    for that field, so the legacy hand-rolled `KimiClient` (which sets
    the UA at the httpx layer) is the only path that actually works.

    This is the same code path as `LLM_USE_LEGACY=1` for that provider,
    just made per-provider instead of global.
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(
            400,
            f"Unsupported X-LLM-Provider {provider!r}. "
            f"Valid: {sorted(_VALID_PROVIDERS)}",
        )

    defaults = _PROVIDER_DEFAULTS[provider]
    resolved_base = api_base or defaults["api_base"]
    resolved_model = model or defaults["model"]

    # Kimi For Coding — bypass LiteLLM. See docstring above.
    # Detection by URL (not just provider name) because users frequently
    # use the "OpenAI" provider as a generic OpenAI-compat shim with a
    # custom Base URL pointing at any compatible upstream — Kimi's
    # /coding/v1 is the most common case and would otherwise hit LiteLLM's
    # openai provider, lose the UA, and fail Kimi's coding-agent gate.
    is_kimi_endpoint = (
        provider == "kimi"
        or "kimi.com" in resolved_base.lower()
    )
    if is_kimi_endpoint:
        from alpha_agent.llm._legacy.kimi import KimiClient
        return KimiClient(
            api_key=api_key,
            base_url=resolved_base,
            model=resolved_model,
        )

    # All other providers go through LiteLLM.
    full_model = f"{defaults['model_prefix']}/{resolved_model}"
    thinking_fallback = provider == "ollama"
    return LiteLLMClient(
        model=full_model,
        api_key=api_key,
        api_base=resolved_base,
        thinking_fallback=thinking_fallback,
    )


async def get_llm_client(
    user_id: int = Depends(require_user),
) -> LLMClient:
    """FastAPI dependency. Returns a per-request LLM client for the authenticated user.

    Reads the user's encrypted BYOK row from user_byok, decrypts it with
    BYOK_MASTER_KEY, and builds an LLMClient. Raises 400 if no key is stored,
    500 if BYOK_MASTER_KEY is missing, 400 if decryption fails. Auth is
    enforced by require_user (401 on missing/invalid token).

    Use as `llm: LLMClient = Depends(get_llm_client)` in any route that calls llm.chat().
    """
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT provider, ciphertext, nonce, base_url, model "
        "FROM user_byok WHERE user_id = $1 LIMIT 1",
        user_id,
    )
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="No BYOK key set; visit /settings to add one",
        )

    master = os.environ.get("BYOK_MASTER_KEY")
    if not master:
        raise HTTPException(status_code=500, detail="BYOK_MASTER_KEY not configured")

    try:
        plaintext_key = decrypt(row["ciphertext"], row["nonce"], master.encode("utf-8"))
    except CryptoError:
        raise HTTPException(
            status_code=400,
            detail="Stored key cannot be decrypted. Please re-save it in /settings.",
        )

    return _build_byok_client(
        provider=row["provider"],
        api_key=plaintext_key,
        api_base=row["base_url"],
        model=row["model"],
    )
