"""Serverless-mode routes — lightweight endpoints without ML dependencies.

Returns demo data matching v1 API contracts so the Next.js frontend
renders correctly on Vercel without pandas/numpy/scikit-learn.
Also provides legacy /api/dashboard for qcore_dashboard.html.
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


@router.get("/api/v1/system/config")
async def system_config(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "tickers": s.dashboard_tickers,
        "cache_ttl_seconds": s.dashboard_cache_ttl_seconds,
        "fastapi_port": 0,
        "llm_provider": s.llm_provider,
        "ollama_model": "",
        "max_iterations": s.max_iterations,
        "data_cache_max_age_hours": s.data_cache_max_age_hours,
        "mode": "serverless",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Services / Pipelines / Metrics  (frontend-specific)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/services/health")
async def services_health(request: Request) -> dict:
    llm_ok = False
    try:
        llm_ok = await request.app.state.llm.is_available()
    except Exception:
        pass
    return {
        "services": [
            {"name": "FastAPI", "status": "ok"},
            {"name": "LLM (Kimi)", "status": "ok" if llm_ok else "degraded"},
            {"name": "ML Pipeline", "status": "offline (serverless)"},
        ],
        "overall": "degraded",
    }


@router.get("/api/v1/pipelines/latency")
async def pipeline_latency() -> dict:
    return {
        "stages": [
            {"name": "data_fetch", "p50_ms": 120, "p99_ms": 350},
            {"name": "feature_compute", "p50_ms": 45, "p99_ms": 110},
            {"name": "model_inference", "p50_ms": 80, "p99_ms": 200},
            {"name": "gate_evaluation", "p50_ms": 15, "p99_ms": 40},
            {"name": "llm_decision", "p50_ms": 900, "p99_ms": 2500},
        ],
        "total_p50_ms": 1160,
        "total_p99_ms": 3200,
    }


@router.get("/api/v1/metrics/throughput")
async def throughput() -> dict:
    return {
        "requests_per_minute": 0,
        "decisions_today": 0,
        "cache_hit_rate": 0.0,
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


@router.get("/api/v1/market/indicators/{ticker}")
async def market_indicators(ticker: str) -> dict:
    return {"ticker": ticker, "indicators": [], "ohlcv_recent": []}


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

@router.get("/api/v1/features/state")
async def features_state() -> list:
    return []


@router.get("/api/v1/features/stats/{ticker}")
async def features_stats(ticker: str) -> dict:
    return {"ticker": ticker, "stats": []}


# ═══════════════════════════════════════════════════════════════════════════
# Alpha
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/alpha/signals")
async def alpha_signals() -> list:
    return []


@router.get("/api/v1/alpha/factors")
async def alpha_factors() -> list:
    return []


@router.get("/api/v1/alpha/factors/summary")
async def alpha_factors_summary() -> dict:
    return {"total_factors": 0, "avg_ic": None, "avg_sharpe": None, "pipeline_status": {"state": "idle"}}


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/portfolio/positions")
async def portfolio_positions() -> list:
    return []


@router.get("/api/v1/portfolio/risk")
async def portfolio_risk() -> dict:
    return {
        "risk_metrics": {
            "total_exposure": 0.0, "max_single_position": 0.0,
            "diversification_score": 0.0, "var_95": None, "realized_volatility": None,
        },
        "positions": [],
        "backtest_summary": {},
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orders
# ═══════════════════════════════════════════════════════════════════════════

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

@router.get("/api/v1/gateway/status")
async def gateway_status(request: Request) -> dict:
    s = request.app.state.settings
    return {
        "ticker": s.dashboard_tickers[0] if s.dashboard_tickers else "NVDA",
        "gates": [],
        "overall_confidence": 0.0,
        "passed": False,
        "signal_description": "Gate evaluation requires ML pipeline",
    }


@router.get("/api/v1/gateway/rules")
async def gateway_rules() -> list:
    return [
        {"name": "4H Trend Alignment", "description": "4h trend aligns with prediction", "enabled": True, "threshold": 0.6},
        {"name": "1H Momentum", "description": "1h momentum confirmation", "enabled": True, "threshold": 0.5},
        {"name": "15M Entry Signal", "description": "15m entry timing", "enabled": True, "threshold": 0.55},
        {"name": "Volume Filter", "description": "Minimum volume threshold", "enabled": True, "threshold": 1.5},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Audit
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/audit/events")
async def audit_events() -> list:
    return []


@router.get("/api/v1/audit/decisions")
async def audit_decisions() -> dict:
    return {"decisions": [], "total": 0}


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
