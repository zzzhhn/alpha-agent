"""CRUD + distillation for the factor_lessons memory layer (Phase A).

The propose loop writes one distilled lesson per candidate outcome; the
proposer reads back recent lessons + the distinct set of already-tried
expressions and injects them into its prompt. This is the persistence that
turns a stateless one-shot proposer into a researcher that compounds.

No ORM: plain asyncpg, mirroring storage/propose_jobs.py. Every function takes
an asyncpg Pool (or Connection — both expose execute/fetch), so callers pass
whatever they hold.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Best-effort operator-name extraction for lesson tagging. This is a hint for
# the memory layer, not a validator (core.factor_ast owns real validation), so
# a cheap regex over `name(` call-heads is sufficient and never raises.
_OP_CALL = re.compile(r"([a-z_][a-z0-9_]*)\s*\(")


def extract_operators(expression: str) -> list[str]:
    """Return the distinct operator/function names called in `expression`,
    in first-seen order. Best-effort; empty on empty/garbage input."""
    seen: list[str] = []
    for m in _OP_CALL.finditer(expression or ""):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def _fmt(v: Optional[float], digits: int) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def distill_lesson(
    *,
    expression: str,
    outcome: str,
    test_sharpe: Optional[float] = None,
    test_ic: Optional[float] = None,
    deflated_sharpe: Optional[float] = None,
    reject_reason: Optional[str] = None,
) -> str:
    """Turn one candidate outcome into a single terse, human- and LLM-legible
    lesson line. The KEEP/WEAK/AVOID prefixes let the proposer scan direction
    at a glance."""
    expr = (expression or "").strip()
    if outcome == "accepted":
        return (
            f"KEEP `{expr}` — OOS Sharpe {_fmt(test_sharpe, 2)}, "
            f"IC {_fmt(test_ic, 3)}; worth extending this structure."
        )
    if outcome == "rejected":
        return f"AVOID `{expr}` — rejected: {reject_reason or 'validation failed'}."
    # weak (evaluated but below the keep gate)
    return (
        f"WEAK `{expr}` — evaluated but OOS Sharpe {_fmt(test_sharpe, 2)} "
        "is below the keep gate; this direction underperforms as-is."
    )


async def record_lesson(
    pool: Any,
    *,
    expression: str,
    outcome: str,
    test_sharpe: Optional[float] = None,
    test_ic: Optional[float] = None,
    deflated_sharpe: Optional[float] = None,
    reject_reason: Optional[str] = None,
    lesson: Optional[str] = None,
) -> None:
    """Persist one lesson. `lesson` defaults to the distilled line; callers may
    pass a richer (e.g. LLM-reflected) lesson in later phases."""
    text = lesson or distill_lesson(
        expression=expression,
        outcome=outcome,
        test_sharpe=test_sharpe,
        test_ic=test_ic,
        deflated_sharpe=deflated_sharpe,
        reject_reason=reject_reason,
    )
    await pool.execute(
        "INSERT INTO factor_lessons "
        "(expression, outcome, test_sharpe, test_ic, deflated_sharpe, "
        " reject_reason, operators_used, lesson) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
        expression,
        outcome,
        test_sharpe,
        test_ic,
        deflated_sharpe,
        reject_reason,
        extract_operators(expression),
        text,
    )


async def load_recent_lessons(pool: Any, limit: int = 12) -> list[str]:
    """Most-recent-first lesson lines for the proposer prompt."""
    rows = await pool.fetch(
        "SELECT lesson FROM factor_lessons ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [r["lesson"] for r in rows]


async def load_tried_expressions(pool: Any, limit: int = 40) -> list[str]:
    """Distinct expressions already tried, ordered by most-recent attempt, so
    the proposer can avoid re-proposing them."""
    rows = await pool.fetch(
        "SELECT expression FROM factor_lessons "
        "GROUP BY expression ORDER BY max(created_at) DESC LIMIT $1",
        limit,
    )
    return [r["expression"] for r in rows]
