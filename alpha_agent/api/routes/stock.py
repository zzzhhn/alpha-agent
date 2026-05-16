"""GET /api/stock/{ticker} — full card for one ticker, read-only from DB.

Ticker is normalised to uppercase.  Returns a stale flag when the most
recent row is older than 24 hours.  Spec §7.2.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.signal_lookup import fetch_latest_signal
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.signals.yf_helpers import extract_ohlcv, get_ticker

router = APIRouter(prefix="/api/stock", tags=["stock"])


class NewsItemLite(BaseModel):
    id: int
    source: str
    headline: str
    url: str
    published_at: str
    sentiment_score: float | None
    sentiment_label: str | None


class FullCard(BaseModel):
    ticker: str
    rating: str
    confidence: float
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]
    breakdown: list[dict]
    # True for a slow-only ticker: daily-pipeline data, rating/confidence
    # derived, no fast factors, can be up to ~1 day old.
    partial: bool = False
    news_items: list[NewsItemLite] = []


class StockResponse(BaseModel):
    card: FullCard
    stale: bool


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(
    ticker: str = Path(min_length=1, max_length=10),
) -> StockResponse:
    """Return the most-recent RatingCard for *ticker*.

    Reads via fetch_latest_signal so a slow-only ticker (covered by the
    daily pipeline but not the intraday cron, e.g. NVDA) resolves to a
    partial card instead of 404ing.
    """
    ticker = ticker.upper()
    pool = await get_db_pool()
    sig = await fetch_latest_signal(pool, ticker)
    if sig is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    fetched_at: datetime = sig["fetched_at"]
    stale = (datetime.now(UTC) - fetched_at) > timedelta(hours=24)

    news_rows = await pool.fetch(
        """
        SELECT id, source, headline, url, published_at,
               sentiment_score, sentiment_label
        FROM news_items
        WHERE ticker = $1
        ORDER BY published_at DESC
        LIMIT 20
        """,
        ticker,
    )
    news_items = [
        NewsItemLite(
            id=r["id"],
            source=r["source"],
            headline=r["headline"],
            url=r["url"],
            published_at=r["published_at"].isoformat(),
            sentiment_score=r["sentiment_score"],
            sentiment_label=r["sentiment_label"],
        )
        for r in news_rows
    ]

    card = FullCard(
        ticker=sig["ticker"],
        rating=sig["rating"],
        confidence=sig["confidence"],
        composite_score=sig["score"],
        as_of=fetched_at.isoformat(),
        top_drivers=top_drivers(sig["breakdown"]),
        top_drags=top_drags(sig["breakdown"]),
        breakdown=sig["breakdown"],
        partial=sig["partial"],
        news_items=news_items,
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
