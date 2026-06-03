"""Shared SSE serialization helper for streaming endpoints.

Extracted so the brief / persona / news-enrich streaming routes all emit
byte-identical `data:` frames and never drift apart. The format matches
what `frontend/src/lib/api/streamBrief.ts` (and its siblings) parse:
one newline-delimited JSON object per SSE event, terminated by a blank
line.
"""
from __future__ import annotations

import json

# Streaming responses must never be buffered by an intermediate proxy
# (nginx) or cached by the edge, or the client paints nothing until the
# whole stream finishes. Mirror the headers brief.py uses.
SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
}


def sse_format(event: dict) -> bytes:
    """Serialize one event as a single SSE `data:` line.

    Keep newline-delimited JSON inside the data field so the client parses
    deterministically.
    """
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")
