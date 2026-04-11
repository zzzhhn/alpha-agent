"""GET /api/market — Market data and feature matrix endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.models.features import compute_features
from alpha_agent.models.trainer import _fetch_training_data

router = APIRouter(prefix="/api", tags=["market"])

_CACHE_TTL = 300  # 5 minutes


def _df_to_records(df) -> list[dict]:
    """Convert a DataFrame to JSON-safe list of dicts."""
    out = df.reset_index()
    # Convert any datetime columns to ISO strings
    for col in out.columns:
        if hasattr(out[col], "dt"):
            out[col] = out[col].astype(str)
    return out.to_dict(orient="records")


@router.get("/market")
async def market_data(request: Request) -> dict:
    """Return recent OHLCV data and computed features per ticker."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("market_data")
    if cached is not None:
        return cached

    tickers = settings.dashboard_tickers

    try:
        ohlcv = _fetch_training_data(tickers)

        ohlcv_by_ticker = {}
        features_by_ticker = {}
        for ticker in tickers:
            ticker_ohlcv = ohlcv.xs(ticker, level="stock_code")
            ohlcv_by_ticker[ticker] = _df_to_records(ticker_ohlcv.tail(20))

            feats = compute_features(ohlcv, ticker)
            features_by_ticker[ticker] = _df_to_records(feats.tail(10))

    except Exception:
        ohlcv_by_ticker = {}
        features_by_ticker = {}

    result = {
        "ohlcv": ohlcv_by_ticker,
        "features": features_by_ticker,
        "tickers": tickers,
    }

    cache.set("market_data", result, _CACHE_TTL)
    return result
