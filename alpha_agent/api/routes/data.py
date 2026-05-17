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
from pydantic import BaseModel

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
    # Per-ticker GICS sector, aligned to `tickers` by index. Each entry
    # is the sector string from the panel's last day (sectors rarely
    # change, and broadcast snapshot anyway). `None` when the panel has
    # no sector data — the frontend falls back to a single "Unknown"
    # bucket. Field is optional for back-compat with any older client
    # that doesn't know about it; absence is equivalent to all-None.
    sectors: list[str | None] | None = None
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


class FieldCoverage(BaseModel):
    name: str            # operand name e.g. "revenue"
    category: str        # "ohlcv" | "metadata" | "fundamental"
    tier: str            # "T1" | "T2" — matches catalog tier
    fill_rate: float     # 0.0–1.0
    n_present: int
    n_total: int


class TickerCoverage(BaseModel):
    ticker: str
    fill_rate: float     # OHLCV fill rate for this ticker
    n_missing: int


class CoverageResponse(BaseModel):
    universe_id: str
    n_tickers: int
    n_days: int
    start_date: str
    end_date: str
    # OHLCV summary (most users care about this)
    ohlcv_total_cells: int
    ohlcv_missing_cells: int
    ohlcv_coverage_pct: float
    # Per-field fill rate — varies meaningfully across fundamentals
    field_coverage: list[FieldCoverage]
    # Per-ticker OHLCV coverage
    ticker_coverage: list[TickerCoverage]


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/universe", response_model=UniverseListResponse)
def list_universes() -> UniverseListResponse:
    """List all available universes with their panel statistics."""
    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Sector vector (one entry per ticker, latest-day snapshot). Sectors
    # are snapshot-broadcast so the last row is canonical; nothing is
    # gained by averaging or majority-voting across rows. Coerce numpy
    # strings to plain str + filter out the legacy "Unknown" / "" / "nan"
    # markers that already appear in the AST whitelist's degenerate set.
    sectors: list[str | None] | None
    if panel.sector is None:
        sectors = None
    else:
        last_row = panel.sector[-1]
        sectors = [
            (None if (s is None or str(s) in ("", "Unknown", "nan")) else str(s))
            for s in last_row
        ]

    info = UniverseInfo(
        id="SP500_subset",
        name="SP500 Megacap Subset (1Y)",
        ticker_count=len(panel.tickers),
        benchmark=BENCHMARK_TICKER,
        tickers=list(panel.tickers),
        sectors=sectors,
        start_date=str(panel.dates[0]),
        end_date=str(panel.dates[-1]),
        n_days=len(panel.dates),
        currency="USD",
    )
    return UniverseListResponse(universes=[info])


@router.get("/operands", response_model=OperandCatalogResponse)
def list_operands(
    tier: Literal["all", "available", "T1", "T2", "T3"] = Query(default="all"),
    include_signature: bool = Query(default=False),
) -> OperandCatalogResponse:
    """Return the augmented catalog of operators and operands.

    `tier` filter:
      - "all":       everything (default — UI catalog page)
      - "available": only items with implemented=true (LLM prompt feed)
      - "T1"/"T2"/"T3": exact tier match

    `include_signature=true` enriches each operator entry with `signature` and
    `source_snippet` fields pulled from scan/vectorized.py via inspect. Used
    by the Methodology page (B1) to render the actual NumPy implementation
    body rather than just the doc string.
    """
    operators, operands = _load_catalog()

    if tier == "available":
        operators = [op for op in operators if op.get("implemented")]
        operands = [f for f in operands if f.get("implemented")]
    elif tier in {"T1", "T2", "T3"}:
        operators = [op for op in operators if op.get("tier") == tier]
        operands = [f for f in operands if f.get("tier") == tier]

    if include_signature:
        operators = _attach_signatures(operators)

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


def _attach_signatures(operators: list[dict]) -> list[dict]:
    """Pull `signature` and `source_snippet` from scan/vectorized.py for each op.

    Looks up each operator name in `OPS` (the registry); if found, uses
    inspect.signature() to get the call form and inspect.getsource() to grab
    the first ~12 lines of the function body. Skips silently for any operator
    not in OPS — the catalog has T3 placeholders that aren't implemented.
    """
    import inspect

    from alpha_agent.scan.vectorized import OPS

    enriched: list[dict] = []
    for op in operators:
        name = op.get("name", "")
        fn = OPS.get(name)
        if fn is None:
            enriched.append(op)
            continue
        try:
            sig = str(inspect.signature(fn))
        except (ValueError, TypeError):
            sig = ""
        try:
            full = inspect.getsource(fn).split("\n")
            # Trim docstring if it's a multi-line one — keep the first 12 lines
            # but stop early if we hit `"""` close after seeing `"""` open.
            snippet = "\n".join(full[:14])
        except (OSError, TypeError):
            snippet = ""
        enriched.append({
            **op,
            "signature": f"{name}{sig}" if sig else name,
            "source_snippet": snippet,
        })
    return enriched


@router.get("/sectors")
def list_sectors() -> dict:
    """Return the canonical list of sector strings present in the active panel.

    Used by:
      * the Methodology page Data tab to show "what sectors does the panel cover"
      * the Screener UniverseFilter UI to populate an autocomplete (so users
        don't type "Tech" and hit a 422)
    """
    try:
        from alpha_agent.factor_engine.factor_backtest import _load_panel
    except ImportError as exc:
        raise HTTPException(503, f"factor_engine import failed: {exc}") from exc

    panel = _load_panel()
    if panel.sector is None:
        return {"sectors": [], "panel_has_sector": False}

    sectors = sorted({str(s) for s in panel.sector[-1]})
    return {"sectors": sectors, "panel_has_sector": True}


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(
    universe_id: Literal["SP500_subset"] = Query(default="SP500_subset"),
) -> CoverageResponse:
    """Return per-field fill-rate stats for the active panel.

    Original v1 returned a (T, N) matrix for a heatmap, which was visually
    pretty but information-dense at zero — every cell green for cleaned
    OHLCV. v2 returns (a) per-operand fill rates so fundamentals' real
    73-98% variation is visible and (b) per-ticker OHLCV coverage as
    horizontal bars instead of a wall of cells.
    """
    try:
        panel = _load_panel()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    import numpy as np

    # OHLCV (close as the canonical existence signal)
    present_close = (~np.isnan(panel.close)).astype(int)
    n_total = int(present_close.size)
    n_missing = int(n_total - present_close.sum())

    ticker_rows: list[TickerCoverage] = []
    for i, tk in enumerate(panel.tickers):
        col = present_close[:, i]
        n_t = int(col.size)
        n_p = int(col.sum())
        ticker_rows.append(TickerCoverage(
            ticker=tk,
            fill_rate=round(n_p / n_t, 6) if n_t else 0.0,
            n_missing=n_t - n_p,
        ))
    ticker_rows.sort(key=lambda r: r.fill_rate)   # worst coverage first

    # Per-field fill rate. Walks every numeric (T, N) array exposed to the
    # evaluator so the user sees the *same* fields they can use in factor
    # expressions, with their realistic fill rates.
    field_rows: list[FieldCoverage] = []

    def _add(name: str, arr: np.ndarray, category: str, tier: str) -> None:
        n_p = int((~np.isnan(arr)).sum())
        n_t = int(arr.size)
        field_rows.append(FieldCoverage(
            name=name, category=category, tier=tier,
            fill_rate=round(n_p / n_t, 6) if n_t else 0.0,
            n_present=n_p, n_total=n_t,
        ))

    # OHLCV core
    _add("close",  panel.close,  "ohlcv", "T1")
    _add("open",   panel.open_,  "ohlcv", "T1")
    _add("high",   panel.high,   "ohlcv", "T1")
    _add("low",    panel.low,    "ohlcv", "T1")
    _add("volume", panel.volume, "ohlcv", "T1")

    # Metadata (T2, broadcast snapshots — fill rate is 100% by construction)
    if panel.cap is not None:
        _add("cap", panel.cap, "metadata", "T2")
    if panel.sector is not None:
        # sector is string array; "fill rate" = fraction not "Unknown"
        sec = panel.sector
        n_p = int((sec != "Unknown").sum())
        n_t = int(sec.size)
        field_rows.append(FieldCoverage(
            name="sector", category="metadata", tier="T2",
            fill_rate=round(n_p / n_t, 6) if n_t else 0.0,
            n_present=n_p, n_total=n_t,
        ))
    if panel.industry is not None:
        ind = panel.industry
        n_p = int((ind != "Unknown").sum())
        n_t = int(ind.size)
        field_rows.append(FieldCoverage(
            name="industry", category="metadata", tier="T2",
            fill_rate=round(n_p / n_t, 6) if n_t else 0.0,
            n_present=n_p, n_total=n_t,
        ))

    # Fundamentals (T2 — the interesting variation lives here)
    if panel.fundamentals:
        for fname, farr in panel.fundamentals.items():
            _add(fname, farr, "fundamental", "T2")

    # Sort: ohlcv first, then metadata, then fundamentals; within each
    # category, sort by fill rate ASCENDING so worst-covered floats up.
    cat_order = {"ohlcv": 0, "metadata": 1, "fundamental": 2}
    field_rows.sort(key=lambda f: (cat_order.get(f.category, 9), f.fill_rate))

    return CoverageResponse(
        universe_id=universe_id,
        n_tickers=len(panel.tickers),
        n_days=len(panel.dates),
        start_date=str(panel.dates[0]),
        end_date=str(panel.dates[-1]),
        ohlcv_total_cells=n_total,
        ohlcv_missing_cells=n_missing,
        ohlcv_coverage_pct=round(100.0 * (n_total - n_missing) / n_total, 4) if n_total else 0.0,
        field_coverage=field_rows,
        ticker_coverage=ticker_rows,
    )
