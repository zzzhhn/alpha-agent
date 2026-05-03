"""Schema-drift CI guard.

Catches the class of bug where a new operand is added to one schema layer
(e.g. _V2_FUNDAMENTAL_FIELDS) but missing from another (e.g. AST whitelist
_ALLOWED_OPERANDS), producing user-visible HTTP 400 in production.

The 4 layers that MUST stay in sync:
    1. _ALLOWED_OPERANDS — AST validator (rejects unknown operands)
    2. _V2_FUNDAMENTAL_FIELDS — backend fundamental field registry
    3. fields_augmented.json — operand catalog served to /methodology + LLM
    4. build_data_dict — kernel data dict population

User-reported precedent: shares_outstanding + total_liabilities added to
layers 2 & 4 in T1.5a but not layers 1 & 3 → HTTP 400 on /signal.
"""
from __future__ import annotations

import json
from pathlib import Path

from alpha_agent.core.factor_ast import _ALLOWED_OPERANDS
from alpha_agent.factor_engine.factor_backtest import _V2_FUNDAMENTAL_FIELDS

_ROOT = Path(__file__).resolve().parent.parent
_CATALOG_PATH = _ROOT / "alpha_agent" / "data" / "wq_catalog" / "fields_augmented.json"

# Metadata operands that AST allows but aren't in the fundamental schema
# (price/volume series + GICS metadata + derived dollar-volume windows).
_METADATA_OPERANDS = frozenset({
    "close", "open", "high", "low", "volume", "returns", "vwap",
    "cap", "sector", "industry", "subindustry", "exchange", "currency",
    "dollar_volume", "adv5", "adv10", "adv20", "adv60", "adv120", "adv180",
})


def test_v2_fundamentals_subset_of_ast():
    """Backend fundamental registry MUST be AST-allowed."""
    missing_from_ast = set(_V2_FUNDAMENTAL_FIELDS) - _ALLOWED_OPERANDS
    assert not missing_from_ast, (
        f"_V2_FUNDAMENTAL_FIELDS contains operands not in _ALLOWED_OPERANDS: "
        f"{sorted(missing_from_ast)}. Adding to backend without adding to AST "
        f"causes HTTP 400 'unknown operand' for any factor expression using them."
    )


def test_ast_fundamentals_subset_of_catalog():
    """Every AST-allowed fundamental must appear in the catalog JSON
    (metadata/price/ADV operands are exempt — populated by kernel)."""
    catalog = json.loads(_CATALOG_PATH.read_text())
    catalog_implemented = {f["name"] for f in catalog if f.get("implemented")}
    ast_fundamentals = _ALLOWED_OPERANDS - _METADATA_OPERANDS
    missing_from_catalog = ast_fundamentals - catalog_implemented
    assert not missing_from_catalog, (
        f"AST allows fundamentals NOT marked implemented in catalog: "
        f"{sorted(missing_from_catalog)}. Methodology page will not render "
        f"these; LLM prompt loses the description."
    )


def test_metadata_operands_in_ast():
    in_ast_only = _METADATA_OPERANDS - _ALLOWED_OPERANDS
    assert not in_ast_only, (
        f"Test's _METADATA_OPERANDS contains entries missing from "
        f"_ALLOWED_OPERANDS: {sorted(in_ast_only)}."
    )


def test_catalog_no_orphan_implemented_fundamentals():
    """Catalog must not advertise fundamentals that AST will reject."""
    catalog = json.loads(_CATALOG_PATH.read_text())
    catalog_fundamentals = {
        f["name"] for f in catalog
        if f.get("implemented") and f.get("category") == "fundamental"
    }
    orphans = catalog_fundamentals - _ALLOWED_OPERANDS
    assert not orphans, (
        f"Catalog marks these fundamentals as implemented but they are "
        f"NOT in _ALLOWED_OPERANDS: {sorted(orphans)}"
    )
