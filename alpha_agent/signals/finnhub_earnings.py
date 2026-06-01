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
    r = client.get(
        f"{_BASE}/calendar/earnings",
        params={"from": frm, "to": to, "token": api_key}, timeout=30.0,
    )
    r.raise_for_status()
    out: dict[str, dict[str, Any]] = {}
    for row in r.json().get("earningsCalendar", []):
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
    r = client.get(
        f"{_BASE}/stock/earnings",
        params={"symbol": ticker.upper(), "token": api_key}, timeout=30.0,
    )
    r.raise_for_status()
    rows = r.json()
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
