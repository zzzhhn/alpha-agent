"""Data layer endpoints — universe metadata, operand catalog, coverage.

P1 of the Data → Signal → Report pipeline. These are read-only introspection
endpoints that tell the UI what raw material is available for factor construction.

Design principles:
  * Honest: return actual panel stats, never fabricate a "fuller" universe.
  * Cheap: all endpoints reuse the lru_cached panel loader from factor_backtest,
    so a warm process answers in <5ms.
  * Upstream: nothing here depends on Signal or Report layers — safe to deploy
    independently.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from alpha_agent.factor_engine.factor_backtest import (
    BENCHMARK_TICKER,
    _load_panel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/data", tags=["data"])


# ── Static catalog: operators + operands ───────────────────────────────────
# Source of truth lives in alpha_agent.core.types (AllowedOperator Literal) and
# the evaluator's known operands. Descriptions are curated here so the UI can
# render a human-readable catalog without re-deriving from source code.

_OPERATOR_CATALOG: list[dict] = [
    {"name": "ts_mean",  "arity": 2, "category": "time_series",
     "description_en": "Rolling arithmetic mean over last N periods.",
     "description_zh": "过去 N 期算术平均。",
     "example": "ts_mean(returns, 10)"},
    {"name": "ts_rank",  "arity": 2, "category": "time_series",
     "description_en": "Rolling rank of the last value vs prior N periods.",
     "description_zh": "当前值在过去 N 期中的排名分位。",
     "example": "ts_rank(close, 20)"},
    {"name": "ts_corr",  "arity": 3, "category": "time_series",
     "description_en": "Rolling correlation of two series over N periods.",
     "description_zh": "两序列在过去 N 期的滚动相关系数。",
     "example": "ts_corr(close, volume, 10)"},
    {"name": "ts_std",   "arity": 2, "category": "time_series",
     "description_en": "Rolling standard deviation over N periods.",
     "description_zh": "过去 N 期标准差。",
     "example": "ts_std(returns, 20)"},
    {"name": "ts_zscore","arity": 2, "category": "time_series",
     "description_en": "Rolling z-score: (x - ts_mean(x, N)) / ts_std(x, N).",
     "description_zh": "过去 N 期 z-score 标准化。",
     "example": "ts_zscore(close, 20)"},
    {"name": "rank",     "arity": 1, "category": "cross_section",
     "description_en": "Cross-sectional rank across the universe [0, 1].",
     "description_zh": "当日在全 universe 内的横截面排名（0 到 1）。",
     "example": "rank(close)"},
    {"name": "scale",    "arity": 1, "category": "cross_section",
     "description_en": "Cross-sectional L1-normalization (sum of |x| = 1).",
     "description_zh": "横截面 L1 归一化。",
     "example": "scale(returns)"},
    {"name": "log",      "arity": 1, "category": "unary",
     "description_en": "Natural log. NaN for non-positive input.",
     "description_zh": "自然对数，非正数返回 NaN。",
     "example": "log(close)"},
    {"name": "sign",     "arity": 1, "category": "unary",
     "description_en": "Sign function: -1, 0, or 1.",
     "description_zh": "符号函数。",
     "example": "sign(returns)"},
    {"name": "winsorize","arity": 2, "category": "cross_section",
     "description_en": "Cap cross-sectional outliers at quantile q and 1-q.",
     "description_zh": "按横截面分位截断极值。",
     "example": "winsorize(returns, 0.05)"},
    {"name": "add",      "arity": 2, "category": "arithmetic",
     "description_en": "Element-wise addition.",
     "description_zh": "逐元素加法。",
     "example": "add(close, open)"},
    {"name": "sub",      "arity": 2, "category": "arithmetic",
     "description_en": "Element-wise subtraction.",
     "description_zh": "逐元素减法。",
     "example": "sub(close, vwap)"},
    {"name": "mul",      "arity": 2, "category": "arithmetic",
     "description_en": "Element-wise multiplication.",
     "description_zh": "逐元素乘法。",
     "example": "mul(rank(close), rank(volume))"},
    {"name": "div",      "arity": 2, "category": "arithmetic",
     "description_en": "Element-wise division. NaN on divide-by-zero.",
     "description_zh": "逐元素除法，除零返回 NaN。",
     "example": "div(close, vwap)"},
    {"name": "pow",      "arity": 2, "category": "arithmetic",
     "description_en": "Element-wise power (base, exponent).",
     "description_zh": "逐元素幂运算。",
     "example": "pow(returns, 2)"},
]

_OPERAND_CATALOG: list[dict] = [
    {"name": "close",   "derived": False, "description_en": "Daily close price.",            "description_zh": "日收盘价。"},
    {"name": "open",    "derived": False, "description_en": "Daily open price.",             "description_zh": "日开盘价。"},
    {"name": "high",    "derived": False, "description_en": "Daily high price.",             "description_zh": "日最高价。"},
    {"name": "low",     "derived": False, "description_en": "Daily low price.",              "description_zh": "日最低价。"},
    {"name": "volume",  "derived": False, "description_en": "Daily traded volume (shares).", "description_zh": "日成交量（股数）。"},
    {"name": "vwap",    "derived": True,  "description_en": "Approximation: (high+low+close)/3. Not true VWAP.", "description_zh": "近似 VWAP：(最高+最低+收盘)/3，非真实 VWAP。"},
    {"name": "returns", "derived": True,  "description_en": "Daily simple returns: close/close.shift(1) - 1.",   "description_zh": "日简单收益率：close 环比变动。"},
]


# ── Response models ─────────────────────────────────────────────────────────


class UniverseInfo(BaseModel):
    id: str
    name: str
    ticker_count: int
    benchmark: str
    tickers: list[str]
    start_date: str
    end_date: str
    n_days: int
    currency: str


class UniverseListResponse(BaseModel):
    universes: list[UniverseInfo]


class OperandCatalogResponse(BaseModel):
    operators: list[dict]
    operands: list[dict]


class CoverageResponse(BaseModel):
    universe_id: str
    dates: list[str]
    tickers: list[str]
    matrix: list[list[int]]          # T × N, 1 = present, 0 = missing
    total_cells: int
    missing_cells: int
    coverage_pct: float
    missing_per_ticker: dict[str, int]


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/universe", response_model=UniverseListResponse)
def list_universes() -> UniverseListResponse:
    """List all available universes with their panel statistics."""
    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    info = UniverseInfo(
        id="SP500_subset",
        name="SP500 Megacap Subset (1Y)",
        ticker_count=len(panel.tickers),
        benchmark=BENCHMARK_TICKER,
        tickers=list(panel.tickers),
        start_date=str(panel.dates[0]),
        end_date=str(panel.dates[-1]),
        n_days=len(panel.dates),
        currency="USD",
    )
    return UniverseListResponse(universes=[info])


@router.get("/operands", response_model=OperandCatalogResponse)
def list_operands() -> OperandCatalogResponse:
    """Return the full catalog of operators and operands the factor DSL accepts."""
    return OperandCatalogResponse(
        operators=_OPERATOR_CATALOG,
        operands=_OPERAND_CATALOG,
    )


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(
    universe_id: Literal["SP500_subset"] = Query(default="SP500_subset"),
) -> CoverageResponse:
    """Return present/missing matrix for the requested universe.

    All cells are 1 (present) for the current cleaned panel — but the endpoint
    shape supports future universes where coverage gaps exist. Honest now, ready
    later.
    """
    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    import numpy as np
    # close is (T, N); cells where close is NaN => missing
    present = (~np.isnan(panel.close)).astype(int)
    total = int(present.size)
    missing = int(total - present.sum())
    per_ticker = {
        tk: int((present[:, i] == 0).sum())
        for i, tk in enumerate(panel.tickers)
    }

    return CoverageResponse(
        universe_id=universe_id,
        dates=[str(d) for d in panel.dates],
        tickers=list(panel.tickers),
        matrix=present.tolist(),
        total_cells=total,
        missing_cells=missing,
        coverage_pct=round(100.0 * (total - missing) / total, 4) if total else 0.0,
        missing_per_ticker=per_ticker,
    )
