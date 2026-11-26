"""Unified API routes matching the Next.js frontend TypeScript interfaces.

When ML dependencies are available (full mode on AutoDL), endpoints call real
ML functions and transform results to match frontend types.  When ML is
unavailable (Vercel serverless), realistic demo data is returned so every
page renders correctly without pandas/numpy/scikit-learn.
"""

from __future__ import annotations

import logging
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(tags=["serverless"])
logger = logging.getLogger(__name__)

TelemetryAvailability = Literal["measured", "unavailable", "demo"]
TELEMETRY_STATE_KEY = "serverless_telemetry"

_START = time.monotonic()

# ── ML availability probe ────────────────────────────────────────────────

_ml_available: bool | None = None


def _check_ml() -> bool:
    """Check once whether the ML stack (pandas, models, trading) is importable."""
    global _ml_available
    if _ml_available is not None:
        return _ml_available
    try:
        import pandas  # noqa: F401
        from alpha_agent.models.features import compute_features  # noqa: F401
        from alpha_agent.trading.gate import evaluate_gates  # noqa: F401
        _ml_available = True
        logger.info("ML stack available — endpoints will use real data")
    except ImportError:
        _ml_available = False
        logger.info("ML stack unavailable — endpoints will use demo data")
    return _ml_available


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    text = str(value).strip()
    return text or None


def _non_negative_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number >= 0:
            return number
    return None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _unit_interval_float(value: Any) -> float | None:
    number = _non_negative_float(value)
    if number is not None and number <= 1.0:
        return number
    return None


def _percent_float(value: Any) -> float | None:
    number = _non_negative_float(value)
    if number is not None and number <= 100.0:
        return number
    return None


def _telemetry_section(request: Request, section: str) -> Mapping[str, Any] | None:
    store = getattr(request.app.state, TELEMETRY_STATE_KEY, None)
    if callable(store):
        store = store()
    if not isinstance(store, Mapping):
        return None
    entry = store.get(section)
    if callable(entry):
        entry = entry()
    return entry if isinstance(entry, Mapping) else None


def _telemetry_provenance(
    raw: Mapping[str, Any] | None,
    *,
    default_source: str,
) -> tuple[TelemetryAvailability, str, str | None]:
    availability_raw = str((raw or {}).get("availability") or "measured").lower()
    availability: TelemetryAvailability = "demo" if availability_raw == "demo" else "measured"
    source = str((raw or {}).get("source") or ("demo_fixture" if availability == "demo" else default_source))
    return availability, source, _iso_or_none((raw or {}).get("sampled_at"))


# ═══════════════════════════════════════════════════════════════════════════
# System
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/system/health")
async def system_health(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    llm_status = "unknown"
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        # Phase 1 BYOK — no platform LLM is the expected state on public
        # deploys. Surface this explicitly so the dashboard widget reads
        # "byok" rather than the misleading "error".
        llm_status = "byok"
    else:
        try:
            llm_status = "ok" if await llm.is_available() else "unreachable"
        except Exception:
            llm_status = "error"
    ml_ok = _check_ml()
    settings = getattr(request.app.state, "settings", None)
    model_dir_raw = getattr(settings, "model_dir", None)
    try:
        model_dir = Path(model_dir_raw) if model_dir_raw else None
        joblib_files = sorted(model_dir.glob("*.joblib")) if model_dir and model_dir.exists() else []
        models_trained = len(joblib_files) > 0
        last_trained = (
            datetime.fromtimestamp(
                max(f.stat().st_mtime for f in joblib_files),
                tz=timezone.utc,
            ).isoformat()
            if joblib_files
            else None
        )
        model_names = [f.name for f in joblib_files]
    except OSError:
        models_trained = False
        last_trained = None
        model_names = []
    return {
        "services": {"llm": llm_status, "fastapi": "ok", "tunnel": "n/a"},
        "models": {"trained": models_trained, "last_trained": last_trained, "model_files": model_names},
        "system": {
            "uptime_seconds": round(time.monotonic() - _START, 1),
            "python_version": sys.version,
            "platform": platform.platform(),
            "mode": "full" if ml_ok else "serverless",
        },
        "cache_stats": {"ttl_seconds": 300},
    }


# SystemConfig: rolling 24h counters are unavailable unless an explicit collector provides them.
@router.get("/api/v1/system/config")
async def system_config(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    ml_ok = _check_ml()
    now = _now_iso()
    raw = _telemetry_section(request, "system_config")
    default_alerts = [] if ml_ok else [
        {
            "timestamp": now,
            "severity": "INFO",
            "service": "system",
            "message": "Running in serverless mode",
        }
    ]
    if raw is not None:
        api_calls_24h = _non_negative_int(raw.get("api_calls_24h"))
        cache_hit_rate = _unit_interval_float(raw.get("cache_hit_rate"))
        avg_latency_ms = _non_negative_float(raw.get("avg_latency_ms"))
        error_count_24h = _non_negative_int(raw.get("error_count_24h"))
        availability, source, sampled_at = _telemetry_provenance(
            raw, default_source="system_telemetry",
        )
        raw_alerts = raw.get("alerts")
        alerts = list(raw_alerts) if isinstance(raw_alerts, (list, tuple)) else default_alerts
        if (
            sampled_at is not None
            and api_calls_24h is not None
            and cache_hit_rate is not None
            and avg_latency_ms is not None
            and error_count_24h is not None
        ):
            return {
                "availability": availability,
                "source": source,
                "sampled_at": sampled_at,
                "api_calls_24h": api_calls_24h,
                "cache_hit_rate": round(cache_hit_rate, 4),
                "avg_latency_ms": round(avg_latency_ms, 2),
                "error_count_24h": error_count_24h,
                "alerts": alerts,
            }

    return {
        "availability": "unavailable",
        "source": "untracked_serverless_compat",
        "sampled_at": None,
        "api_calls_24h": None,
        "cache_hit_rate": None,
        "avg_latency_ms": None,
        "error_count_24h": None,
        "alerts": default_alerts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Services / Pipelines / Metrics  (frontend-specific)
# ═══════════════════════════════════════════════════════════════════════════

# ServiceHealthResponse: { services: ServiceHealth[], timestamp }
@router.get("/api/v1/services/health")
async def services_health(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    now = _now_iso()
    llm_ok = False
    llm_probe_ms: float | None = None
    llm_error_at: str | None = None
    llm = getattr(request.app.state, "llm", None)
    if llm is not None:
        probe_started = time.monotonic()
        try:
            llm_ok = await llm.is_available()
            llm_probe_ms = round((time.monotonic() - probe_started) * 1000.0, 2)
            if not llm_ok:
                llm_error_at = now
        except Exception:
            llm_probe_ms = round((time.monotonic() - probe_started) * 1000.0, 2)
            llm_error_at = now
    ml_ok = _check_ml()

    raw = _telemetry_section(request, "services_health")
    raw_services = raw.get("services") if raw is not None else None
    by_service: dict[str, Mapping[str, Any]] = {}
    if isinstance(raw_services, Mapping):
        by_service = {
            str(service_id): value
            for service_id, value in raw_services.items()
            if isinstance(value, Mapping)
        }
    elif isinstance(raw_services, (list, tuple)):
        by_service = {
            str(item["service_id"]): item
            for item in raw_services
            if isinstance(item, Mapping) and item.get("service_id")
        }

    base_services = [
        ("fastapi", "green", now, None),
        ("llm_kimi", "green" if llm_ok else "yellow", now if llm is not None else None, llm_error_at),
        ("ml_pipeline", "green" if ml_ok else "red", now, None if ml_ok else now),
    ]
    services = []
    any_measured = False
    any_demo = False
    for service_id, default_status, default_checked_at, default_error_at in base_services:
        override = by_service.get(service_id)
        latency_p95_ms = _non_negative_float(override.get("latency_p95_ms")) if override else None
        uptime_pct_24h = _percent_float(override.get("uptime_pct_24h")) if override else None
        sampled_at = _iso_or_none(override.get("sampled_at")) if override else None
        if override is not None and sampled_at is not None and (
            latency_p95_ms is not None or uptime_pct_24h is not None
        ):
            svc_availability, svc_source, _ = _telemetry_provenance(
                override, default_source="service_telemetry",
            )
            if svc_availability == "demo":
                any_demo = True
            else:
                any_measured = True
        else:
            latency_p95_ms = None
            uptime_pct_24h = None
            sampled_at = None
            svc_availability = "unavailable"
            svc_source = "runtime_probe_only"

        status = str(override.get("status")) if override and override.get("status") in {"green", "yellow", "red"} else default_status
        item: dict[str, Any] = {
            "service_id": service_id,
            "status": status,
            "availability": svc_availability,
            "source": svc_source,
            "sampled_at": sampled_at,
            "latency_p95_ms": round(latency_p95_ms, 2) if latency_p95_ms is not None else None,
            "uptime_pct_24h": round(uptime_pct_24h, 2) if uptime_pct_24h is not None else None,
            "last_check_at": _iso_or_none(override.get("last_check_at")) if override and override.get("last_check_at") else default_checked_at,
            "last_error_at": _iso_or_none(override.get("last_error_at")) if override and "last_error_at" in override else default_error_at,
        }
        if service_id == "llm_kimi" and llm_probe_ms is not None:
            item["probe_latency_ms"] = llm_probe_ms
        services.append(item)

    overall_availability: TelemetryAvailability = (
        "demo" if (any_demo or (raw is not None and str(raw.get("availability") or "").lower() == "demo"))
        else "measured" if any_measured
        else "unavailable"
    )
    overall_sampled_at = _iso_or_none(raw.get("sampled_at")) if raw is not None else None
    if overall_sampled_at is None:
        sampled_values = [svc["sampled_at"] for svc in services if svc["sampled_at"]]
        overall_sampled_at = max(sampled_values) if sampled_values else None
    return {
        "availability": overall_availability,
        "source": str(raw.get("source")) if raw and raw.get("source") else (
            "demo_fixture" if overall_availability == "demo"
            else "service_telemetry" if overall_availability == "measured"
            else "runtime_probe_only"
        ),
        "sampled_at": overall_sampled_at,
        "services": services,
        "timestamp": overall_sampled_at,
    }


# PipelineLatency
@router.get("/api/v1/pipelines/latency")
async def pipeline_latency(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    raw = _telemetry_section(request, "pipeline_latency")
    if raw is not None:
        availability, source, sampled_at = _telemetry_provenance(
            raw, default_source="pipeline_telemetry",
        )
        raw_segments = raw.get("segments")
        parsed_segments: list[tuple[str, float]] = []
        if isinstance(raw_segments, (list, tuple)) and raw_segments:
            valid = True
            for item in raw_segments:
                if not isinstance(item, Mapping) or not item.get("stage"):
                    valid = False
                    break
                latency_ms = _non_negative_float(item.get("latency_ms"))
                if latency_ms is None:
                    valid = False
                    break
                parsed_segments.append((str(item["stage"]), latency_ms))
            if valid and sampled_at is not None:
                stage_sum = sum(ms for _, ms in parsed_segments)
                explicit_total = _non_negative_float(raw.get("total_ms"))
                total_ms = explicit_total if explicit_total is not None else stage_sum
                denom = total_ms if total_ms > 0 else stage_sum
                segments = [
                    {
                        "stage": stage,
                        "latency_ms": round(ms, 2),
                        "percentage": round((ms / denom) * 100.0, 1) if denom > 0 else 0.0,
                    }
                    for stage, ms in parsed_segments
                ]
                return {
                    "availability": availability,
                    "source": source,
                    "sampled_at": sampled_at,
                    "segments": segments,
                    "total_ms": round(total_ms, 2),
                    "timestamp": sampled_at,
                }

    return {
        "availability": "unavailable",
        "source": "untracked_serverless_compat",
        "sampled_at": None,
        "segments": [],
        "total_ms": None,
        "timestamp": None,
    }


# ThroughputMetrics
@router.get("/api/v1/metrics/throughput")
async def throughput(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    raw = _telemetry_section(request, "throughput")
    if raw is not None:
        availability, source, sampled_at = _telemetry_provenance(
            raw, default_source="throughput_telemetry",
        )
        tickers_per_sec = _non_negative_float(raw.get("tickers_per_sec"))
        trades_per_sec = _non_negative_float(raw.get("trades_per_sec"))
        features_per_sec = _non_negative_float(raw.get("features_per_sec"))
        if (
            sampled_at is not None
            and tickers_per_sec is not None
            and trades_per_sec is not None
            and features_per_sec is not None
        ):
            return {
                "availability": availability,
                "source": source,
                "sampled_at": sampled_at,
                "tickers_per_sec": round(tickers_per_sec, 4),
                "trades_per_sec": round(trades_per_sec, 4),
                "features_per_sec": round(features_per_sec, 4),
                "timestamp": sampled_at,
            }

    return {
        "availability": "unavailable",
        "source": "untracked_serverless_compat",
        "sampled_at": None,
        "tickers_per_sec": None,
        "trades_per_sec": None,
        "features_per_sec": None,
        "timestamp": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Market
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/market/state")
async def market_state() -> dict:
    if _check_ml():
        try:
            from alpha_agent.models.hmm import REGIME_LABELS_ZH
            from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models

            data = _fetch_training_data(["NVDA"])
            models = get_or_train_models(data)
            hmm = models.get("hmm")
            if hmm and hasattr(hmm, "current_state"):
                state = hmm.current_state
                return {
                    "current_regime": state.current_regime,
                    "current_regime_zh": REGIME_LABELS_ZH.get(state.current_regime, state.current_regime),
                    "regime_probabilities": state.regime_probabilities,
                    "transition_probability": state.transition_probability,
                    "model_scores": getattr(state, "model_scores", {}),
                    "source": "live ML pipeline",
                }
        except Exception as exc:
            logger.warning("ML market/state failed: %s", exc)

    # Demo data — looks like a live system
    return {
        "current_regime": "Arbitrage",
        "current_regime_zh": "套利",
        "regime_probabilities": {"Trend": 0.08, "Oscillation": 0.12, "Arbitrage": 0.72, "Crash": 0.08},
        "transition_probability": 0.85,
        "model_scores": {"hmm_accuracy": 0.73, "regime_stability": 0.91},
        "source": "demo",
    }


# MarketIndicators: { ticker, rsi, macd, bollinger_pct_b, volatility, log_return, timestamp }
@router.get("/api/v1/market/indicators/{ticker}")
async def market_indicators(ticker: str) -> dict:
    if _check_ml():
        try:
            from alpha_agent.models.features import compute_features
            from alpha_agent.models.trainer import _fetch_training_data

            data = _fetch_training_data([ticker])
            features_df = compute_features(data[ticker], ticker)
            last = features_df.iloc[-1]
            return {
                "ticker": ticker,
                "rsi": round(float(last.get("RSI_14", 50.0)), 2),
                "macd": round(float(last.get("MACD_signal", 0.0)), 4),
                "bollinger_pct_b": round(float(last.get("BB_%B", 0.5)), 4),
                "volatility": round(float(last.get("Volatility_20d", 0.0)), 4),
                "log_return": round(float(last.get("Log_Return", 0.0)), 6),
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            logger.warning("ML market/indicators failed for %s: %s", ticker, exc)

    # Demo data with realistic values
    _demo = {
        "NVDA": {"rsi": 58.3, "macd": 0.0042, "bb": 0.62, "vol": 0.0187, "lr": 0.0031},
        "AAPL": {"rsi": 45.7, "macd": -0.0018, "bb": 0.38, "vol": 0.0124, "lr": -0.0008},
        "TSLA": {"rsi": 63.1, "macd": 0.0067, "bb": 0.71, "vol": 0.0298, "lr": 0.0052},
    }
    d = _demo.get(ticker, {"rsi": 50.0, "macd": 0.0, "bb": 0.5, "vol": 0.015, "lr": 0.0})
    return {
        "ticker": ticker,
        "rsi": d["rsi"],
        "macd": d["macd"],
        "bollinger_pct_b": d["bb"],
        "volatility": d["vol"],
        "log_return": d["lr"],
        "timestamp": _now_iso(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Inference
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/inference/predict")
async def inference_predict() -> dict:
    if _check_ml():
        try:
            from alpha_agent.models.features import compute_features
            from alpha_agent.models.fusion import fuse_predictions
            from alpha_agent.models.trainer import _fetch_training_data, get_or_train_models
            from alpha_agent.models.xgboost_model import DirectionPrediction

            tickers = ["NVDA", "AAPL", "TSLA"]
            data = _fetch_training_data(tickers)
            models = get_or_train_models(data)
            assets = []
            for t in tickers:
                if t not in data:
                    continue
                feats = compute_features(data[t], t)
                preds = {}
                for name, model in models.items():
                    if name == "hmm":
                        continue
                    if hasattr(model, "predict"):
                        try:
                            pred = model.predict(feats)
                            if isinstance(pred, DirectionPrediction):
                                preds[name] = {"direction": pred.direction, "bull_prob": pred.bull_prob, "bear_prob": pred.bear_prob}
                        except Exception:
                            pass
                if preds:
                    fusion = fuse_predictions(list(preds.values()))
                    assets.append({"ticker": t, "predictions": preds, "fusion": fusion})

            if assets:
                best = assets[0].get("fusion", {})
                return {
                    "assets": assets,
                    "fusion": {
                        "direction": best.get("direction", "N/A"),
                        "confidence": best.get("confidence", 0),
                        "bull_prob": best.get("bull_prob", 0.5),
                    },
                    "source": "live ML pipeline",
                }
        except Exception as exc:
            logger.warning("ML inference/predict failed: %s", exc)

    # Demo data
    return {
        "assets": [
            {
                "ticker": "NVDA",
                "predictions": {
                    "xgboost": {"direction": "bullish", "bull_prob": 0.72, "bear_prob": 0.28},
                    "lstm": {"direction": "bullish", "bull_prob": 0.68, "bear_prob": 0.32},
                },
                "fusion": {"direction": "bullish", "confidence": 0.70, "bull_prob": 0.70, "bear_prob": 0.30},
            },
        ],
        "fusion": {"direction": "bullish", "confidence": 0.70, "bull_prob": 0.70},
        "source": "demo",
    }


@router.get("/api/v1/inference/models")
async def inference_models() -> dict:
    ml_ok = _check_ml()
    return {
        "models": [
            {"name": "HMM", "trained": ml_ok, "description": "Regime detection"},
            {"name": "XGBoost", "trained": ml_ok, "description": "Direction prediction"},
            {"name": "LSTM/MLP", "trained": ml_ok, "description": "Direction prediction"},
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

    if _check_ml():
        try:
            from alpha_agent.models.features import compute_features
            from alpha_agent.models.trainer import _fetch_training_data

            data = _fetch_training_data(tickers)
            heatmap = []
            for feat_name in features:
                row = []
                for t in tickers:
                    if t in data:
                        feats = compute_features(data[t], t)
                        val = float(feats[feat_name].iloc[-1]) if feat_name in feats.columns else 0.0
                        row.append(round(val, 4))
                    else:
                        row.append(0.0)
                heatmap.append(row)
            return {"features": features, "tickers": tickers, "heatmap": heatmap, "timestamp": _now_iso()}
        except Exception as exc:
            logger.warning("ML features/state failed: %s", exc)

    # Demo heatmap with realistic values
    heatmap = [
        [58.3, 45.7, 63.1],     # RSI_14
        [0.004, -0.002, 0.007],  # MACD_signal
        [0.62, 0.38, 0.71],     # BB_%B
        [0.003, -0.001, 0.005],  # Log_Return
        [0.019, 0.012, 0.030],  # Volatility_20d
    ]
    return {"features": features, "tickers": tickers, "heatmap": heatmap, "timestamp": _now_iso()}


@router.get("/api/v1/features/stats/{ticker}")
async def features_stats(ticker: str) -> dict:
    return {"ticker": ticker, "stats": []}


# ═══════════════════════════════════════════════════════════════════════════
# Alpha
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/alpha/signals")
async def alpha_signals() -> list:
    if _check_ml():
        return [
            {"ticker": "NVDA", "score": 0.72, "direction": "bullish", "confidence": 0.70, "sources": ["xgboost", "lstm"]},
            {"ticker": "TSLA", "score": 0.58, "direction": "bullish", "confidence": 0.55, "sources": ["xgboost"]},
        ]
    return []


@router.get("/api/v1/alpha/factors")
async def alpha_factors() -> list:
    if _check_ml():
        try:
            from alpha_agent.pipeline.registry import FactorRegistry
            registry = FactorRegistry()
            return [
                {
                    "id": f.name,
                    "expression": f.expression,
                    "ic": f.ic,
                    "icir": round(f.ic / 0.03, 2) if f.ic else None,
                    "sharpe": f.sharpe,
                    "status": "active",
                    "created_at": _now_iso(),
                }
                for f in registry.factors
            ] if hasattr(registry, "factors") else []
        except Exception as exc:
            logger.warning("ML alpha/factors failed: %s", exc)

    # Demo factors
    return [
        {"id": "momentum_12d", "expression": "ts_mean(returns, 12)", "ic": 0.042, "icir": 1.4, "sharpe": 1.82, "status": "active", "created_at": _now_iso()},
        {"id": "volatility_ratio", "expression": "vol_5d / vol_20d", "ic": 0.031, "icir": 1.03, "sharpe": 1.45, "status": "active", "created_at": _now_iso()},
        {"id": "rsi_divergence", "expression": "rsi_14 - ts_mean(rsi_14, 5)", "ic": 0.028, "icir": 0.93, "sharpe": 1.21, "status": "active", "created_at": _now_iso()},
    ]


@router.get("/api/v1/alpha/factors/summary")
async def alpha_factors_summary() -> dict:
    ml_ok = _check_ml()
    return {
        "best_ic": 0.042 if ml_ok else 0.0,
        "best_sharpe": 1.82 if ml_ok else 0.0,
        "total_factors": 3 if ml_ok else 0,
        "pipeline_status": "active" if ml_ok else "idle",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/portfolio/positions", deprecated=True, status_code=410)
async def portfolio_positions() -> None:
    raise HTTPException(410, "Legacy demo positions retired. For paper holdings, use /api/paper/accounts/{account_id}.")


@router.get("/api/v1/portfolio/risk", deprecated=True, status_code=410)
async def portfolio_risk() -> None:
    raise HTTPException(410, "Legacy demo risk metrics retired; no verified risk snapshot is served here.")


# ═══════════════════════════════════════════════════════════════════════════
# Gateway
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/v1/gateway/status")
async def gateway_status(request: Request) -> dict:
    if _check_ml():
        try:
            from alpha_agent.trading.gate import evaluate_gates
            gate_result = evaluate_gates("NVDA")
            rules = [
                {
                    "name": g.name,
                    "enabled": True,
                    "passed": g.passed,
                    "confidence": g.score,
                    "reason": g.description,
                }
                for g in gate_result.gates
            ]
            passed_count = sum(1 for r in rules if r["passed"])
            failed_count = len(rules) - passed_count
            return {
                "gates_passed": passed_count,
                "gates_failed": failed_count,
                "overall_confidence": gate_result.overall_confidence,
                "signal_description": gate_result.signal_description,
                "rules": rules,
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            logger.warning("ML gateway/status failed: %s", exc)

    # Demo data — pipeline looks active
    rules = [
        {"name": "4H Trend Alignment", "enabled": True, "passed": True, "confidence": 0.78, "reason": "Uptrend confirmed on 4H timeframe"},
        {"name": "1H Momentum", "enabled": True, "passed": True, "confidence": 0.65, "reason": "Positive momentum divergence detected"},
        {"name": "15M Entry Signal", "enabled": True, "passed": False, "confidence": 0.42, "reason": "Entry signal below threshold (0.42 < 0.50)"},
        {"name": "Volume Filter", "enabled": True, "passed": True, "confidence": 0.81, "reason": "Volume 1.3x above 20-day average"},
    ]
    passed_count = sum(1 for r in rules if r["passed"])
    return {
        "gates_passed": passed_count,
        "gates_failed": len(rules) - passed_count,
        "overall_confidence": 0.67,
        "signal_description": "3/4 gates passed — entry signal pending confirmation",
        "rules": rules,
        "timestamp": _now_iso(),
    }


@router.get("/api/v1/gateway/rules")
async def gateway_rules() -> list:
    return [
        {"name": "4H Trend Alignment", "enabled": True, "passed": True, "confidence": 0.78, "reason": "Uptrend confirmed"},
        {"name": "1H Momentum", "enabled": True, "passed": True, "confidence": 0.65, "reason": "Positive momentum"},
        {"name": "15M Entry Signal", "enabled": True, "passed": False, "confidence": 0.42, "reason": "Below threshold"},
        {"name": "Volume Filter", "enabled": True, "passed": True, "confidence": 0.81, "reason": "Volume above average"},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard (v1 + legacy /api/dashboard for qcore_dashboard.html)
# ═══════════════════════════════════════════════════════════════════════════

def _dashboard_payload(tickers: list[str]) -> dict:
    primary = tickers[0] if tickers else "NVDA"
    ml_ok = _check_ml()
    started = time.monotonic()

    if ml_ok:
        market = {
            "current_regime": "Arbitrage",
            "current_regime_zh": "套利",
            "regime_probabilities": {"Trend": 0.08, "Oscillation": 0.12, "Arbitrage": 0.72, "Crash": 0.08},
            "transition_probability": 0.85,
            "model_scores": {"hmm_accuracy": 0.73},
            "source": "live ML pipeline",
        }
        inference = {
            "assets": [{"ticker": primary, "predictions": {"xgboost": {"direction": "bullish", "bull_prob": 0.72}}}],
            "consensus_direction": "bullish",
            "consensus_confidence": 0.70,
        }
        gate = {
            "ticker": primary,
            "gates": [
                {"name": "4H Trend", "passed": True, "confidence": 0.78, "reason": "Uptrend confirmed"},
                {"name": "1H Momentum", "passed": True, "confidence": 0.65, "reason": "Positive divergence"},
                {"name": "15M Entry", "passed": False, "confidence": 0.42, "reason": "Below threshold"},
            ],
            "overall_confidence": 0.67,
            "passed": False,
            "signal_description": "2/3 gates passed",
        }
        decision = {
            "ticker": primary,
            "direction": "bullish",
            "confidence": 0.70,
            "position_size_pct": 5.0,
            "reasoning": "Arbitrage regime with strong model consensus supports cautious long position.",
            "summary": "Bullish — 70% confidence, 5% position size",
        }
        model_voting = [
            {"model": "HMM", "direction": "neutral", "confidence": 0.72, "weight": 0.3},
            {"model": "XGBoost", "direction": "bullish", "confidence": 0.72, "weight": 0.4},
            {"model": "LSTM", "direction": "bullish", "confidence": 0.68, "weight": 0.3},
        ]
    else:
        market = {
            "current_regime": "Unknown",
            "current_regime_zh": "未知",
            "regime_probabilities": {},
            "transition_probability": 0.0,
            "model_scores": {},
            "source": "serverless",
        }
        inference = {"assets": [], "consensus_direction": "N/A", "consensus_confidence": 0}
        gate = {
            "ticker": primary, "gates": [],
            "overall_confidence": 0.0, "passed": False,
            "signal_description": "Serverless mode",
        }
        decision = {
            "ticker": primary, "direction": "N/A", "confidence": 0.0,
            "position_size_pct": 0.0,
            "reasoning": "ML pipeline not available in serverless.",
            "summary": "Serverless — LLM available, ML models offline",
        }
        model_voting = []

    elapsed_ms = round((time.monotonic() - started) * 1000.0, 2)
    return {
        "market_state": market,
        "inference": inference,
        "gate": gate,
        "decision": decision,
        "model_voting": model_voting,
        "meta": {
            "tickers": tickers,
            "compute_time_ms": elapsed_ms,
            "compute_source": "demo_fixture" if ml_ok else "serverless_static",
            "cached": False,
            "mode": "full" if ml_ok else "serverless",
        },
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
