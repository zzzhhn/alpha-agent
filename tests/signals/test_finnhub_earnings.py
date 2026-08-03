"""Finnhub earnings parsing (no network, fake client)."""
from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from alpha_agent.signals import finnhub_earnings as fe


class _Resp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    def json(self):
        return self._p


class _Client:
    """Routes a request to a canned payload by URL substring."""
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, params=None, timeout=None):
        for key, payload in self.routes.items():
            if key in url:
                return _Resp(payload)
        raise AssertionError(f"no route for {url}")


class _SequenceClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(fe.time, "sleep", lambda *_: None)


def test_fetch_surprise_relative_and_report_date():
    rows = [
        {"actual": 1.20, "estimate": 1.00, "period": "2026-03-31"},
        {"actual": 1.02, "estimate": 1.00, "period": "2025-12-31"},
        {"actual": 0.98, "estimate": 1.00, "period": "2025-09-30"},
        {"actual": 1.01, "estimate": 1.00, "period": "2025-06-30"},
    ]
    out = fe.fetch_surprise(_Client({"stock/earnings": rows}), "k", "AAPL")
    assert out["recent_surprise"] == pytest.approx(0.20)  # (1.2-1.0)/1.0
    assert out["report_date"] == date(2026, 3, 31)
    assert out["sigma"] >= 0.05  # 4 quarters -> real std, floored


def test_fetch_surprise_sparse_history_uses_default_sigma():
    rows = [{"actual": 1.20, "estimate": 1.00, "period": "2026-03-31"}]
    out = fe.fetch_surprise(_Client({"stock/earnings": rows}), "k", "AAPL")
    assert out["sigma"] == 0.20  # < 4 quarters -> FOS fallback


def test_fetch_surprise_skips_null_estimate_keeps_date_consistent():
    rows = [
        {"actual": 1.20, "estimate": None, "period": "2026-06-30"},  # skipped
        {"actual": 1.10, "estimate": 1.00, "period": "2026-03-31"},  # used
    ]
    out = fe.fetch_surprise(_Client({"stock/earnings": rows}), "k", "AAPL")
    assert out["recent_surprise"] == pytest.approx(0.10)
    assert out["report_date"] == date(2026, 3, 31)  # matches the used quarter


def test_fetch_surprise_empty_is_none():
    assert fe.fetch_surprise(_Client({"stock/earnings": []}), "k", "X") is None


def test_load_upcoming_map():
    payload = {"earningsCalendar": [
        {"symbol": "AAPL", "date": "2026-07-30", "epsEstimate": 1.5,
         "revenueEstimate": 1.0e11},
        {"symbol": "NVDA", "date": "2026-08-25", "epsEstimate": None,
         "revenueEstimate": None},
    ]}
    out = fe.load_upcoming_map(
        _Client({"calendar/earnings": payload}), "k", datetime(2026, 6, 1, tzinfo=UTC)
    )
    assert out["AAPL"]["next_date"] == date(2026, 7, 30)
    assert out["AAPL"]["eps_estimate"] == 1.5
    assert out["NVDA"]["next_date"] == date(2026, 8, 25)


def test_load_upcoming_map_retries_read_timeout():
    request = httpx.Request("GET", "https://finnhub.io/api/v1/calendar/earnings")
    client = _SequenceClient([
        httpx.ReadTimeout("slow provider", request=request),
        _Resp({"earningsCalendar": [
            {"symbol": "AAPL", "date": "2026-08-25"},
        ]}),
    ])

    out = fe.load_upcoming_map(client, "k", datetime(2026, 8, 1, tzinfo=UTC))

    assert client.calls == 2
    assert out["AAPL"]["next_date"] == date(2026, 8, 25)


def test_fetch_surprise_does_not_retry_permanent_401():
    client = _SequenceClient([_Resp({"error": "invalid token"}, status_code=401)])

    with pytest.raises(httpx.HTTPStatusError):
        fe.fetch_surprise(client, "bad", "AAPL")

    assert client.calls == 1
