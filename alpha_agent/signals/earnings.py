# alpha_agent/signals/earnings.py
"""Earnings catalyst signal. Two components contribute to z:
- Proximity: |days_until_or_since_earnings|; sigmoid -> [0, 1]
- Surprise: (actual - estimate) / |estimate|; +-50% saturates.

M4a: raw payload extended with structured upcoming-earnings fields
(next_date, eps_estimate, revenue_estimate) so CatalystsBlock can render
a real earnings card without a separate fetch.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

import pandas as pd

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_next_earnings, get_ticker


def _fetch_info(ticker: str) -> tuple[dict, object]:
    """Returns (info_dict, ticker_for_calendar). Keeping the legacy
    signature so existing tests that patch _fetch_info don't break - but
    now we also surface the Ticker for calendar extraction.

    `Ticker.earnings_dates` may return None, an empty DataFrame, a populated
    DataFrame, OR a list/dict depending on yfinance version + cache state.
    We strictly require a DataFrame before indexing — anything else falls
    through with no prior-quarter surprise enrichment (extract_next_earnings
    handles the upcoming-earnings card independently)."""
    t = get_ticker(ticker)
    info = dict(t.info or {})
    edates = getattr(t, "earnings_dates", None)
    if isinstance(edates, pd.DataFrame) and not edates.empty:
        try:
            info["epsActual"] = edates["Reported EPS"].iloc[0]
            info["epsEstimate"] = edates["EPS Estimate"].iloc[0]
            info["earningsDate"] = [edates.index[0]]
        except (KeyError, IndexError, AttributeError):
            # Shape drift in yfinance; skip surprise enrichment, keep going.
            pass
    return info, t


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info, ticker_obj = _fetch_info(ticker)
    actual = info.get("epsActual")
    est = info.get("epsEstimate")
    earn_dates = info.get("earningsDate") or []

    # Upcoming earnings (always try, even when surprise data is missing).
    # NB: Ticker.calendar property access itself can raise KeyError when
    # yfinance's internal pandas indexing returns ['Earnings Date'] form
    # for some ticker shapes — getattr default only catches AttributeError,
    # not KeyError. Wrap defensively.
    try:
        calendar = ticker_obj.calendar
    except (KeyError, ValueError, TypeError, AttributeError):
        calendar = None
    upcoming = extract_next_earnings(calendar, as_of=as_of)

    if not earn_dates or actual is None or est is None or est == 0:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={
                "surprise_pct": None, "days_to_earnings": None,
                "next_date": upcoming["next_date"],
                "days_until": upcoming["days_until"],
                "eps_estimate": upcoming["eps_estimate"],
                "revenue_estimate": upcoming["revenue_estimate"],
            },
            confidence=0.3, as_of=as_of, source="yfinance",
            error="missing earnings",
        )

    surprise = (actual - est) / abs(est)
    surprise_z = float(np.clip(surprise / 0.20, -2.0, 2.0))
    days = abs((earn_dates[0].replace(tzinfo=as_of.tzinfo) - as_of).days)
    proximity_w = float(np.exp(-days / 14))
    z = float(np.clip(surprise_z * proximity_w, -3.0, 3.0))

    return SignalScore(
        ticker=ticker, z=z,
        raw={
            "surprise_pct": surprise * 100,
            "days_to_earnings": days,
            "next_date": upcoming["next_date"],
            "days_until": upcoming["days_until"],
            "eps_estimate": upcoming["eps_estimate"],
            "revenue_estimate": upcoming["revenue_estimate"],
        },
        confidence=0.75, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
