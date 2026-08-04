"""Finnhub earnings fetch for the earnings (Catalyst) signal.

Used by the offline ingestion job (scripts/ingest_earnings_finnhub.py), NOT the
signal path. yfinance returned usable earnings data for only ~21/557 tickers
(Yahoo deprecated estimates); Finnhub's free tier covers the full universe.

Two endpoints:
  /stock/earnings?symbol=X       -> last 4 quarters {actual, estimate, surprise,
                                    period}, per ticker (the surprise + SUE std).
  /calendar/earnings?from=&to=   -> ALL upcoming earnings in a window, one call
                                    (next_date + consensus for the UI card).

Free tier: 60 req/min, so the per-ticker loop throttles ~1.05s.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from statistics import pstdev
from typing import Any

import httpx

_BASE = "https://finnhub.io/api/v1"
_THROTTLE_S = 1.05  # ~57/min, under the 60/min free-tier ceiling
_SIGMA_FLOOR = 0.05
_SIGMA_DEFAULT = 0.20  # Foster-Olsen-Shevlin fallback when < 4 quarters
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_S = 1.0
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _get_json(
    client: httpx.Client,
    url: str,
    *,
    params: dict[str, Any],
    max_attempts: int = _MAX_ATTEMPTS,
) -> Any:
    """GET JSON with bounded retry for transient provider failures.

    Finnhub occasionally stalls long enough to hit the 30s read timeout. A
    single timeout must not abort the whole daily universe ingestion, while
    authentication and other permanent 4xx failures should still surface
    immediately.
    """
    for attempt in range(1, max_attempts + 1):
        response: httpx.Response | None = None
        try:
            response = client.get(url, params=params, timeout=_TIMEOUT)
            if response.status_code not in _RETRYABLE_STATUS:
                response.raise_for_status()
                return response.json()
            response.raise_for_status()
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        ):
            if attempt >= max_attempts:
                raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS or attempt >= max_attempts:
                raise

        delay = _BACKOFF_BASE_S * (2 ** (attempt - 1))
        retry_after = response.headers.get("retry-after") if response is not None else None
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        time.sleep(delay)

    raise RuntimeError("unreachable retry state")


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_upcoming_map(
    client: httpx.Client, api_key: str, as_of: datetime, horizon_days: int = 100
) -> dict[str, dict[str, Any]]:
    """{TICKER: {next_date, eps_estimate, revenue_estimate}} for the window."""
    frm = as_of.date().isoformat()
    to = (as_of.date() + timedelta(days=horizon_days)).isoformat()
    payload = _get_json(
        client,
        f"{_BASE}/calendar/earnings",
        params={"from": frm, "to": to, "token": api_key},
    )
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("earningsCalendar", []):
        sym = str(row.get("symbol", "")).upper()
        if not sym or sym in out:  # keep the earliest (list is date-descending)
            continue
        out[sym] = {
            "next_date": _parse_date(row.get("date")),
            "eps_estimate": row.get("epsEstimate"),
            "revenue_estimate": row.get("revenueEstimate"),
        }
    return out


def fetch_surprise(
    client: httpx.Client, api_key: str, ticker: str
) -> dict[str, Any] | None:
    """{recent_surprise, sigma, report_date} from the last 4 reported quarters,
    or None when Finnhub has no usable earnings history for the ticker."""
    time.sleep(_THROTTLE_S)
    rows = _get_json(
        client,
        f"{_BASE}/stock/earnings",
        params={"symbol": ticker.upper(), "token": api_key},
    )
    if not isinstance(rows, list) or not rows:
        return None
    # Most-recent-first. Relative surprise = (actual - estimate) / |estimate|.
    # Keep (rel, period) pairs so report_date matches the quarter we use.
    pairs: list[tuple[float, Any]] = []
    for row in rows:
        actual, est = row.get("actual"), row.get("estimate")
        if actual is None or est in (None, 0):
            continue
        pairs.append(((actual - est) / abs(est), row.get("period")))
    if not pairs:
        return None
    rels = [p[0] for p in pairs]
    sigma = max(pstdev(rels), _SIGMA_FLOOR) if len(rels) >= 4 else _SIGMA_DEFAULT
    return {
        "recent_surprise": pairs[0][0],
        "sigma": sigma,
        "report_date": _parse_date(pairs[0][1]),
    }
