"""Live-endpoint smoke for the A1 LiteLLMClient refactor.

Dispatches a single 1-token completion against whichever provider is
configured in the environment, prints structured PASS/FAIL with
diagnostics. Run before deploying any LiteLLM-related change so we
catch provider-side regressions (model rename, header change, etc.)
without finding out via a 503 in production.

Usage:
    # Use whatever LLM_PROVIDER is set in .env
    python3 scripts/smoke_litellm_live.py

    # Force one provider explicitly
    LLM_PROVIDER=kimi KIMI_API_KEY=sk-... python3 scripts/smoke_litellm_live.py

    # Validate the legacy fallback path still works
    LLM_USE_LEGACY=1 python3 scripts/smoke_litellm_live.py

Exits 0 on success, 1 on any failure. Suitable as a deploy gate.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env if dotenv is available; fall back to relying on shell env.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from alpha_agent.config import Settings
from alpha_agent.llm.base import Message
from alpha_agent.llm.factory import create_llm_client


async def main() -> int:
    settings = Settings()
    provider = settings.llm_provider
    using_legacy = os.environ.get("LLM_USE_LEGACY") == "1"
    print(f"=== LiteLLM live smoke ===")
    print(f"  provider:   {provider}")
    print(f"  legacy:     {using_legacy}")

    try:
        client = create_llm_client(settings)
    except ValueError as exc:
        print(f"FAIL: factory rejected config: {exc}", file=sys.stderr)
        return 1

    print(f"  client:     {type(client).__name__}")
    if hasattr(client, "_model"):
        print(f"  model:      {client._model}")
    if hasattr(client, "_api_base"):
        print(f"  api_base:   {client._api_base}")

    print()
    print("[1/2] is_available probe...")
    try:
        ok = await client.is_available()
    except Exception as exc:
        print(f"FAIL: is_available raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if not ok:
        print(
            f"FAIL: is_available returned False — check provider creds / "
            f"tunnel / model name. See logs above for the underlying error.",
            file=sys.stderr,
        )
        return 1
    print("  → PASS")

    print()
    print("[2/2] chat round-trip (1-message, 32-token cap)...")
    try:
        resp = await client.chat(
            messages=[
                Message(role="user", content="Reply with one short word: 'pong'."),
            ],
            temperature=0.0,
            max_tokens=32,
        )
    except Exception as exc:
        print(f"FAIL: chat raised {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not resp.content.strip():
        print(
            f"FAIL: chat returned empty content. "
            f"prompt_tokens={resp.prompt_tokens} completion_tokens={resp.completion_tokens}",
            file=sys.stderr,
        )
        return 1

    print(f"  → PASS")
    print(f"     content:           {resp.content[:80]!r}")
    print(f"     model echoed:      {resp.model}")
    print(f"     prompt_tokens:     {resp.prompt_tokens}")
    print(f"     completion_tokens: {resp.completion_tokens}")

    print()
    print("=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
