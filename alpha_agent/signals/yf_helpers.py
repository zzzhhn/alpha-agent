# alpha_agent/signals/yf_helpers.py
"""Centralized yfinance access with Ticker caching + structured extractors.

Why this module exists:
- yfinance creates a fresh HTTP session per Ticker instance. Without caching,
  every signal module re-creates a Ticker for the same symbol, multiplying
  the request count under cron load.
- `info` dicts are sparse for thinly-traded names. Returning `None` for any
  missing field (rather than a default `0` or `nan`) lets frontend
  components fall back to "—" cleanly + keeps Neon JSONB happy (NaN tokens
  are rejected by Postgres' JSON parser).
- All extractors take pre-fetched data (dicts / DataFrames) so the actual
  network call lives in one place (`get_ticker`) and tests don't need a
  network mock for every signal module.
"""
from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf

# 10-minute TTL keeps Ticker instances reusable across one cron cycle without
# accumulating stale state across days.
_TTL_SECONDS = 600
_cache: dict[str, tuple[float, yf.Ticker]] = {}

_POSITIVE_WORDS = {
    "beats", "beat", "raises", "raise", "surge", "surges", "soars", "rally",
    "upgrade", "strong", "record", "boost", "gains", "outperform",
}
_NEGATIVE_WORDS = {
    "misses", "miss", "cuts", "cut", "plunges", "plunge", "drops", "fall",
    "downgrade", "weak", "concern", "loss", "lawsuit", "probe", "investigation",
}


def get_ticker(symbol: str) -> yf.Ticker:
    """Cached yf.Ticker. Same symbol within TTL → same instance."""
    now = time.time()
    cached = _cache.get(symbol)
    if cached is not None and (now - cached[0]) < _TTL_SECONDS:
        return cached[1]
    t = yf.Ticker(symbol)
    _cache[symbol] = (now, t)
    return t


def _safe_float(v: Any) -> float | None:
    """yfinance returns mixed int/float/NaN/None. Normalize to float|None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def extract_fundamentals(info: dict) -> dict[str, float | None]:
    """Pluck the 8 retail-relevant metrics from yfinance Ticker.info.
    Keys aligned with frontend FundamentalsBlock display order."""
    return {
        "pe_trailing": _safe_float(info.get("trailingPE")),
        "pe_forward": _safe_float(info.get("forwardPE")),
        "eps_ttm": _safe_float(info.get("trailingEps")),
        "market_cap": _safe_float(info.get("marketCap")),
        "dividend_yield": _safe_float(info.get("dividendYield")),
        "profit_margin": _safe_float(info.get("profitMargins")),
        "debt_to_equity": _safe_float(info.get("debtToEquity")),
        "beta": _safe_float(info.get("beta")),
    }


def _classify_sentiment(title: str) -> str:
    """Keyword-rule sentiment. M4a does not call an LLM here; M4b can replace
    this with a Rich-brief enrichment step that scores headlines via the user's
    BYOK key."""
    lower = title.lower()
    pos_hits = sum(1 for w in _POSITIVE_WORDS if w in lower)
    neg_hits = sum(1 for w in _NEGATIVE_WORDS if w in lower)
    if pos_hits > neg_hits:
        return "pos"
    if neg_hits > pos_hits:
        return "neg"
    return "neu"


def extract_news_items(raw: list[dict], limit: int = 5) -> list[dict]:
    """yfinance Ticker.news → frontend-renderable list. Returns at most
    `limit` items (most-recent first per yfinance default order)."""
    out: list[dict] = []
    for item in raw[:limit]:
        title = item.get("title") or ""
        ts_unix = item.get("providerPublishTime")
        try:
            ts_iso = datetime.fromtimestamp(int(ts_unix), tz=UTC).isoformat() if ts_unix else ""
        except (TypeError, ValueError):
            ts_iso = ""
        out.append({
            "title": title,
            "publisher": item.get("publisher") or "",
            "published_at": ts_iso,
            "link": item.get("link") or "",
            "sentiment": _classify_sentiment(title),
        })
    return out


def extract_next_earnings(
    calendar: pd.DataFrame | None, *, as_of: datetime
) -> dict[str, Any]:
    """Decode `yf.Ticker.calendar` (a DataFrame) into a structured upcoming
    earnings block. Returns all-None fields if no calendar entry exists."""
    none_payload: dict[str, Any] = {
        "next_date": None, "days_until": None,
        "eps_estimate": None, "revenue_estimate": None,
    }
    if calendar is None or len(calendar) == 0:
        return none_payload
    try:
        date = pd.to_datetime(calendar["Earnings Date"].iloc[0])
        if date.tzinfo is None:
            date = date.tz_localize("UTC")
        days = (date - as_of).days
        return {
            "next_date": date.strftime("%Y-%m-%d"),
            "days_until": int(days),
            "eps_estimate": _safe_float(calendar["EPS Estimate"].iloc[0])
                if "EPS Estimate" in calendar else None,
            "revenue_estimate": _safe_float(calendar["Revenue Estimate"].iloc[0])
                if "Revenue Estimate" in calendar else None,
        }
    except (KeyError, IndexError, ValueError):
        return none_payload


def extract_ohlcv(df: pd.DataFrame) -> list[dict]:
    """yfinance.Ticker.history() DataFrame → list of {date, ohlcv} dicts
    serialisable to JSON for the chart endpoint."""
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for ts, row in df.iterrows():
        out.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": _safe_float(row.get("Open")) or 0.0,
            "high": _safe_float(row.get("High")) or 0.0,
            "low": _safe_float(row.get("Low")) or 0.0,
            "close": _safe_float(row.get("Close")) or 0.0,
            "volume": int(_safe_float(row.get("Volume")) or 0),
        })
    return out
