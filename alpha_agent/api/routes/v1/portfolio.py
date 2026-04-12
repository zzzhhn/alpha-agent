"""v1 Portfolio endpoints — positions and risk metrics."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from alpha_agent.api.cache import TTLCache
from alpha_agent.api.routes.v1.schemas import (
    BacktestResult,
    PortfolioPositionsResponse,
    PortfolioRiskResponse,
    Position,
    RiskMetrics,
)
from alpha_agent.models.features import compute_features
from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_CACHE_TTL = 300


def _build_positions(settings) -> list[Position]:
    """Compute current portfolio positions from model scores."""
    tickers = settings.dashboard_tickers
    n_assets = len(tickers)
    equal_weight = round(1.0 / n_assets, 4) if n_assets > 0 else 0.0

    try:
        models = get_or_train_models()
        ohlcv = _fetch_training_data(tickers)

        positions: list[Position] = []
        for ticker in tickers:
            feats = compute_features(ohlcv, ticker)
            xgb_pred = models.xgboost.predict(feats)
            positions.append(
                Position(
                    ticker=ticker,
                    direction=xgb_pred.direction,
                    weight=equal_weight,
                    score=round(xgb_pred.bull_prob, 4),
                )
            )
        return positions
    except Exception:
        return [
            Position(
                ticker=t,
                direction="Neutral",
                weight=equal_weight,
                score=0.5,
            )
            for t in tickers
        ]


@router.get("/positions", response_model=PortfolioPositionsResponse)
async def portfolio_positions(request: Request) -> PortfolioPositionsResponse:
    """Return current portfolio positions."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_portfolio_positions")
    if cached is not None:
        return cached

    positions = _build_positions(settings)

    result = PortfolioPositionsResponse(
        positions=positions,
        total_positions=len(positions),
    )

    cache.set("v1_portfolio_positions", result, _CACHE_TTL)
    return result


@router.get("/risk", response_model=PortfolioRiskResponse)
async def portfolio_risk(request: Request) -> PortfolioRiskResponse:
    """Return portfolio risk metrics and backtest summary."""
    cache: TTLCache = request.app.state.cache
    settings = request.app.state.settings

    cached = cache.get("v1_portfolio_risk")
    if cached is not None:
        return cached

    positions = _build_positions(settings)
    weights = [p.weight for p in positions]
    n_assets = len(positions)

    risk = RiskMetrics(
        total_exposure=round(sum(weights), 4),
        max_single_position=round(max(weights), 4) if weights else 0.0,
        diversification_score=round(1.0 / n_assets, 4) if n_assets > 0 else 0.0,
        var_95=None,
        realized_volatility=None,
    )

    result = PortfolioRiskResponse(
        risk_metrics=risk,
        positions=positions,
        backtest_summary=BacktestResult(
            sharpe=None,
            max_drawdown=None,
            annual_return=None,
            total_trades=0,
            win_rate=None,
            period={
                "start": settings.backtest_start,
                "end": settings.backtest_end,
            },
        ),
    )

    cache.set("v1_portfolio_risk", result, _CACHE_TTL)
    return result
