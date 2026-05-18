# alpha_agent/signals/earnings.py
"""Earnings catalyst signal. Two components contribute to z:
- Proximity: |days_until_or_since_earnings|; sigmoid -> [0, 1]
- Surprise: standardized SUE per Foster-Olsen-Shevlin (1984); see below.

Academic anchors (2020-2025 modernization, 2026-05-18):
- Primary modern reference: Hartzmark & Shue (2018, JoF 73(4)) "A Tough Act
  to Follow: Contrast Effects in Financial Markets" — surprise magnitude is
  contextualized by *yesterday's* surprises (a +5% surprise after a series
  of +10% surprises generates a *negative* abnormal return). Refines the
  standard PEAD setup.
- SUE standardization: Foster, Olsen, Shevlin (1984, Accounting Review 59(4))
  "Earnings Releases, Anomalies, and the Behavior of Security Returns" —
  established that surprise should be standardized by the firm's historical
  surprise std (Standardized Unexpected Earnings), not a fixed pct cap.
  Implemented here as a 4q rolling std with 0.20 fallback for sparse-history
  tickers (preserves prior behavior on small caps with <4 reported quarters).
- Capital-gains overhang: Frazzini (2006, JoF 61(4)) "The Disposition Effect
  and Underreaction to News" — PEAD magnitude depends on overhang; useful
  for sub-segmenting which surprises drift more.
- Pre-event premium: So & Wang (2014, JFE 114(1)) "News-Driven Return
  Reversals: Liquidity Provision Ahead of Earnings Announcements" — could
  refine proximity-decay to capture both pre-event premium and post-drift.
- Historical anchors: Ball & Brown (1968, JAR 6(2)) foundational PEAD;
  Bernard & Thomas (1990, JAE 13(4)) systematic 60-day drift documentation.

M4a: raw payload extended with structured upcoming-earnings fields
(next_date, eps_estimate, revenue_estimate) so CatalystsBlock can render
a real earnings card without a separate fetch.

Phase X TBD: add Hartzmark-Shue contrast adjustment using same-sector peers'
SUEs from the last 5 trading days:
  adj_surprise = sue - 0.3 * sue_peer_5d_mean
Requires sector classification + recent-earnings panel join, both available
in our DB but not yet wired into this signal.
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
            # Stash the full DataFrame so _compute_sigma_surprise can build
            # the Foster-Olsen-Shevlin SUE denominator from historical
            # quarters. The legacy signature keeps `info` as the primary
            # output for back-compat with tests that patch _fetch_info.
            info["_edates_df"] = edates
        except (KeyError, IndexError, AttributeError):
            # Shape drift in yfinance; skip surprise enrichment, keep going.
            pass
    return info, t


def _compute_sigma_surprise(edates_df) -> float:
    """Foster-Olsen-Shevlin (1984) SUE denominator: rolling std of historical
    EPS surprise scaled by |estimate|. Defaults to the legacy 0.20 hardcode
    when fewer than 4 quarters of surprise history are available — preserves
    back-compat for small caps + brand-new IPOs. Floors at 0.05 so a
    perfectly-consistent firm (sigma → 0) doesn't divide by zero.

    Returns a unitless fraction (consistent with how `surprise` is computed
    in _fetch as (actual - est) / |est|)."""
    if not isinstance(edates_df, pd.DataFrame) or len(edates_df) < 4:
        return 0.20
    try:
        actual = edates_df["Reported EPS"]
        est = edates_df["EPS Estimate"]
        rel_surprise = ((actual - est) / est.abs()).dropna()
    except (KeyError, AttributeError):
        return 0.20
    if len(rel_surprise) < 4:
        return 0.20
    return float(max(rel_surprise.std(), 0.05))


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
    # SUE-style standardization (Foster-Olsen-Shevlin 1984): divide surprise
    # by the firm's historical surprise std rather than a fixed 20% cap.
    # Clip widened from [-2, 2] to [-3, 3] since standardized SUEs have a
    # wider distribution than fixed-cap percentages.
    sigma = _compute_sigma_surprise(info.get("_edates_df"))
    surprise_z = float(np.clip(surprise / sigma, -3.0, 3.0))
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
