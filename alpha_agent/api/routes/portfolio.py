"""GET /api/portfolio — Portfolio and risk view endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.models.features import compute_features
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models

router = APIRouter(prefix="/api", tags=["portfolio"])

_CACHE_TTL = 300  # 5 minutes


@router.get("/portfolio")
async def portfolio_view(request: Request) -> dict:
    """Return portfolio positions, risk metrics, and backtest summary."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("portfolio_view")
    if cached is not None:
        return cached

    tickers = settings.dashboard_tickers
    n_assets = len(tickers)
    equal_weight = round(1.0 / n_assets, 4) if n_assets > 0 else 0.0

    positions: list[dict] = []
    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(tickers)

        for ticker in tickers:
            feats = compute_features(ohlcv, ticker)
            xgb_pred = models.xgboost.predict(feats)
            positions.append({
                "ticker": ticker,
                "direction": xgb_pred.direction,
                "weight": equal_weight,
                "score": round(xgb_pred.bull_prob, 4),
            })
    except Exception:
        positions = [
            {"ticker": t, "direction": "Neutral", "weight": equal_weight, "score": 0.5}
            for t in tickers
        ]

    weights = [p["weight"] for p in positions]
    result = {
        "positions": positions,
        "risk_metrics": {
            "total_exposure": round(sum(weights), 4),
            "max_single_position": round(max(weights), 4) if weights else 0.0,
            "diversification_score": round(1.0 / n_assets, 4) if n_assets > 0 else 0.0,
        },
        "backtest_summary": {
            "sharpe": None,
            "max_drawdown": None,
            "annual_return": None,
        },
    }

    cache.set("portfolio_view", result, _CACHE_TTL)
    return result
