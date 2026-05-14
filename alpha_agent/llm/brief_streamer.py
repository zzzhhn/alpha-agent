"""Section-emitting generator for the Rich brief endpoint.

This used to call `litellm.acompletion(stream=True, ...)` directly, which
reimplemented provider routing and silently missed the Kimi-For-Coding
User-Agent gate (Kimi allow-lists coding-agent UAs; LiteLLM's own UA gets
rejected with a 400). The fix: reuse `_build_byok_client` - the single
provider router that `get_llm_client` also uses - so Kimi goes through the
hand-rolled `KimiClient` (correct UA, Anthropic-compat `/messages`) exactly
like every other authenticated LLM route.

Trade-off: the legacy `KimiClient` exposes only a one-shot `chat()`, no
streaming. So the brief is fetched in one call, then split into
`[SUMMARY]`/`[BULL]`/`[BEAR]` sections and emitted as discrete SSE events.
The client UI is unchanged - it already keys off the section markers.

Key handling: api_key is request-only. It is passed straight into the
per-request client and never stored, logged, or echoed into error payloads.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

# `_build_byok_client` is the one place that knows Kimi must bypass LiteLLM.
# Importing it (rather than re-deriving provider routing here) is what keeps
# this module from drifting out of sync again.
from alpha_agent.api.byok import _build_byok_client
from alpha_agent.llm.base import Message

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

_SECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("[SUMMARY]", "summary"),
    ("[BULL]", "bull"),
    ("[BEAR]", "bear"),
)


def _build_user_prompt(ticker: str, rating: str, composite: float, breakdown: list[dict]) -> str:
    return (
        f"Ticker: {ticker}\n"
        f"Rating: {rating}\n"
        f"Composite score: {composite:+.2f}\n\n"
        f"Signal breakdown (JSON):\n{json.dumps(breakdown, default=str, indent=2)}"
    )


def _split_sections(text: str) -> list[dict]:
    """Split a full LLM response into ordered {type, delta} section events.

    Sections are delimited by the `[SUMMARY]`/`[BULL]`/`[BEAR]` header
    markers the system prompt mandates. Any text before the first marker is
    attributed to `summary` (defensive: the model occasionally adds a stray
    preface). If no markers are present at all, the whole response is
    emitted as a single `summary` event so the client still renders it.
    """
    found = sorted(
        (idx, marker, section)
        for marker, section in _SECTION_MARKERS
        if (idx := text.find(marker)) != -1
    )
    if not found:
        body = text.strip()
        return [{"type": "summary", "delta": body}] if body else []

    events: list[dict] = []
    pre = text[: found[0][0]].strip()
    if pre:
        events.append({"type": "summary", "delta": pre})
    for i, (idx, marker, section) in enumerate(found):
        start = idx + len(marker)
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        body = text[start:end].strip()
        if body:
            events.append({"type": section, "delta": body})
    return events


async def stream_brief(
    *,
    provider: str,
    api_key: str,
    ticker: str,
    rating: str,
    composite: float,
    breakdown: list[dict],
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncIterator[dict]:
    """Async generator yielding {type, delta} dicts, terminated by {type: "done"}.

    Builds a per-request LLM client via the shared `_build_byok_client`
    router (so Kimi correctly bypasses LiteLLM), runs one `chat()` call, and
    emits the result as `summary`/`bull`/`bear` section events.

    Raises:
        Upstream client errors propagate to the caller, which wraps them
        into a sanitized SSE error event.
    """
    client = _build_byok_client(
        provider=provider,
        api_key=api_key,
        api_base=base_url,
        model=model,
    )
    messages = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(
            role="user",
            content=_build_user_prompt(ticker, rating, composite, breakdown),
        ),
    ]
    try:
        response = await client.chat(messages, temperature=0.3, max_tokens=800)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()

    for event in _split_sections(response.content):
        yield event
    yield {"type": "done"}
