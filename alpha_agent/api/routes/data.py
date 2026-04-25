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

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from alpha_agent.factor_engine.factor_backtest import (
    BENCHMARK_TICKER,
    _load_panel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/data", tags=["data"])


# ── Catalog loader (source of truth = WorldQuant docs ingested into JSON) ──
# Re-run alpha_agent/data/wq_catalog/augment_catalog.py to refresh tiers
# whenever the OPS dict or panel schema changes.

_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wq_catalog"


@lru_cache(maxsize=1)
def _load_catalog() -> tuple[list[dict], list[dict]]:
    """Return (operators, operands) augmented with tier + implemented flags."""
    ops_path = _CATALOG_DIR / "operators_augmented.json"
    fields_path = _CATALOG_DIR / "fields_augmented.json"
    if not ops_path.exists() or not fields_path.exists():
        logger.warning(
            "wq_catalog augmented JSON missing; falling back to empty catalog. "
            "Re-run alpha_agent/data/wq_catalog/augment_catalog.py."
        )
        return [], []
    operators = json.loads(ops_path.read_text())
    operands = json.loads(fields_path.read_text())
    return operators, operands



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
    """Augmented WorldQuant catalog. Each item carries `tier` and `implemented`.

    Tier semantics:
      - "T1" — implemented now, included in factor expressions today
      - "T2" — implemented, requires v2 panel data (sector / fundamentals)
      - "T3" — catalog-only; data source unavailable or operator semantics
        out of scope (vector ops, news/options/sentiment, infix comparisons)
    """
    operators: list[dict]
    operands: list[dict]
    tier_summary: dict[str, dict[str, int]]  # {operators|operands: {T1: n, T2, T3, total}}


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
def list_operands(
    tier: Literal["all", "available", "T1", "T2", "T3"] = Query(default="all"),
) -> OperandCatalogResponse:
    """Return the augmented catalog of operators and operands.

    `tier` filter:
      - "all":       everything (default — UI catalog page)
      - "available": only items with implemented=true (LLM prompt feed)
      - "T1"/"T2"/"T3": exact tier match
    """
    operators, operands = _load_catalog()

    if tier == "available":
        operators = [op for op in operators if op.get("implemented")]
        operands = [f for f in operands if f.get("implemented")]
    elif tier in {"T1", "T2", "T3"}:
        operators = [op for op in operators if op.get("tier") == tier]
        operands = [f for f in operands if f.get("tier") == tier]

    def _summarize(items: list[dict]) -> dict[str, int]:
        s = {"T1": 0, "T2": 0, "T3": 0, "total": len(items)}
        for it in items:
            t = it.get("tier", "T3")
            s[t] = s.get(t, 0) + 1
        return s

    # tier_summary always reflects the full catalog (not the filtered slice),
    # so the UI can show "you're seeing X / total" alongside the items.
    full_ops, full_fields = _load_catalog()
    return OperandCatalogResponse(
        operators=operators,
        operands=operands,
        tier_summary={
            "operators": _summarize(full_ops),
            "operands": _summarize(full_fields),
        },
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
