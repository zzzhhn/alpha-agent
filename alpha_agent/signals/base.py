"""Shared SignalScore contract + safe_fetch wrapper.

Spec §3.1: every signal module exports a `fetch_signal(ticker, as_of)`
that returns SignalScore. safe_fetch is the ONLY place we catch external
errors; it does NOT catch generic Exception (CLAUDE.md silent-except rule).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, TypedDict

import httpx

logger = logging.getLogger(__name__)


class SignalScore(TypedDict):
    ticker: str
    z: float                 # clipped to [-3, 3]
    raw: Any                 # original value(s) for transparency
    confidence: float        # [0, 1]; 0 = signal unavailable
    as_of: datetime
    source: str              # 'yfinance' / 'edgar' / 'fred' / 'agent-reach'
    error: str | None        # populated only on graceful failure


# These are the ONLY exceptions safe_fetch catches.
# Programming bugs (TypeError, AttributeError, ZeroDivisionError, etc.)
# propagate so they get surfaced and fixed, not silently zeroed.
_EXTERNAL_ERRORS = (
    ConnectionError, TimeoutError,
    httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError,
    KeyError, ValueError, IndexError,
)


def safe_fetch(
    fn: Callable[[str, datetime], SignalScore],
    ticker: str,
    as_of: datetime,
    *,
    source: str,
) -> SignalScore:
    try:
        return fn(ticker, as_of)
    except _EXTERNAL_ERRORS as e:
        logger.warning("signal fetch failed: %s/%s: %s", source, ticker, e)
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.0,
            as_of=as_of, source=source,
            error=f"{type(e).__name__}: {str(e)[:120]}",
        )
