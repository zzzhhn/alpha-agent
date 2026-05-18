"""Section-emitting generator for the Rich brief endpoint.

Architecture (2026-05-19 true-streaming upgrade):
1. The provider client is built via `_build_byok_client` — the single
   provider router shared with `get_llm_client`. Kimi goes through the
   hand-rolled KimiClient (Anthropic-compat /messages with the UA gate
   honored); everything else routes through LiteLLMClient.
2. We call `client.stream_chat(...)` which yields raw text chunks as the
   LLM generates them. KimiClient + LiteLLMClient both have native SSE
   streaming; any future client without a streaming path inherits the
   default fallback in LLMClient.base (one yield of the full chat()
   response — preserves behaviour for non-streaming providers).
3. A `_StreamSplitter` (below) buffers the incoming text and detects
   `[SUMMARY]`/`[BULL]`/`[BEAR]` section markers on the fly, emitting
   {type, delta} events as soon as enough characters have arrived to be
   unambiguously past a marker boundary. This is what makes the UI
   actually paint tokens as the LLM emits them, rather than waiting for
   the full response and bursting all events at the end.

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


_SECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("[SUMMARY]", "summary"),
    ("[BULL]", "bull"),
    ("[BEAR]", "bear"),
)
_MAX_MARKER_LEN = max(len(m) for m, _ in _SECTION_MARKERS)


class _StreamSplitter:
    """Token-streaming marker router for Rich Brief.

    Buffers incoming chunks and emits {type, delta} events as soon as
    enough text has arrived to be unambiguously past a section boundary.
    Holds back up to `_MAX_MARKER_LEN` characters at the buffer tail so a
    marker split across two chunks (e.g. "[SUM" then "MARY]\\n") is not
    misclassified as belonging to the prior section.

    Pre-marker prose (rare: model occasionally adds a stray preface) is
    attributed to `summary`, matching the prior post-hoc splitter's
    behaviour so the client never sees a "no section yet" delta.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._current_section: str | None = None

    def feed(self, chunk: str) -> list[dict]:
        events: list[dict] = []
        self._buf += chunk
        while True:
            best_idx = -1
            best_marker_len = 0
            best_section: str | None = None
            for marker, section in _SECTION_MARKERS:
                idx = self._buf.find(marker)
                if idx != -1 and (best_idx == -1 or idx < best_idx):
                    best_idx = idx
                    best_marker_len = len(marker)
                    best_section = section
            if best_idx == -1:
                # No complete marker visible. Emit everything except the
                # last MAX_MARKER_LEN chars (which might be a partial
                # marker still arriving). On the first chunk before any
                # marker fires we attribute to summary.
                hold = _MAX_MARKER_LEN
                if len(self._buf) > hold:
                    emit = self._buf[:-hold]
                    self._buf = self._buf[-hold:]
                    target = self._current_section or "summary"
                    if emit:
                        events.append({"type": target, "delta": emit})
                return events
            prefix = self._buf[:best_idx]
            if prefix:
                target = self._current_section or "summary"
                events.append({"type": target, "delta": prefix})
            self._current_section = best_section
            tail_start = best_idx + best_marker_len
            # Trim a leading newline immediately after the marker for
            # cleaner section text; harmless if absent.
            if (
                tail_start < len(self._buf)
                and self._buf[tail_start] == "\n"
            ):
                tail_start += 1
            self._buf = self._buf[tail_start:]

    def flush(self) -> list[dict]:
        if not self._buf:
            return []
        target = self._current_section or "summary"
        out = [{"type": target, "delta": self._buf}]
        self._buf = ""
        return out

_SYSTEM_PROMPT_BASE = """You are a sober equity research analyst writing a brief for a retail trader.

You will receive a JSON blob containing the latest signal breakdown for ONE ticker. Your job is to produce three sections in this exact order:

1. **SUMMARY** - one paragraph (3-5 sentences) stating the current rating, the strongest 1-2 drivers, the strongest 1-2 drags, and what specifically the trader should watch next.
2. **BULL** - 3 to 5 bullet points making the case to buy. Each bullet must cite a concrete number from the breakdown (e.g. "P/E trailing 28.5", "news sentiment +0.5 from 2 headlines", "earnings beat 12.0%").
3. **BEAR** - 3 to 5 bullet points making the case to avoid or short, with the same citation discipline.

Strict rules:
- If a field is null or missing in the breakdown, do NOT fabricate it. Say "data thin" or omit the bullet.
- Do NOT recommend specific trades, position sizes, or stops. Stick to thesis quality.
- Do NOT include any prefatory or closing commentary outside the three sections.
- Format each section header as `[SUMMARY]`, `[BULL]`, `[BEAR]` on its own line so the client can split sections deterministically.
{language_directive}"""


def _build_system_prompt(language: str) -> str:
    """Inject a language directive at the bottom of the base prompt.

    language="zh" → entire output in 简体中文 (section markers stay ASCII
    so the client-side splitter remains deterministic). Anything else
    defaults to English. Phase 312 (2026-05-19) bilingual feature; prior
    SYSTEM_PROMPT constant remains exposed as the English default for any
    external import.
    """
    if language == "zh":
        directive = (
            "- Write the SUMMARY, BULL, and BEAR section bodies in 简体中文. "
            "Keep the `[SUMMARY]` / `[BULL]` / `[BEAR]` markers themselves "
            "in ASCII so the client-side splitter still works. Numbers, "
            "tickers, and field names stay in English."
        )
    else:
        directive = "- Write everything in clear, professional English."
    return _SYSTEM_PROMPT_BASE.format(language_directive=directive)


# Back-compat: callers that imported the bare constant still get the English
# prompt. The streamer below now resolves per-request via _build_system_prompt.
SYSTEM_PROMPT = _build_system_prompt("en")

def _build_user_prompt(ticker: str, rating: str, composite: float, breakdown: list[dict]) -> str:
    return (
        f"Ticker: {ticker}\n"
        f"Rating: {rating}\n"
        f"Composite score: {composite:+.2f}\n\n"
        f"Signal breakdown (JSON):\n{json.dumps(breakdown, default=str, indent=2)}"
    )




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
    language: str = "en",
) -> AsyncIterator[dict]:
    """Async generator yielding {type, delta} dicts, terminated by {type: "done"}.

    Builds a per-request LLM client via the shared `_build_byok_client`
    router (so Kimi correctly bypasses LiteLLM), runs one `chat()` call, and
    emits the result as `summary`/`bull`/`bear` section events.

    `language` ("zh" | "en") controls the language of the section bodies;
    the [SUMMARY]/[BULL]/[BEAR] markers themselves stay ASCII so the
    client-side splitter still works regardless of language.

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
        Message(role="system", content=_build_system_prompt(language)),
        Message(
            role="user",
            content=_build_user_prompt(ticker, rating, composite, breakdown),
        ),
    ]
    splitter = _StreamSplitter()
    try:
        async for chunk in client.stream_chat(
            messages, temperature=0.3, max_tokens=800,
        ):
            for ev in splitter.feed(chunk):
                yield ev
        for ev in splitter.flush():
            yield ev
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            await close()
    yield {"type": "done"}
