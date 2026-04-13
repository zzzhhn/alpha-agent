"""Serverless-mode routes — lightweight endpoints without ML dependencies.

Returns demo data matching the Next.js frontend TypeScript interfaces
(see frontend/src/lib/types.ts) so every page renders correctly on
Vercel without pandas/numpy/scikit-learn.
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter(tags=["serverless"])

_START = time.monotonic()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# System
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/system/health")
async def system_health(request: Request) -> dict:
    llm_status = "unknown"
    try:
        llm = request.app.state.llm
        llm_status = "ok" if await llm.is_available() else "unreachable"
    except Exception:
        llm_status = "error"
    return {
        "services": {"llm": llm_status, "fastapi": "ok", "tunnel": "n/a"},
        "models": {"trained": False, "last_trained": None, "model_files": []},
        "system": {
            "uptime_seconds": round(time.monotonic() - _START, 1),
            "python_version": sys.version,
            "platform": platform.platform(),
            "mode": "serverless",
        },
        "cache_stats": {"ttl_seconds": 300},
    }


# SystemConfig: api_calls_24h, cache_hit_rate, avg_latency_ms, error_count_24h, alerts[]
@router.get("/api/v1/system/config")
async def system_config(request: Request) -> dict:
    return {
        "api_calls_24h": 0,
        "cache_hit_rate": 0.0,
        "avg_latency_ms": 0,
        "error_count_24h": 0,
        "alerts": [
            {
                "timestamp": _now_iso(),
                "severity": "INFO",
                "service": "system",
                "message": "Running in serverless mode — ML pipeline offline",
            }
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Services / Pipelines / Metrics  (frontend-specific)
# ═══════════════════════════════════════════════════════════════════════════

# ServiceHealthResponse: { services: ServiceHealth[], timestamp }
# ServiceHealth: { service_id, status, latency_p95_ms, uptime_pct_24h, last_check_at, last_error_at }
@router.get("/api/v1/services/health")
async def services_health(request: Request) -> dict:
    now = _now_iso()
    llm_ok = False
    try:
        llm_ok = await request.app.state.llm.is_available()
    except Exception:
        pass
    return {
        "services": [
            {
                "service_id": "fastapi",
                "status": "green",
                "latency_p95_ms": 45,
                "uptime_pct_24h": 99.9,
                "last_check_at": now,
                "last_error_at": None,
            },
            {
                "service_id": "llm_kimi",
                "status": "green" if llm_ok else "yellow",
                "latency_p95_ms": 900,
                "uptime_pct_24h": 95.0 if llm_ok else 0.0,
                "last_check_at": now,
                "last_error_at": None if llm_ok else now,
            },
            {
                "service_id": "ml_pipeline",
                "status": "red",
                "latency_p95_ms": 0,
                "uptime_pct_24h": 0.0,
                "last_check_at": now,
                "last_error_at": now,
            },
        ],
        "timestamp": now,
    }


# PipelineLatency: { segments: LatencySegment[], total_ms, timestamp }
# LatencySegment: { stage, latency_ms, percentage }
@router.get("/api/v1/pipelines/latency")
async def pipeline_latency() -> dict:
    segments = [
        {"stage": "data_fetch", "latency_ms": 120, "percentage": 10.3},
        {"stage": "feature_compute", "latency_ms": 45, "percentage": 3.9},
        {"stage": "model_inference", "latency_ms": 80, "percentage": 6.9},
        {"stage": "gate_evaluation", "latency_ms": 15, "percentage": 1.3},
        {"stage": "llm_decision", "latency_ms": 900, "percentage": 77.6},
    ]
    return {
        "segments": segments,
        "total_ms": 1160,
        "timestamp": _now_iso(),
    }


# ThroughputMetrics: { tickers_per_sec, trades_per_sec, features_per_sec, timestamp }
@router.get("/api/v1/metrics/throughput")
async def throughput() -> dict:
    return {
        "tickers_per_sec": 0.0,
        "trades_per_sec": 0.0,
        "features_per_sec": 0.0,
        "timestamp": _now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Market
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/market/state")
async def market_state() -> dict:
    return {
        "current_regime": "Unknown",
        "current_regime_zh": "未知（Serverless）",
        "regime_probabilities": {},
        "transition_probability": 0.0,
        "model_scores": {},
        "source": "serverless — ML pipeline offline",
    }


# MarketIndicators: { ticker, rsi, macd, bollinger_pct_b, volatility, log_return, timestamp }
@router.get("/api/v1/market/indicators/{ticker}")
async def market_indicators(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "rsi": 50.0,
        "macd": 0.0,
        "bollinger_pct_b": 0.5,
        "volatility": 0.0,
        "log_return": 0.0,
        "timestamp": _now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Inference
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/inference/predict")
async def inference_predict() -> dict:
    return {
        "assets": [],
        "fusion": {"direction": "N/A", "confidence": 0, "bull_prob": 0.5},
        "source": "serverless — ML models not loaded",
    }


@router.get("/api/v1/inference/models")
async def inference_models() -> dict:
    return {
        "models": [
            {"name": "HMM", "trained": False, "description": "Regime detection"},
            {"name": "XGBoost", "trained": False, "description": "Direction prediction"},
            {"name": "LSTM/MLP", "trained": False, "description": "Direction prediction"},
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# Features
# ═══════════════════════════════════════════════════════════════════════════

# FeatureState: { features: string[], tickers: string[], heatmap: number[][], timestamp }
@router.get("/api/v1/features/state")
async def features_state() -> dict:
    tickers = ["NVDA", "AAPL", "TSLA"]
    features = ["RSI_14", "MACD_signal", "BB_%B", "Log_Return", "Volatility_20d"]
    heatmap = [
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    return {
        "features": features,
        "tickers": tickers,
        "heatmap": heatmap,
        "timestamp": _now_iso(),
    }


@router.get("/api/v1/features/stats/{ticker}")
async def features_stats(ticker: str) -> dict:
    return {"ticker": ticker, "stats": []}


# ═══════════════════════════════════════════════════════════════════════════
# Alpha
# ═══════════════════════════════════════════════════════════════════════════

# AlphaSignal[]: { ticker, score, direction, confidence, sources }
@router.get("/api/v1/alpha/signals")
async def alpha_signals() -> list:
    return []


# AlphaFactor[]: { id, expression, ic, icir, sharpe, status, created_at }
@router.get("/api/v1/alpha/factors")
async def alpha_factors() -> list:
    return []


# AlphaFactorSummary: { best_ic, best_sharpe, total_factors, pipeline_status }
@router.get("/api/v1/alpha/factors/summary")
async def alpha_factors_summary() -> dict:
    return {
        "best_ic": 0.0,
        "best_sharpe": 0.0,
        "total_factors": 0,
        "pipeline_status": "idle",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════════════════════════════

# Position[]: { ticker, quantity, avg_price, current_price, pnl, pnl_pct, weight }
@router.get("/api/v1/portfolio/positions")
async def portfolio_positions() -> list:
    return []


# PortfolioRisk: { total_exposure, diversification_score, max_position_pct,
#   var_95, sharpe_ratio, max_drawdown, beta, timestamp }
@router.get("/api/v1/portfolio/risk")
async def portfolio_risk() -> dict:
    return {
        "total_exposure": 0.0,
        "diversification_score": 0.0,
        "max_position_pct": 0.0,
        "var_95": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "beta": 0.0,
        "timestamp": _now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orders
# ═══════════════════════════════════════════════════════════════════════════

# Order[]: { order_id, ticker, side, quantity, price, status, filled_quantity, timestamp }
@router.get("/api/v1/orders")
async def orders_list() -> list:
    return []


@router.get("/api/v1/orders/pending")
async def orders_pending() -> list:
    return []


@router.get("/api/v1/orders/history")
async def orders_history() -> list:
    return []


# ═══════════════════════════════════════════════════════════════════════════
# Gateway
# ═══════════════════════════════════════════════════════════════════════════

# GatewayStatus: { gates_passed, gates_failed, overall_confidence,
#   signal_description, rules: GateRule[], timestamp }
# GateRule: { name, enabled, passed, confidence, reason }
@router.get("/api/v1/gateway/status")
async def gateway_status(request: Request) -> dict:
    rules = [
        {"name": "4H Trend Alignment", "enabled": True, "passed": False, "confidence": 0.0, "reason": "ML pipeline offline"},
        {"name": "1H Momentum", "enabled": True, "passed": False, "confidence": 0.0, "reason": "ML pipeline offline"},
        {"name": "15M Entry Signal", "enabled": True, "passed": False, "confidence": 0.0, "reason": "ML pipeline offline"},
        {"name": "Volume Filter", "enabled": True, "passed": False, "confidence": 0.0, "reason": "ML pipeline offline"},
    ]
    return {
        "gates_passed": 0,
        "gates_failed": 4,
        "overall_confidence": 0.0,
        "signal_description": "Gate evaluation requires ML pipeline",
        "rules": rules,
        "timestamp": _now_iso(),
    }


# GateRule[]: { name, enabled, passed, confidence, reason }
@router.get("/api/v1/gateway/rules")
async def gateway_rules() -> list:
    return [
        {"name": "4H Trend Alignment", "enabled": True, "passed": False, "confidence": 0.0, "reason": "Requires ML pipeline"},
        {"name": "1H Momentum", "enabled": True, "passed": False, "confidence": 0.0, "reason": "Requires ML pipeline"},
        {"name": "15M Entry Signal", "enabled": True, "passed": False, "confidence": 0.0, "reason": "Requires ML pipeline"},
        {"name": "Volume Filter", "enabled": True, "passed": False, "confidence": 0.0, "reason": "Requires ML pipeline"},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Audit
# ═══════════════════════════════════════════════════════════════════════════

# AuditEvent[]: complex type — return empty array (frontend handles empty)
@router.get("/api/v1/audit/events")
async def audit_events() -> list:
    return []


@router.get("/api/v1/audit/events/{event_id}/raw")
async def audit_event_raw(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "timestamp": _now_iso(),
        "event_type": "unknown",
        "user_id": "system",
        "ticker": "N/A",
        "side": "BUY",
        "quantity": 0,
        "order_price": 0.0,
        "fill_price": 0.0,
        "fill_quantity": 0,
        "decision_chain_id": "",
        "regime_state": {"current_regime": "Unknown", "probability": 0.0},
        "risk_assessment": {"var_impact_bps": 0.0, "concentration_impact": 0.0},
        "execution_latency_ms": 0,
        "slippage_bps": 0.0,
        "tags": [],
    }


# AuditSummary: { total_decisions, acceptance_rate, avg_confidence, last_decision_time, decisions[] }
@router.get("/api/v1/audit/decisions")
async def audit_decisions() -> dict:
    return {
        "total_decisions": 0,
        "acceptance_rate": 0.0,
        "avg_confidence": 0.0,
        "last_decision_time": _now_iso(),
        "decisions": [],
    }


@router.get("/api/v1/audit/log")
async def audit_log() -> dict:
    return {"entries": [], "total_entries": 0, "filters": {}}


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard (v1 + legacy /api/dashboard for qcore_dashboard.html)
# ═══════════════════════════════════════════════════════════════════════════

def _dashboard_payload(tickers: list[str]) -> dict:
    primary = tickers[0] if tickers else "NVDA"
    return {
        "market_state": {
            "current_regime": "Unknown",
            "current_regime_zh": "未知",
            "regime_probabilities": {},
            "transition_probability": 0.0,
            "model_scores": {},
            "source": "serverless — ML pipeline offline",
        },
        "inference": {"assets": [], "consensus_direction": "N/A", "consensus_confidence": 0},
        "gate": {
            "ticker": primary, "gates": [],
            "overall_confidence": 0.0, "passed": False,
            "signal_description": "Serverless mode",
        },
        "decision": {
            "ticker": primary, "direction": "N/A", "confidence": 0.0,
            "position_size_pct": 0.0,
            "reasoning": "ML pipeline not available in serverless. Switch to full deployment for live inference.",
            "summary": "Serverless — LLM available, ML models offline",
        },
        "model_voting": [],
        "meta": {"tickers": tickers, "compute_time_ms": 0, "cached": False, "mode": "serverless"},
    }


@router.get("/api/v1/dashboard/summary")
async def dashboard_summary(request: Request) -> dict:
    return _dashboard_payload(request.app.state.settings.dashboard_tickers)


@router.get("/api/dashboard")
async def legacy_dashboard(request: Request) -> dict:
    return _dashboard_payload(request.app.state.settings.dashboard_tickers)


# ═══════════════════════════════════════════════════════════════════════════
# Data Quality
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/data/quality/{ticker}")
async def data_quality(ticker: str) -> dict:
    return {"ticker": ticker, "total_rows": 0, "rules": [], "overall_pass": False}
