# alpha_agent/fusion/attribution.py
"""Reverse attribution: which signals drove the rating up/down."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _contrib(b: Mapping[str, Any]) -> float:
    """Read contribution from a breakdown row, treating None / missing /
    non-numeric as 0.0. Storage layer sanitizes NaN/Inf → None before JSONB
    write, so reading back can hit None even though the original code
    produced a float."""
    v = b.get("contribution", 0.0)
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def top_drivers(breakdown: Sequence[Mapping[str, Any]], n: int = 3) -> list[str]:
    pos = [b for b in breakdown if _contrib(b) > 0]
    pos.sort(key=lambda b: -_contrib(b))
    return [b["signal"] for b in pos[:n]]


def top_drags(breakdown: Sequence[Mapping[str, Any]], n: int = 3) -> list[str]:
    neg = [b for b in breakdown if _contrib(b) < 0]
    neg.sort(key=lambda b: _contrib(b))  # ascending = most negative first
    return [b["signal"] for b in neg[:n]]
