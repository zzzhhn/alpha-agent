"""Cumulative Abnormal Return (CAR) vs SPY benchmark.

Implements the standard event-study methodology (Brown-Warner 1985,
MacKinlay 1997) at minute-level granularity: realized ticker return
minus realized SPY return over a fixed N-minute window starting at
event_ts. Window default 60 minutes per Phase 6a spec.

CAR = (ticker_close_end / ticker_close_start - 1)
      - (spy_close_end / spy_close_start - 1)

Returns None if either ticker or SPY bars are missing in the window
(caller falls back to daily-level aggregation).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_agent.data.minute_price import get_bars_for_event


@dataclass
class CarResult:
    car_pct: float       # ticker_return - spy_return, in decimal (0.003 = 0.3%)
    ticker_return: float
    spy_return: float
    n_bars: int


def _return_from_bars(df) -> float | None:
    if df is None or df.empty or len(df) < 2:
        return None
    closes = df["close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1)


async def compute_car(
    pool, ticker: str, event_ts: datetime, window_min: int = 60,
) -> CarResult | None:
    ticker_df = await get_bars_for_event(pool, ticker, event_ts, window_min)
    spy_df    = await get_bars_for_event(pool, "SPY",   event_ts, window_min)
    tr = _return_from_bars(ticker_df)
    sr = _return_from_bars(spy_df)
    if tr is None or sr is None:
        return None
    return CarResult(
        car_pct=tr - sr,
        ticker_return=tr,
        spy_return=sr,
        n_bars=int(min(len(ticker_df), len(spy_df))),
    )
