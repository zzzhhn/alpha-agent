# alpha_agent/fusion/attribution.py
"""Reverse attribution: which signals drove the rating up/down."""
from __future__ import annotations

from typing import Mapping, Sequence


def top_drivers(breakdown: Sequence[Mapping[str, float]], n: int = 3) -> list[str]:
    pos = [b for b in breakdown if b.get("contribution", 0.0) > 0]
    pos.sort(key=lambda b: -b["contribution"])
    return [b["signal"] for b in pos[:n]]


def top_drags(breakdown: Sequence[Mapping[str, float]], n: int = 3) -> list[str]:
    neg = [b for b in breakdown if b.get("contribution", 0.0) < 0]
    neg.sort(key=lambda b: b["contribution"])  # ascending = most negative first
    return [b["signal"] for b in neg[:n]]
