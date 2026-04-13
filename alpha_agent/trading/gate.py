"""Multi-timeframe trading gate — 4H trend + 1H momentum + 15M entry."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateScore:
    """Single timeframe gate result."""

    name: str
    timeframe: str
    score: float  # 0.0 - 1.0
    passed: bool
    description: str


@dataclass(frozen=True)
class GateResult:
    """Immutable aggregated gate result across all timeframes."""

    gates: list[GateScore]
    overall_confidence: float
    passed: bool
    signal_description: str


# Thresholds for each gate to "pass"
_GATE_THRESHOLD = 0.5


def evaluate_gates(ticker: str) -> GateResult:
    """Evaluate multi-timeframe gates for a ticker.

    Tries yfinance first (multi-timeframe), then AKShare daily fallback.
    """
    daily = pd.DataFrame()

    # ── Try yfinance (multi-timeframe) ───────────────────────────────
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        daily = tk.history(period="3mo", interval="1d")
        hourly = tk.history(period="5d", interval="1h")
        m15 = tk.history(period="5d", interval="15m")
        if not daily.empty:
            trend_score = _compute_trend_score(daily)
            momentum_score = _compute_momentum_score(hourly) if not hourly.empty else _estimate_momentum_from_daily(daily)
            entry_score = _compute_entry_score(m15) if not m15.empty else _estimate_entry_from_daily(daily)
            return _build_gate_result(trend_score, momentum_score, entry_score)
    except Exception:
        logger.info("yfinance unavailable for %s, trying AKShare.", ticker)

    # ── Fallback: AKShare daily (works from China) ───────────────────
    try:
        import akshare as ak
        raw = ak.stock_us_daily(symbol=ticker, adjust="qfq")
        if raw is not None and not raw.empty:
            daily = raw.tail(90).copy()
            daily = daily.rename(columns={"close": "Close", "open": "Open",
                                          "high": "High", "low": "Low",
                                          "volume": "Volume"})
            trend_score = _compute_trend_score(daily)
            momentum_score = _estimate_momentum_from_daily(daily)
            entry_score = _estimate_entry_from_daily(daily)
            return _build_gate_result(trend_score, momentum_score, entry_score)
    except Exception:
        logger.warning("AKShare fallback also failed for %s.", ticker, exc_info=True)

    return _default_gate_result()

    return _build_gate_result(trend_score, momentum_score, entry_score)


def _compute_trend_score(daily: pd.DataFrame) -> float:
    """4H trend approximation using EMA cross on daily data."""
    close = daily["Close"]
    if len(close) < 21:
        return 0.5

    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()

    # Score based on how far fast EMA is above slow EMA (normalized)
    diff = (ema_fast.iloc[-1] - ema_slow.iloc[-1]) / close.iloc[-1]
    return float(np.clip(0.5 + diff * 10, 0.0, 1.0))


def _compute_momentum_score(hourly: pd.DataFrame) -> float:
    """1H momentum via RSI on hourly data."""
    close = hourly["Close"]
    if len(close) < 14:
        return 0.5

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()

    rs = gain.iloc[-1] / max(loss.iloc[-1], 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Map RSI to 0-1 score: RSI 30→0.0, RSI 50→0.5, RSI 70→1.0
    return float(np.clip((rsi - 30) / 40, 0.0, 1.0))


def _compute_entry_score(m15: pd.DataFrame) -> float:
    """15M entry signal via MACD cross."""
    close = m15["Close"]
    if len(close) < 26:
        return 0.5

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    # Score based on MACD histogram (macd - signal)
    histogram = (macd.iloc[-1] - signal.iloc[-1]) / close.iloc[-1]
    return float(np.clip(0.5 + histogram * 50, 0.0, 1.0))


def _build_gate_result(trend_score: float, momentum_score: float, entry_score: float) -> GateResult:
    """Build a GateResult from three gate scores."""
    gates = [
        GateScore("4H Trend", "4H", trend_score, trend_score >= _GATE_THRESHOLD, "EMA(8) vs EMA(21) cross"),
        GateScore("1H Momentum", "1H", momentum_score, momentum_score >= _GATE_THRESHOLD, "RSI(14) momentum zone"),
        GateScore("15M Entry", "15M", entry_score, entry_score >= _GATE_THRESHOLD, "MACD signal cross"),
    ]
    weights = [0.4, 0.35, 0.25]
    scores = [g.score for g in gates]
    overall = sum(w * s for w, s in zip(weights, scores))
    all_passed = all(g.passed for g in gates)
    signal_desc = (
        f"{'All gates passed' if all_passed else 'Gate check incomplete'} — "
        f"Trend={trend_score:.0%}, Momentum={momentum_score:.0%}, Entry={entry_score:.0%}"
    )
    return GateResult(gates=gates, overall_confidence=overall, passed=all_passed, signal_description=signal_desc)


def _estimate_momentum_from_daily(daily: pd.DataFrame) -> float:
    """Estimate 1H momentum from daily data using RSI on daily close."""
    return _compute_momentum_score(daily)


def _estimate_entry_from_daily(daily: pd.DataFrame) -> float:
    """Estimate 15M entry signal from daily data using MACD on daily close."""
    return _compute_entry_score(daily)


def _default_gate_result() -> GateResult:
    """Fallback when data is unavailable."""
    gates = [
        GateScore("4H Trend", "4H", 0.5, False, "Data unavailable"),
        GateScore("1H Momentum", "1H", 0.5, False, "Data unavailable"),
        GateScore("15M Entry", "15M", 0.5, False, "Data unavailable"),
    ]
    return GateResult(
        gates=gates,
        overall_confidence=0.5,
        passed=False,
        signal_description="Market data unavailable — gates defaulted to neutral",
    )
