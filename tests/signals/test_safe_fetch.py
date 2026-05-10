from datetime import datetime, UTC

import httpx
import pytest

from alpha_agent.signals.base import SignalScore, safe_fetch


def _ok_fetch(ticker, as_of):
    return SignalScore(
        ticker=ticker, z=1.5, raw=42.0, confidence=0.9,
        as_of=as_of, source="test", error=None,
    )


def _conn_fetch(ticker, as_of):
    raise httpx.ConnectError("network down")


def _parse_fetch(ticker, as_of):
    return {"foo": 1}["bar"]  # KeyError


def _fatal_fetch(ticker, as_of):
    raise RuntimeError("programmer bug — must propagate")


def test_happy_path_passes_through():
    out = safe_fetch(_ok_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 1.5
    assert out["confidence"] == 0.9
    assert out["error"] is None


def test_connection_error_returns_zero_confidence():
    out = safe_fetch(_conn_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None and "ConnectError" in out["error"]


def test_parse_error_returns_zero_confidence():
    out = safe_fetch(_parse_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 0.0
    assert out["error"] is not None and "KeyError" in out["error"]


def test_fatal_error_propagates():
    """Programming bugs must NOT be silently absorbed (CLAUDE.md silent except rule)."""
    with pytest.raises(RuntimeError):
        safe_fetch(_fatal_fetch, "AAPL", datetime.now(UTC), source="test")
