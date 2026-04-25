"""Interactive POST endpoints — user-controlled backtest, ticker analysis, search.

These endpoints wrap existing ML modules with parameter acceptance, transforming
the read-only dashboard into a research workstation.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["interactive"])


# ── Request / Response schemas ──────────────────────────────────────────────


class TickerSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20)

    model_config = {"protected_namespaces": ()}


class FactorAnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    sort_by: str = Field(default="ic", pattern=r"^(ic|icir|sharpe|name)$")

    model_config = {"protected_namespaces": ()}


class GateSimulateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    gate_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    weight_trend: float = Field(default=0.40, ge=0.0, le=1.0)
    weight_momentum: float = Field(default=0.35, ge=0.0, le=1.0)
    weight_entry: float = Field(default=0.25, ge=0.0, le=1.0)

    model_config = {"protected_namespaces": ()}


class StressTestRequest(BaseModel):
    positions: list[dict] = Field(..., min_length=1)
    scenario: str = Field(default="covid_crash")
    custom_shocks: dict[str, float] = Field(default_factory=dict)

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


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Factor Analytics + Gate Editor
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/api/v1/factors/analyze")
async def analyze_factors(req: FactorAnalyzeRequest) -> dict[str, Any]:
    """Return factor registry + live feature stats for a ticker."""

    # 1. Factor registry (saved factors from pipeline runs)
    registry_factors: list[dict] = []
    try:
        from alpha_agent.pipeline.registry import FactorRegistry
        registry = FactorRegistry()
        for record in registry.list_all():
            metrics = record.metrics if isinstance(record.metrics, dict) else {}
            registry_factors.append({
                "id": record.id,
                "name": record.hypothesis_name,
                "expression": record.expression,
                "rationale": record.rationale,
                "ic": metrics.get("ic_mean", 0.0),
                "icir": metrics.get("icir", 0.0),
                "sharpe": metrics.get("sharpe_ratio", 0.0),
                "turnover": metrics.get("turnover", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "alpha_decay": metrics.get("alpha_decay", []),
                "created_at": record.created_at,
            })
    except Exception as exc:
        logger.warning("FactorRegistry load failed: %s", exc)

    # 2. Live feature stats for the ticker
    feature_stats: list[dict] = []
    try:
        ohlcv = _fetch_ohlcv(req.ticker, "2023-01-01", datetime.now().strftime("%Y-%m-%d"))
        if not ohlcv.empty:
            from alpha_agent.models.features import compute_feature_stats
            feature_stats = [dict(s) for s in compute_feature_stats(ohlcv, req.ticker)]
    except Exception as exc:
        logger.warning("Feature stats failed: %s", exc)

    # 3. Sort registry factors
    sort_key = req.sort_by
    if sort_key in ("ic", "icir", "sharpe") and registry_factors:
        registry_factors.sort(key=lambda f: abs(f.get(sort_key, 0)), reverse=True)
    elif sort_key == "name" and registry_factors:
        registry_factors.sort(key=lambda f: f.get("name", ""))

    # 4. Build correlation matrix from feature stats
    correlation_matrix: list[list[float]] = []
    feature_names: list[str] = []
    try:
        if not ohlcv.empty:
            from alpha_agent.models.features import compute_features
            feat_df = compute_features(ohlcv, req.ticker)
            if not feat_df.empty:
                feature_names = list(feat_df.columns)
                corr = feat_df.corr()
                correlation_matrix = [[round(float(v), 3) for v in row] for row in corr.values]
    except Exception as exc:
        logger.warning("Correlation matrix failed: %s", exc)

    return {
        "ticker": req.ticker,
        "registry_factors": registry_factors,
        "feature_stats": feature_stats,
        "feature_names": feature_names,
        "correlation_matrix": correlation_matrix,
        "total_factors": len(registry_factors),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/v1/gates/simulate")
async def simulate_gates(req: GateSimulateRequest) -> dict[str, Any]:
    """Evaluate multi-timeframe gates with custom threshold and weights."""
    try:
        from alpha_agent.trading.gate import evaluate_gates
    except ImportError:
        raise HTTPException(status_code=501, detail="Gate module not available")

    try:
        result = evaluate_gates(req.ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gate evaluation failed: {exc}") from exc

    # Re-score with user weights
    weights = {
        "4H Trend": req.weight_trend,
        "1H Momentum": req.weight_momentum,
        "15M Entry": req.weight_entry,
    }
    total_weight = sum(weights.values()) or 1.0

    gates_output = []
    weighted_score = 0.0
    for gate in result.gates:
        w = weights.get(gate.name, 0.0) / total_weight
        weighted_score += gate.score * w
        gates_output.append({
            "name": gate.name,
            "timeframe": gate.timeframe,
            "score": round(gate.score, 4),
            "weight": round(w, 4),
            "passed": gate.score >= req.gate_threshold,
            "description": gate.description,
        })

    overall_pass = all(g["passed"] for g in gates_output)

    return {
        "ticker": req.ticker,
        "gates": gates_output,
        "composite_score": round(weighted_score, 4),
        "threshold": req.gate_threshold,
        "passed": overall_pass,
        "signal_description": result.signal_description,
        "weights_used": {
            "trend": round(req.weight_trend / total_weight, 4),
            "momentum": round(req.weight_momentum / total_weight, 4),
            "entry": round(req.weight_entry / total_weight, 4),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Portfolio Stress Test
# ══════════════════════════════════════════════════════════════════════════════

_STRESS_SCENARIOS = {
    "covid_crash": {
        "name": "COVID-19 Crash",
        "name_zh": "新冠暴跌 (2020.02-03)",
        "description": "Feb-Mar 2020 market crash: SPY -34%, VIX +400%",
        "period": "2020-02-19 to 2020-03-23",
        "shocks": {"SPY": -0.34, "QQQ": -0.28, "IWM": -0.41, "VIX": 4.0,
                   "XLF": -0.38, "XLK": -0.26, "XLE": -0.55, "XLV": -0.22},
    },
    "rate_hike_2022": {
        "name": "2022 Rate Hike Selloff",
        "name_zh": "2022 加息抛售",
        "description": "2022 Fed rate hikes: growth stocks hit hardest, SPY -25%",
        "period": "2022-01-03 to 2022-10-12",
        "shocks": {"SPY": -0.25, "QQQ": -0.35, "IWM": -0.27, "VIX": 1.5,
                   "XLF": -0.20, "XLK": -0.33, "XLE": 0.45, "XLV": -0.05},
    },
    "gfc_2008": {
        "name": "2008 Financial Crisis",
        "name_zh": "2008 金融危机",
        "description": "Global Financial Crisis: SPY -57%, financials devastated",
        "period": "2007-10-09 to 2009-03-09",
        "shocks": {"SPY": -0.57, "QQQ": -0.49, "IWM": -0.60, "VIX": 5.0,
                   "XLF": -0.83, "XLK": -0.48, "XLE": -0.56, "XLV": -0.38},
    },
    "dot_com_burst": {
        "name": "Dot-Com Bubble Burst",
        "name_zh": "互联网泡沫破裂 (2000)",
        "description": "2000-2002 tech crash: NASDAQ -78%, value outperformed",
        "shocks": {"SPY": -0.49, "QQQ": -0.78, "IWM": -0.32, "VIX": 2.5,
                   "XLF": -0.18, "XLK": -0.82, "XLE": 0.10, "XLV": -0.10},
    },
}

# Beta estimates for common tickers (approximate)
_TICKER_BETAS: dict[str, dict[str, float]] = {
    "NVDA": {"SPY": 1.8, "QQQ": 1.6, "XLK": 1.5},
    "AAPL": {"SPY": 1.2, "QQQ": 1.1, "XLK": 1.0},
    "MSFT": {"SPY": 1.1, "QQQ": 1.0, "XLK": 0.95},
    "GOOG": {"SPY": 1.2, "QQQ": 1.1, "XLK": 1.0},
    "AMZN": {"SPY": 1.3, "QQQ": 1.2, "XLK": 1.1},
    "META": {"SPY": 1.4, "QQQ": 1.3, "XLK": 1.2},
    "TSLA": {"SPY": 2.0, "QQQ": 1.8, "XLK": 1.5},
    "AMD":  {"SPY": 1.7, "QQQ": 1.5, "XLK": 1.4},
    "NFLX": {"SPY": 1.3, "QQQ": 1.2, "XLK": 1.0},
    "JPM":  {"SPY": 1.1, "QQQ": 0.6, "XLF": 1.2},
    "BAC":  {"SPY": 1.3, "QQQ": 0.5, "XLF": 1.4},
    "V":    {"SPY": 1.0, "QQQ": 0.8, "XLF": 0.9},
    "JNJ":  {"SPY": 0.7, "QQQ": 0.3, "XLV": 0.9},
    "WMT":  {"SPY": 0.5, "QQQ": 0.3, "XLK": 0.2},
    "XOM":  {"SPY": 0.9, "QQQ": 0.3, "XLE": 1.1},
}


def _estimate_ticker_shock(ticker: str, scenario_shocks: dict[str, float]) -> float:
    """Estimate a ticker's shock using sector ETF beta mapping."""
    betas = _TICKER_BETAS.get(ticker, {"SPY": 1.0})
    total_shock = 0.0
    total_weight = 0.0
    for etf, beta in betas.items():
        if etf in scenario_shocks:
            total_shock += beta * scenario_shocks[etf]
            total_weight += 1.0
    if total_weight == 0:
        return scenario_shocks.get("SPY", -0.20)
    return total_shock / total_weight


@router.post("/api/v1/portfolio/stress")
async def stress_test(req: StressTestRequest) -> dict[str, Any]:
    """Run a stress test on a portfolio using predefined or custom scenarios."""

    # Resolve scenario
    if req.scenario == "custom":
        if not req.custom_shocks:
            raise HTTPException(status_code=400, detail="Custom scenario requires custom_shocks")
        scenario_info = {
            "name": "Custom Scenario",
            "name_zh": "自定义情景",
            "description": "User-defined market shocks",
            "shocks": req.custom_shocks,
        }
    else:
        scenario_info = _STRESS_SCENARIOS.get(req.scenario)
        if not scenario_info:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scenario: {req.scenario}. Available: {list(_STRESS_SCENARIOS.keys())}",
            )

    shocks = scenario_info["shocks"]

    # Calculate per-position impact
    total_portfolio_value = sum(p.get("value", 0) for p in req.positions)
    if total_portfolio_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio total value must be positive")

    position_results = []
    total_pnl = 0.0

    for pos in req.positions:
        ticker = pos.get("ticker", "UNKNOWN")
        value = float(pos.get("value", 0))
        weight = value / total_portfolio_value

        ticker_shock = _estimate_ticker_shock(ticker, shocks)
        pnl = value * ticker_shock
        total_pnl += pnl

        position_results.append({
            "ticker": ticker,
            "value": round(value, 2),
            "weight": round(weight, 4),
            "shock": round(ticker_shock, 4),
            "pnl": round(pnl, 2),
            "contribution": round(weight * ticker_shock, 4),
        })

    # Sort by contribution (worst first)
    position_results.sort(key=lambda p: p["contribution"])

    portfolio_return = total_pnl / total_portfolio_value

    return {
        "scenario": {
            "id": req.scenario,
            "name": scenario_info.get("name", req.scenario),
            "name_zh": scenario_info.get("name_zh", req.scenario),
            "description": scenario_info.get("description", ""),
            "period": scenario_info.get("period", ""),
        },
        "portfolio": {
            "initial_value": round(total_portfolio_value, 2),
            "pnl": round(total_pnl, 2),
            "return_pct": round(portfolio_return * 100, 2),
            "final_value": round(total_portfolio_value + total_pnl, 2),
        },
        "positions": position_results,
        "available_scenarios": [
            {"id": k, "name": v["name"], "name_zh": v["name_zh"]}
            for k, v in _STRESS_SCENARIOS.items()
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════════════════════
# T1: HypothesisTranslator (REFACTOR_PLAN.md §3.1)
# ════════════════════════════════════════════════════════════════════════════
#
# Input: natural-language factor hypothesis
# Output: FactorSpec JSON (Pydantic-validated + AST-validated) + 10-day smoke IC
#
# Pipeline:
#   1. LLM call with grammar-describing system prompt
#   2. Pydantic FactorSpec.model_validate  (field schemas)
#   3. validate_expression  (AST whitelist + declared/used op equality)
#   4. smoke_test  (20-ticker synthetic panel, 10-day cross-sectional Spearman IC)
#
# Failure surfacing: each step raises a distinct HTTPException status so curl
# consumers can distinguish schema violation (422) from upstream-provider error
# (502) from smoke crash (500). See feedback_silent_trycatch_antipattern.md.

import json as _json
import re as _re

from fastapi import Request as _Request

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError as _FactorSpecValidationError,
)
from alpha_agent.core.factor_ast import validate_expression as _validate_expression
from alpha_agent.core.types import FactorSpec as _FactorSpec
from alpha_agent.llm.base import Message as _Message
from alpha_agent.scan.smoke import smoke_test as _smoke_test


class HypothesisTranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    universe: str = Field(
        default="SP500", pattern=r"^(CSI300|CSI500|SP500|custom)$"
    )
    budget_tokens: int = Field(default=4000, ge=500, le=8000)


class SmokeReport(BaseModel):
    rows_valid: int
    ic_spearman: float
    runtime_ms: float


class HypothesisTranslateResponse(BaseModel):
    spec: _FactorSpec
    smoke: SmokeReport
    llm_tokens: dict[str, int]
    llm_raw: str


def _build_translate_prompt() -> str:
    """Build the system prompt with the LIVE operator + operand whitelist.

    Source of truth = scan/vectorized.py::OPS and core/factor_ast::_ALLOWED_OPERANDS.
    Re-rendered each request so adding an operator anywhere flows here automatically.
    """
    from alpha_agent.scan.vectorized import OPS as _OPS
    from alpha_agent.core.factor_ast import _ALLOWED_OPERANDS

    # Group operators by category for readability.
    arith = sorted(n for n in _OPS if n in {
        "abs", "add", "subtract", "sub", "multiply", "mul", "divide", "div",
        "inverse", "log", "sqrt", "power", "pow", "sign", "signed_power",
        "max", "min", "reverse", "densify",
    })
    logic = sorted(n for n in _OPS if n in {
        "if_else", "and_", "or_", "not_", "is_nan",
        "equal", "not_equal", "less", "greater", "less_equal", "greater_equal",
    })
    ts = sorted(n for n in _OPS if n.startswith("ts_") or n == "last_diff_value")
    cs = sorted(n for n in _OPS if n in {
        "rank", "zscore", "scale", "normalize", "quantile", "winsorize",
    })
    grp = sorted(n for n in _OPS if n.startswith("group_"))

    operands = sorted(_ALLOWED_OPERANDS)

    return f"""You convert a natural-language factor hypothesis into a strict FactorSpec JSON.

Output rules:
1. Emit ONLY one JSON object. No prose, no markdown fences.
2. Schema:
   {{
     "name": "<snake_case, <=40 chars>",
     "hypothesis": "<<=200 chars, restate the user idea>",
     "expression": "<Python call syntax using ALLOWED_OPS>",
     "operators_used": [<exact set of ops used in expression>],
     "lookback": <int 5-252>,
     "universe": "<CSI300|CSI500|SP500|custom>",
     "justification": "<<=400 chars, why this captures the hypothesis>"
   }}

ALLOWED_OPS — every function call must be one of these names:
  arithmetic:    {", ".join(arith)}
  logical:       {", ".join(logic)}
  time-series:   {", ".join(ts)}
  cross-section: {", ".join(cs)}
  group:         {", ".join(grp)}

Operands (leaves) — only these names + numeric literals are allowed:
  {", ".join(operands)}

No attributes, no imports, no lambdas, no keyword args. No infix `< > == + - * / **`
— use the functional forms (less, greater, equal, add, sub, mul, div, pow).

Op signatures:
  ts_mean(arr, window:int)         ts_std_dev(arr, window:int)
  ts_zscore(arr, window:int)       ts_rank(arr, window:int)
  ts_delay(arr, d:int)             ts_delta(arr, d:int)
  ts_sum/ts_min/ts_max/ts_arg_min/ts_arg_max(arr, window:int)
  ts_corr(arr, arr, window:int)    ts_covariance(arr, arr, window:int)
  ts_quantile(arr, window:int, q:float)
  ts_decay_linear(arr, window:int) ts_decay_exp(arr, window:int)
  rank(arr)  scale(arr)  zscore(arr)  normalize(arr)
  winsorize(arr, pct:float)        quantile(arr, n_buckets:int)
  group_rank/group_zscore/group_neutralize/group_mean/group_scale(arr, group_arr)
    — group_arr MUST be `sector` or `industry`.
  if_else(cond, t, f)              and_(a,b)/or_(a,b)/not_(x)
  equal/less/greater(a,b)
  add/sub/mul/div/pow/power(a,b)   abs/log/sqrt/sign/inverse(x)

lookback must be >= the largest ts_* window in the expression.
operators_used must exactly equal the set of ops actually called.

Example input: {{"hypothesis": "low turnover and rising ROE for mid-caps", "universe": "CSI500"}}
Example output:
{{"name":"low_turn_roe_up","hypothesis":"Mid-caps with low turnover and rising ROE.","expression":"sub(rank(ts_mean(div(volume,close),20)),rank(ts_zscore(returns,20)))","operators_used":["sub","rank","ts_mean","div","ts_zscore"],"lookback":20,"universe":"CSI500","justification":"Inverse-turnover proxy via rolling volume/close; ROE proxy via short-term return zscore; cross-sectional rank removes scale."}}
"""


_TRANSLATE_SYSTEM_PROMPT = _build_translate_prompt()


def _extract_json_object(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response (tolerates fences)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[: cleaned.rfind("```")]
    match = _re.search(r"\{[\s\S]*\}", cleaned)
    if match is None:
        return None
    try:
        return _json.loads(match.group(0))
    except _json.JSONDecodeError:
        return None


@router.post(
    "/api/v1/alpha/translate",
    response_model=HypothesisTranslateResponse,
)
async def translate_hypothesis(
    body: HypothesisTranslateRequest, request: _Request
) -> HypothesisTranslateResponse:
    """T1 HypothesisTranslator: NL -> FactorSpec -> smoke IC."""
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        raise HTTPException(
            503,
            "LLM provider not initialized (check /healthz/routers and LLM_PROVIDER env)",
        )

    user_payload = _json.dumps({"hypothesis": body.text, "universe": body.universe})
    messages = [
        _Message(role="system", content=_TRANSLATE_SYSTEM_PROMPT),
        _Message(role="user", content=user_payload),
    ]
    try:
        llm_resp = await llm.chat(
            messages, temperature=0.3, max_tokens=body.budget_tokens
        )
    except Exception as exc:  # noqa: BLE001 — surface upstream failure explicitly
        raise HTTPException(
            502, f"LLM provider error: {type(exc).__name__}: {exc}"
        ) from exc

    spec_dict = _extract_json_object(llm_resp.content)
    if spec_dict is None:
        raise HTTPException(
            422,
            f"LLM did not return parseable JSON. Head: {llm_resp.content[:200]!r}",
        )

    try:
        spec = _FactorSpec.model_validate(spec_dict)
    except ValueError as exc:
        raise HTTPException(422, f"FactorSpec schema violation: {exc}") from exc

    try:
        _validate_expression(spec.expression, spec.operators_used)
    except _FactorSpecValidationError as exc:
        raise HTTPException(422, f"Expression AST invalid: {exc}") from exc

    try:
        smoke = _smoke_test(spec.expression, spec.lookback)
    except Exception as exc:  # noqa: BLE001 — smoke crash is a real bug
        raise HTTPException(
            500, f"Smoke test crashed: {type(exc).__name__}: {exc}"
        ) from exc

    return HypothesisTranslateResponse(
        spec=spec,
        smoke=SmokeReport(
            rows_valid=smoke.rows_valid,
            ic_spearman=smoke.ic_spearman,
            runtime_ms=smoke.runtime_ms,
        ),
        llm_tokens={
            "prompt": llm_resp.prompt_tokens,
            "completion": llm_resp.completion_tokens,
        },
        llm_raw=llm_resp.content,
    )


# ── Factor long-short backtest ──────────────────────────────────────────────


class FactorBacktestRequest(BaseModel):
    spec: _FactorSpec
    train_ratio: float = Field(default=0.80, ge=0.10, le=0.95)
    direction: Literal["long_short", "long_only", "short_only"] = Field(
        default="long_short",
        description=(
            "Portfolio construction. 'long_short' is market-neutral (gross 2.0), "
            "'long_only' is apples-to-apples with SPY benchmark, 'short_only' "
            "is the inverse."
        ),
    )
    # P4.1 — configurable rank cutoffs and transaction cost.
    top_pct: float = Field(default=0.30, ge=0.01, le=0.50,
        description="Fraction of universe to long (rank ≥ 1 - top_pct).")
    bottom_pct: float = Field(default=0.30, ge=0.01, le=0.50,
        description="Fraction of universe to short (rank ≤ bottom_pct).")
    transaction_cost_bps: float = Field(default=0.0, ge=0.0, le=200.0,
        description="Round-trip cost in basis points; charged on L1 weight delta.")


class _SplitMetricsModel(BaseModel):
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int
    max_drawdown: float = 0.0
    turnover: float = 0.0
    hit_rate: float = 0.0


class _CurvePoint(BaseModel):
    date: str
    value: float


class FactorBacktestResponse(BaseModel):
    equity_curve: list[_CurvePoint]
    benchmark_curve: list[_CurvePoint]
    train_end_index: int
    train_metrics: _SplitMetricsModel
    test_metrics: _SplitMetricsModel
    currency: str
    factor_name: str
    benchmark_ticker: str
    direction: Literal["long_short", "long_only", "short_only"]


@router.post(
    "/api/v1/factor/backtest",
    response_model=FactorBacktestResponse,
)
async def factor_backtest(body: FactorBacktestRequest) -> FactorBacktestResponse:
    """Run a cross-sectional long-short backtest on the 37-ticker US panel.

    Uses a pre-cached 1y OHLCV parquet (committed at deploy-time) so the
    request stays inside Vercel's 300s timeout. Long top 30% / short
    bottom 30% by factor rank, equal-weighted daily rebalance. Returns
    train/test metrics plus SPY benchmark curve for overlay.
    """
    # Lazy import: keeps existing interactive endpoints alive if the
    # factor_engine submodule fails to import (see dual-entry mirror rule).
    try:
        from alpha_agent.factor_engine.factor_backtest import run_factor_backtest
    except ImportError as exc:
        raise HTTPException(
            503,
            f"factor_engine module failed to import: {type(exc).__name__}: {exc}",
        ) from exc

    # Re-validate the expression against the AST whitelist. The FactorSpec
    # model already validates operator names, but _validate_expression also
    # catches AST-level issues like calling a non-whitelisted op inline.
    try:
        _validate_expression(body.spec.expression, body.spec.operators_used)
    except _FactorSpecValidationError as exc:
        raise HTTPException(422, f"Expression AST invalid: {exc}") from exc

    try:
        result = run_factor_backtest(
            body.spec,
            train_ratio=body.train_ratio,
            direction=body.direction,
            top_pct=body.top_pct,
            bottom_pct=body.bottom_pct,
            transaction_cost_bps=body.transaction_cost_bps,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Panel data missing: {exc}") from exc
    except ImportError as exc:
        raise HTTPException(
            503,
            f"Optional dependency missing during backtest: {type(exc).__name__}: {exc}",
        ) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            422, f"Factor evaluation failed: {type(exc).__name__}: {exc}"
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            422,
            f"Factor uses an operator without a vectorized impl: {exc}",
        ) from exc

    def _to_model(m) -> _SplitMetricsModel:
        return _SplitMetricsModel(
            sharpe=m.sharpe,
            total_return=m.total_return,
            ic_spearman=m.ic_spearman,
            n_days=m.n_days,
            max_drawdown=m.max_drawdown,
            turnover=m.turnover,
            hit_rate=m.hit_rate,
        )

    return FactorBacktestResponse(
        equity_curve=[_CurvePoint(**p) for p in result.equity_curve],
        benchmark_curve=[_CurvePoint(**p) for p in result.benchmark_curve],
        train_end_index=result.train_end_index,
        train_metrics=_to_model(result.train_metrics),
        test_metrics=_to_model(result.test_metrics),
        currency=result.currency,
        factor_name=result.factor_name,
        benchmark_ticker=result.benchmark_ticker,
        direction=result.direction,
    )
