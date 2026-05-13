"""GET /api/stock/{ticker} — full card for one ticker, read-only from DB.

Ticker is normalised to uppercase.  Returns a stale flag when the most
recent row is older than 24 hours.  Spec §7.2.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.signals.yf_helpers import extract_ohlcv, get_ticker


def _safe_float(v, default: float = 0.0) -> float:
    """NaN/Inf/None → default. Mirrors picks.py — legacy DB rows may
    contain NaN composite/confidence written before storage-side
    sanitization was added."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default

router = APIRouter(prefix="/api/stock", tags=["stock"])


class FullCard(BaseModel):
    ticker: str
    rating: str
    confidence: float
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]
    breakdown: list[dict]


class StockResponse(BaseModel):
    card: FullCard
    stale: bool


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(
    ticker: str = Path(min_length=1, max_length=10),
) -> StockResponse:
    """Return the most-recent RatingCard for *ticker*."""
    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        SELECT ticker, date, composite, rating, confidence, breakdown, fetched_at
        FROM daily_signals_fast
        WHERE ticker = $1
        ORDER BY date DESC, fetched_at DESC
        LIMIT 1
        """,
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown_data: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    fetched_at: datetime = row["fetched_at"]
    stale = (datetime.now(UTC) - fetched_at) > timedelta(hours=24)

    card = FullCard(
        ticker=row["ticker"],
        rating=row["rating"] or "HOLD",
        confidence=_safe_float(row["confidence"]),
        composite_score=_safe_float(row["composite"]),
        as_of=fetched_at.isoformat(),
        top_drivers=top_drivers(breakdown_data),
        top_drags=top_drags(breakdown_data),
        breakdown=breakdown_data,
    )
    return StockResponse(card=card, stale=stale)


class OhlcvBar(BaseModel):
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int


class OhlcvResponse(BaseModel):
    ticker: str
    period: str
    bars: list[OhlcvBar]


# yfinance period vocabulary: 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max.
# Restrict to the ones the chart UI offers to avoid surprises.
_AllowedPeriod = Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"]


@router.get("/{ticker}/ohlcv", response_model=OhlcvResponse)
async def stock_ohlcv(
    ticker: str,
    period: _AllowedPeriod = "6mo",
) -> OhlcvResponse:
    """Lazy OHLCV feed for the price chart. Cache headers in middleware
    (or here, future) - for now relies on FE-side staleness."""
    ticker = ticker.upper()
    df = get_ticker(ticker).history(period=period)
    bars = extract_ohlcv(df)
    return OhlcvResponse(
        ticker=ticker,
        period=period,
        bars=[OhlcvBar(**b) for b in bars],
    )
