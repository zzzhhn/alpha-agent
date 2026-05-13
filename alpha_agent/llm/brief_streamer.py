"""LiteLLM-backed streaming generator for the Rich brief endpoint.

Wraps the existing `litellm.acompletion(stream=True, ...)` interface so the
FastAPI route can `async for` over normalized `{type, delta}` events without
caring which provider (OpenAI / Anthropic / Kimi / Ollama) the user picked.

Key handling: api_key is a request-only parameter. We pass it directly to
LiteLLM and never store, never log, never include in error payloads. The
exception path returns the type name + a sanitized message (no key prefix).
"""
from __future__ import annotations

from typing import AsyncIterator, Literal

import litellm

Provider = Literal["openai", "anthropic", "kimi", "ollama"]

_DEFAULT_MODEL: dict[Provider, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "kimi": "openai/kimi-for-coding",
    "ollama": "ollama/llama3.1",
}
_DEFAULT_BASE: dict[Provider, str | None] = {
    "openai": None,
    "anthropic": None,
    "kimi": "https://api.kimi.com/coding/v1",
    "ollama": "http://localhost:11434",
}

SYSTEM_PROMPT = """You are a sober equity research analyst writing a brief for a retail trader.

You will receive a JSON blob containing the latest signal breakdown for ONE ticker. Your job is to produce three sections in this exact order:

1. **SUMMARY** - one paragraph (3-5 sentences) stating the current rating, the strongest 1-2 drivers, the strongest 1-2 drags, and what specifically the trader should watch next.
2. **BULL** - 3 to 5 bullet points making the case to buy. Each bullet must cite a concrete number from the breakdown (e.g. "P/E trailing 28.5", "news sentiment +0.5 from 2 headlines", "earnings beat 12.0%").
3. **BEAR** - 3 to 5 bullet points making the case to avoid or short, with the same citation discipline.

Strict rules:
- If a field is null or missing in the breakdown, do NOT fabricate it. Say "data thin" or omit the bullet.
- Do NOT recommend specific trades, position sizes, or stops. Stick to thesis quality.
- Do NOT include any prefatory or closing commentary outside the three sections.
- Format each section header as `[SUMMARY]`, `[BULL]`, `[BEAR]` on its own line so the client can split sections deterministically."""


def _build_user_prompt(ticker: str, rating: str, composite: float, breakdown: list[dict]) -> str:
    import json
    return (
        f"Ticker: {ticker}\n"
        f"Rating: {rating}\n"
        f"Composite score: {composite:+.2f}\n\n"
        f"Signal breakdown (JSON):\n{json.dumps(breakdown, default=str, indent=2)}"
    )


async def stream_brief(
    *,
    provider: Provider,
    api_key: str,
    ticker: str,
    rating: str,
    composite: float,
    breakdown: list[dict],
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncIterator[dict]:
    """Async generator yielding {type, delta} dicts.

    Yields sections tagged by header markers in the LLM output: the streamer
    tracks the current section as the LLM emits `[SUMMARY]` / `[BULL]` /
    `[BEAR]` tokens. Final yield is `{type: "done"}`.

    Raises:
        RuntimeError on upstream failure (caller wraps into SSE error event).
    """
    chosen_model = model or _DEFAULT_MODEL[provider]
    chosen_base = base_url or _DEFAULT_BASE[provider]

    kwargs = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": _build_user_prompt(ticker, rating, composite, breakdown)},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
        "stream": True,
        "api_key": api_key,
    }
    if chosen_base:
        kwargs["api_base"] = chosen_base

    current = "summary"  # default until first header marker
    buffer = ""

    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        try:
            tok = chunk.choices[0].delta.content
        except (AttributeError, IndexError, TypeError):
            tok = None
        if not tok:
            continue
        buffer += tok
        # Header markers split sections. We only flush after a complete
        # marker so streaming doesn't render the marker itself.
        for marker, section in (
            ("[SUMMARY]", "summary"),
            ("[BULL]", "bull"),
            ("[BEAR]", "bear"),
        ):
            if marker in buffer:
                # Anything before the marker belongs to the prior section
                pre, _, rest = buffer.partition(marker)
                if pre:
                    yield {"type": current, "delta": pre}
                current = section
                buffer = rest
        # Drain buffer in small chunks so the client renders smoothly.
        if len(buffer) > 12:
            yield {"type": current, "delta": buffer}
            buffer = ""
    if buffer:
        yield {"type": current, "delta": buffer}
    yield {"type": "done"}
