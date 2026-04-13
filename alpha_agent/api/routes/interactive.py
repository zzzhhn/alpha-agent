"""Interactive POST endpoints — user-controlled backtest, ticker analysis, search.

These endpoints wrap existing ML modules with parameter acceptance, transforming
the read-only dashboard into a research workstation.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["interactive"])


# ── Request / Response schemas ──────────────────────────────────────────────


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_oversold: float = Field(default=30.0, ge=5, le=50)
    rsi_overbought: float = Field(default=70.0, ge=50, le=95)
    macd_fast: int = Field(default=12, ge=2, le=50)
    macd_slow: int = Field(default=26, ge=5, le=100)
    bollinger_period: int = Field(default=20, ge=5, le=100)
    bollinger_std: float = Field(default=2.0, ge=0.5, le=4.0)
    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=50.0)
    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    position_size_pct: float = Field(default=100.0, ge=10.0, le=100.0)
    initial_capital: float = Field(default=100000.0, ge=1000)

    model_config = {"protected_namespaces": ()}


class TickerAnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    rsi_period: int = Field(default=14, ge=2, le=100)
    macd_fast: int = Field(default=12, ge=2, le=50)
    macd_slow: int = Field(default=26, ge=5, le=100)
    bollinger_period: int = Field(default=20, ge=5, le=100)

    model_config = {"protected_namespaces": ()}


class TickerSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20)

    model_config = {"protected_namespaces": ()}


# ── Constants ───────────────────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 252
_POPULAR_US_TICKERS = [
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology"},
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
    {"ticker": "GOOG", "name": "Alphabet Inc.", "sector": "Technology"},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Cyclical"},
    {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Technology"},
    {"ticker": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Cyclical"},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "sector": "Technology"},
    {"ticker": "NFLX", "name": "Netflix Inc.", "sector": "Communication"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financial"},
    {"ticker": "V", "name": "Visa Inc.", "sector": "Financial"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
    {"ticker": "WMT", "name": "Walmart Inc.", "sector": "Consumer Defensive"},
    {"ticker": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Defensive"},
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy"},
    {"ticker": "BAC", "name": "Bank of America Corp.", "sector": "Financial"},
    {"ticker": "DIS", "name": "Walt Disney Company", "sector": "Communication"},
    {"ticker": "INTC", "name": "Intel Corporation", "sector": "Technology"},
    {"ticker": "CRM", "name": "Salesforce Inc.", "sector": "Technology"},
    {"ticker": "COST", "name": "Costco Wholesale Corp.", "sector": "Consumer Defensive"},
]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fetch_ohlcv(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch OHLCV data using YFinanceProvider (AKShare primary, yfinance fallback)."""
    from alpha_agent.data.us_provider import YFinanceProvider

    start_fmt = start_date.replace("-", "")
    end_fmt = end_date.replace("-", "")
    provider = YFinanceProvider()
    return provider.fetch([ticker], start_fmt, end_fmt)


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_macd(close: pd.Series, fast: int = 12, slow: int = 26) -> tuple[pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal_line


def _compute_bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return upper, lower, sma


def _sharpe_ratio(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    mean_r = float(returns.mean())
    std_r = float(returns.std(ddof=1))
    if std_r < 1e-12:
        return 0.0
    return mean_r / std_r * math.sqrt(TRADING_DAYS_PER_YEAR)


def _sortino_ratio(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    mean_r = float(returns.mean())
    downside = returns[returns < 0]
    if len(downside) < 2:
        return 0.0
    down_std = float(downside.std(ddof=1))
    if down_std < 1e-12:
        return 0.0
    return mean_r / down_std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min())


# ── POST /api/v1/backtest/run ───────────────────────────────────────────────


@router.post("/api/v1/backtest/run")
async def run_backtest(req: BacktestRequest) -> dict[str, Any]:
    """Run a signal-based backtest with user-specified indicator parameters.

    Strategy: RSI mean-reversion + MACD trend confirmation + Bollinger band filter.
    - Buy when RSI < oversold AND MACD histogram positive AND price near lower Bollinger
    - Sell when RSI > overbought OR MACD histogram turns negative
    """
    try:
        ohlcv = _fetch_ohlcv(req.ticker, req.start_date, req.end_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}") from exc

    if ohlcv.empty:
        raise HTTPException(status_code=404, detail=f"No data for {req.ticker} in date range")

    # Extract single-ticker close series
    try:
        df = ohlcv.xs(req.ticker, level="stock_code").copy()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Ticker {req.ticker} not found in data")

    close = df["close"]
    if len(close) < max(req.macd_slow, req.bollinger_period, req.rsi_period) + 10:
        raise HTTPException(status_code=400, detail="Not enough data for selected parameters")

    # Compute indicators with user params
    rsi = _compute_rsi(close, req.rsi_period)
    macd_line, signal_line = _compute_macd(close, req.macd_fast, req.macd_slow)
    macd_hist = macd_line - signal_line
    bb_upper, bb_lower, bb_mid = _compute_bollinger(close, req.bollinger_period, req.bollinger_std)
    bb_pctb = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # Generate signals and simulate
    capital = req.initial_capital
    position = 0.0  # shares held
    entry_price = 0.0
    cash = capital
    trades: list[dict] = []
    equity_values: list[dict] = []

    for i in range(len(close)):
        date_str = str(close.index[i].date()) if hasattr(close.index[i], "date") else str(close.index[i])
        price = float(close.iloc[i])
        r = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50.0
        mh = float(macd_hist.iloc[i]) if not np.isnan(macd_hist.iloc[i]) else 0.0
        bp = float(bb_pctb.iloc[i]) if not np.isnan(bb_pctb.iloc[i]) else 0.5

        # Buy signal: at least 2 of 3 conditions (RSI oversold, MACD positive, near lower band)
        buy_signals = int(r < req.rsi_oversold) + int(mh > 0) + int(bp < 0.3)
        if position == 0 and buy_signals >= 2:
            alloc = cash * (req.position_size_pct / 100.0)
            shares = int(alloc / price)
            if shares > 0:
                position = shares
                entry_price = price
                cash -= shares * price
                trades.append({"date": date_str, "side": "BUY", "price": round(price, 2), "shares": shares, "pnl": 0.0})

        # Sell signal: stop-loss / take-profit / RSI overbought / MACD turning down
        elif position > 0:
            change_pct = (price - entry_price) / entry_price * 100.0
            hit_stop = req.stop_loss_pct > 0 and change_pct <= -req.stop_loss_pct
            hit_tp = req.take_profit_pct > 0 and change_pct >= req.take_profit_pct
            hit_signal = r > req.rsi_overbought or mh < 0
            if hit_stop or hit_tp or hit_signal:
                side_label = "SELL (stop)" if hit_stop else "SELL (tp)" if hit_tp else "SELL"
                pnl = position * price - (entry_price * position)
                trades.append({"date": date_str, "side": side_label, "price": round(price, 2), "shares": int(position), "pnl": round(pnl, 2)})
                cash += position * price
                position = 0

        portfolio_value = cash + position * price
        equity_values.append({"date": date_str, "value": round(portfolio_value, 2)})

    # Close any open position at end
    if position > 0:
        last_price = float(close.iloc[-1])
        pnl = position * last_price - (entry_price * position)
        date_str = str(close.index[-1].date()) if hasattr(close.index[-1], "date") else str(close.index[-1])
        trades.append({"date": date_str, "side": "SELL (close)", "price": round(last_price, 2), "shares": int(position), "pnl": round(pnl, 2)})
        cash += position * last_price
        position = 0
        equity_values[-1]["value"] = round(cash, 2)

    # Compute performance metrics
    equity_series = pd.Series([e["value"] for e in equity_values])
    daily_returns = equity_series.pct_change().dropna()

    total_return = (cash - capital) / capital
    sharpe = _sharpe_ratio(daily_returns)
    sortino = _sortino_ratio(daily_returns)
    mdd = _max_drawdown(equity_series) if len(equity_series) > 0 else 0.0

    winning_trades = [t for t in trades if t["side"] == "SELL" and t["pnl"] > 0]
    sell_trades = [t for t in trades if t["side"].startswith("SELL")]
    win_rate = len(winning_trades) / max(len(sell_trades), 1)

    # Downsample equity curve for frontend (max 500 points)
    step = max(1, len(equity_values) // 500)
    equity_sampled = equity_values[::step]
    if equity_values and equity_sampled[-1] != equity_values[-1]:
        equity_sampled.append(equity_values[-1])

    return {
        "ticker": req.ticker,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "params": {
            "rsi_period": req.rsi_period,
            "rsi_oversold": req.rsi_oversold,
            "rsi_overbought": req.rsi_overbought,
            "macd_fast": req.macd_fast,
            "macd_slow": req.macd_slow,
            "bollinger_period": req.bollinger_period,
        },
        "metrics": {
            "total_return": round(total_return, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "max_drawdown": round(mdd, 4),
            "win_rate": round(win_rate, 4),
            "total_trades": len(sell_trades),
            "final_value": round(cash, 2),
        },
        "equity_curve": equity_sampled,
        "trades": trades[-50:],  # Last 50 trades for display
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── POST /api/v1/ticker/analyze ────────────────────────────────────────────


@router.post("/api/v1/ticker/analyze")
async def analyze_ticker(req: TickerAnalyzeRequest) -> dict[str, Any]:
    """Analyze a ticker with custom indicator parameters + HMM regime detection."""
    try:
        ohlcv = _fetch_ohlcv(req.ticker, "2024-01-01", datetime.now().strftime("%Y-%m-%d"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {exc}") from exc

    if ohlcv.empty:
        raise HTTPException(status_code=404, detail=f"No data for {req.ticker}")

    try:
        df = ohlcv.xs(req.ticker, level="stock_code").copy()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Ticker {req.ticker} not found")

    close = df["close"]

    # Compute indicators with custom params
    rsi = _compute_rsi(close, req.rsi_period)
    macd_line, signal_line = _compute_macd(close, req.macd_fast, req.macd_slow)
    bb_upper, bb_lower, bb_mid = _compute_bollinger(close, req.bollinger_period, req.bollinger_std)
    bb_pctb = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

    # Build OHLCV + indicators response (last 120 days for charting)
    tail = min(120, len(close))
    dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in close.index[-tail:]]

    ohlcv_data = []
    for i in range(-tail, 0):
        row = df.iloc[i]
        ohlcv_data.append({
            "date": dates[i + tail],
            "open": round(float(row.get("open", 0)), 2),
            "high": round(float(row.get("high", 0)), 2),
            "low": round(float(row.get("low", 0)), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row.get("volume", 0)),
        })

    indicators = {
        "rsi": [round(float(v), 2) if not np.isnan(v) else None for v in rsi.iloc[-tail:]],
        "macd_line": [round(float(v), 4) if not np.isnan(v) else None for v in macd_line.iloc[-tail:]],
        "macd_signal": [round(float(v), 4) if not np.isnan(v) else None for v in signal_line.iloc[-tail:]],
        "bb_upper": [round(float(v), 2) if not np.isnan(v) else None for v in bb_upper.iloc[-tail:]],
        "bb_lower": [round(float(v), 2) if not np.isnan(v) else None for v in bb_lower.iloc[-tail:]],
        "bb_mid": [round(float(v), 2) if not np.isnan(v) else None for v in bb_mid.iloc[-tail:]],
        "bb_pctb": [round(float(v), 4) if not np.isnan(v) else None for v in bb_pctb.iloc[-tail:]],
    }

    # HMM regime detection
    regime = "unknown"
    regime_probs: dict[str, float] = {}
    try:
        from alpha_agent.models.features import compute_features
        from alpha_agent.models.hmm import HMMRegimeModel

        features = compute_features(ohlcv, req.ticker)
        if not features.empty and len(features) > 50:
            hmm = HMMRegimeModel()
            hmm = hmm.fit(features)
            state = hmm.predict(features)
            regime = state.current_regime
            regime_probs = state.regime_probabilities
    except Exception as exc:
        logger.warning("HMM regime detection failed: %s", exc)

    return {
        "ticker": req.ticker,
        "ohlcv": ohlcv_data,
        "indicators": indicators,
        "regime": regime,
        "regime_probabilities": regime_probs,
        "params": {
            "rsi_period": req.rsi_period,
            "macd_fast": req.macd_fast,
            "macd_slow": req.macd_slow,
            "bollinger_period": req.bollinger_period,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── POST /api/v1/ticker/search ─────────────────────────────────────────────


@router.post("/api/v1/ticker/search")
async def search_ticker(req: TickerSearchRequest) -> dict[str, Any]:
    """Search for US tickers by name or symbol."""
    query = req.query.upper()
    results = [
        t for t in _POPULAR_US_TICKERS
        if query in t["ticker"] or query in t["name"].upper()
    ]
    return {
        "query": req.query,
        "results": results[:10],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
