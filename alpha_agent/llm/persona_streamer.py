"""Token-streaming generator for the persona-commentary endpoint.

Mirrors `brief_streamer.stream_brief`, but the persona output is a single
block of prose (no [SUMMARY]/[BULL]/[BEAR] sections), so events are simply
`{type: "explanation", delta}` terminated by `{type: "done"}`.

Architecture (matches the Rich Brief streamer):
1. A per-request client is built via the shared `_build_byok_client`
   router so Kimi correctly bypasses LiteLLM.
2. `client.stream_chat(...)` yields raw text chunks as the LLM generates
   them; the route SSE-wraps each chunk into an `explanation` event so the
   panel paints tokens live.
3. B3 per-user cache: on a hit the cached text is replayed as one
   `explanation` delta + `done` (sub-100ms, no LLM round-trip), preserving
   the existing per-(user, ticker, persona, language, as_of) cache so a
   re-click within 24h is instant.

Key handling: api_key is request-only — passed straight into the
per-request client, never stored, logged, or echoed into error payloads.
"""
from __future__ import annotations

from typing import AsyncIterator

from alpha_agent.api.byok import _build_byok_client
from alpha_agent.llm.base import Message


async def stream_persona(
    *,
    provider: str,
    api_key: str,
    system_prompt: str,
    user_payload: str,
    model: str | None = None,
    base_url: str | None = None,
    pool=None,
    user_id: int | None = None,
    cache_key_str: str | None = None,
) -> AsyncIterator[dict]:
    """Async generator yielding {type: "explanation", delta} dicts,
    terminated by {type: "done", cache}.

    Builds a per-request LLM client via the shared `_build_byok_client`
    router, runs one streaming `stream_chat()` call, and emits the result
    as `explanation` deltas.

    Caching is opt-in: when pool/user_id/cache_key_str are all present the
    response is served from / written to the B3 per-user llm_cache, exactly
    matching the non-streaming persona route's cache slot. When any is
    absent the streamer behaves as a plain pass-through.

    Raises:
        Upstream client errors propagate to the caller, which wraps them
        into a sanitized SSE error event.
    """
    cache_enabled = (
        pool is not None and user_id is not None and cache_key_str is not None
    )
    if cache_enabled:
        from alpha_agent.llm.cache import cached_response

        cached_text = await cached_response(pool, user_id, cache_key_str)
        if cached_text is not None:
            # Hit: emit the cached text as a single delta then done. Same
            # downstream event shape as a fresh stream, sub-100ms latency.
            if cached_text:
                yield {"type": "explanation", "delta": cached_text}
            yield {"type": "done", "cache": "hit"}
            return

    client = _build_byok_client(
        provider=provider,
        api_key=api_key,
        api_base=base_url,
        model=model,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_payload),
    ]
    accumulated = ""
    try:
        async for chunk in client.stream_chat(
            messages, temperature=0.3, max_tokens=300,
        ):
            if not chunk:
                continue
            accumulated += chunk
            yield {"type": "explanation", "delta": chunk}
        # Only persist after a successful stream — partial / aborted
        # responses must not pollute the cache.
        if cache_enabled and accumulated.strip():
            from alpha_agent.llm.cache import CACHE_TTL_DEFAULT, store_response

            await store_response(
                pool, user_id, cache_key_str,
                model or provider, accumulated.strip(),
                ttl=CACHE_TTL_DEFAULT,
            )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()
    yield {"type": "done", "cache": "miss"}
