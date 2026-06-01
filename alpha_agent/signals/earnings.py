# alpha_agent/signals/earnings.py
"""Earnings catalyst signal (PEAD). z = standardized surprise * proximity decay.

Architecture (2026-06-01): the signal no longer calls yfinance inline (which
returned usable earnings for only ~21/557 tickers; Yahoo deprecated estimates).
A daily job (scripts/ingest_earnings_finnhub.py via GitHub Actions, using
alpha_agent.signals.finnhub_earnings) precomputes per-ticker surprise inputs
into earnings_finnhub. Each signal cron run loads that table once and calls
prime_cache(...); fetch_signal reads the primed dict (no network on the path).

z = clip( clip(recent_surprise / sigma, -3, 3) * exp(-days_since_report / 14),
          -3, 3 )

Academic anchors:
- SUE standardization: Foster, Olsen, Shevlin (1984) — surprise / firm's rolling
  surprise std (computed in the ingestion over 4 quarters, floor 0.05).
- PEAD: Ball & Brown (1968); Bernard & Thomas (1990) — post-announcement drift
  decays over ~60 days, modeled here by the exp(-days/14) proximity weight.
- Contrast effects: Hartzmark & Shue (2018) — peer-relative refinement, TBD.

No earnings data for a ticker => z=None: dropped from the composite (combine
treats non-finite z as a drop) and shown "—" in the grade, not a fake neutral.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

# Primed once per cron run from earnings_finnhub:
# {TICKER: {recent_surprise, sigma, report_date, next_date, eps_estimate,
#           revenue_estimate}}.
_CACHE: dict[str, dict] = {}


def prime_cache(values: dict[str, dict]) -> None:
    """Replace the in-memory earnings cache (called by the signal crons)."""
    global _CACHE
    _CACHE = dict(values)


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    entry = _CACHE.get(ticker.upper())
    next_date = entry.get("next_date") if entry else None
    eps_est = entry.get("eps_estimate") if entry else None
    rev_est = entry.get("revenue_estimate") if entry else None
    days_until = (next_date - as_of.date()).days if next_date else None

    surprise = entry.get("recent_surprise") if entry else None
    sigma = entry.get("sigma") if entry else None
    report_date = entry.get("report_date") if entry else None

    # No usable surprise history -> no catalyst signal (z=None -> "—"), but
    # still surface any upcoming-earnings card fields we do have.
    if surprise is None or not sigma or report_date is None:
        return SignalScore(
            ticker=ticker, z=None,  # type: ignore[typeddict-item]
            raw={
                "surprise_pct": None, "days_to_earnings": None,
                "next_date": next_date.isoformat() if next_date else None,
                "days_until": days_until, "eps_estimate": eps_est,
                "revenue_estimate": rev_est,
            },
            confidence=0.0, as_of=as_of, source="finnhub",
            error="no earnings data",
        )

    surprise_z = float(np.clip(surprise / sigma, -3.0, 3.0))
    days_since = max((as_of.date() - report_date).days, 0)
    proximity = float(np.exp(-days_since / 14))
    z = float(np.clip(surprise_z * proximity, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={
            "surprise_pct": surprise * 100,
            "days_to_earnings": days_since,
            "next_date": next_date.isoformat() if next_date else None,
            "days_until": days_until,
            "eps_estimate": eps_est,
            "revenue_estimate": rev_est,
        },
        confidence=0.75, as_of=as_of, source="finnhub", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="finnhub")
