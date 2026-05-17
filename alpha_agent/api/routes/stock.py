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


class MinuteBar(BaseModel):
    ts: str  # ISO 8601
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int


class MinuteBarsResponse(BaseModel):
    ticker: str
    date: str
    bars: list[MinuteBar]
    # True if the requested date is older than the 30d rolling retention
    # window of minute_bars (yfinance 1m retention limit). Frontend uses
    # this to distinguish a "no data, day out of coverage" message from a
    # "no data, weekend / holiday" message.
    out_of_range: bool


# Minute bars are kept on a rolling ~30 day window by minute_bars_puller.
# yfinance only retains 1m bars for the last 7-30 days, so older dates
# return an empty bars list with out_of_range=True instead of querying.
_MINUTE_BARS_RETENTION_DAYS = 30


@router.get("/{ticker}/minute_bars", response_model=MinuteBarsResponse)
async def stock_minute_bars(
    ticker: str,
    date: str,  # YYYY-MM-DD
) -> MinuteBarsResponse:
    """Return all minute_bars for one ticker on one calendar date (UTC).

    Returns empty bars list if date is older than the 30d rolling window
    or no bars exist (e.g. weekend / holiday / out-of-coverage ticker).
    Caller (frontend IntradayDrawer) renders an empty-state message.
    """
    ticker = ticker.upper()
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{date}', expected YYYY-MM-DD",
        ) from exc

    today_utc = datetime.now(UTC).date()
    out_of_range = date_obj < (today_utc - timedelta(days=_MINUTE_BARS_RETENTION_DAYS))
    if out_of_range:
        return MinuteBarsResponse(
            ticker=ticker,
            date=date,
            bars=[],
            out_of_range=True,
        )

    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT ts, open, high, low, close, volume FROM minute_bars
        WHERE ticker = $1
          AND (ts AT TIME ZONE 'UTC')::date = $2::date
        ORDER BY ts ASC
        """,
        ticker,
        date_obj,
    )
    bars = [
        MinuteBar(
            ts=r["ts"].isoformat(),
            open=float(r["open"]) if r["open"] is not None else None,
            high=float(r["high"]) if r["high"] is not None else None,
            low=float(r["low"]) if r["low"] is not None else None,
            close=float(r["close"]) if r["close"] is not None else None,
            volume=int(r["volume"]) if r["volume"] is not None else 0,
        )
        for r in rows
    ]
    return MinuteBarsResponse(
        ticker=ticker,
        date=date,
        bars=bars,
        out_of_range=False,
    )
