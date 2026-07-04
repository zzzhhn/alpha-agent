"""Phase E optimization (AlphaEval 'Financial Logic' dimension): pre-screen GA
candidates with an LLM BEFORE the slow BRAIN simulation.

BRAIN sims are the bottleneck (minutes each, serial). Not every generated
expression makes economic sense — a ratio of two unrelated raw prices, a
double-negation, a nonsense field pairing. An LLM that knows finance scores each
candidate's economic logic in ONE batched call; we simulate only the ones that
score above a bar. This cuts wasted sims and raises the quality of what surfaces.

Best-effort and OPTIONAL: with no LLM client the screen is a no-op (everything
passes), so the miner still runs unattended without an LLM key.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from alpha_agent.evolution.llm_factor_proposer import _strip_md_fence
from alpha_agent.llm.base import LLMClient, Message

logger = logging.getLogger(__name__)

_WALL_CLOCK_S = 90
# Generous cap: Kimi-for-coding (k2.6) is a reasoning model that spends output
# tokens on internal thinking before the JSON — too small a cap returns empty
# content (the screen then degrades to a harmless no-op). 4000 leaves room for
# the reasoning plus a scored array for a full batch.
_OUTPUT_TOKEN_CAP = 4000
# Keep candidates scoring at least this (0-10) — 5 = "plausible economic logic".
DEFAULT_MIN_SCORE = 5.0

_PROMPT = """You are a quantitative equity researcher screening candidate alpha \
factors before an expensive backtest. For EACH expression below, judge its \
ECONOMIC LOGIC only (not its likely performance): does it encode a coherent, \
interpretable financial signal (value, quality, profitability, momentum, \
sentiment, etc.), or is it a nonsensical combination (unrelated fields divided, \
double transforms with no meaning, degenerate)?

Score each 0-10: 0 = economically meaningless, 5 = plausible, 10 = clean, \
well-motivated signal a PM would recognize. Fields prefixed fnd6_/fundamental \
are company fundamentals, anl4_ are analyst estimates, news/option are \
alternative data. group_rank(...,subindustry) neutralizes within peer groups.

Return ONLY a JSON array, one object per expression IN ORDER:
[{"i": 0, "score": 7, "why": "earnings yield, group-neutralized"}, ...]

Expressions:
%s
"""


async def score_economic_logic(
    llm_client: Optional[LLMClient], expressions: list[str]
) -> dict[str, float]:
    """Score each expression's economic logic 0-10 in one batched LLM call.
    Returns {expression: score}. With no client, or on any failure, returns {}
    (caller treats missing scores as passing — the screen never blocks mining)."""
    if llm_client is None or not expressions:
        return {}
    numbered = "\n".join(f"{i}. {e}" for i, e in enumerate(expressions))
    try:
        import asyncio

        resp = await asyncio.wait_for(
            llm_client.chat(
                messages=[Message(role="user", content=_PROMPT % numbered)],
                max_tokens=_OUTPUT_TOKEN_CAP,
            ),
            timeout=_WALL_CLOCK_S,
        )
        data = json.loads(_strip_md_fence(resp.content or ""))
    except Exception as e:  # noqa: BLE001 — screen is best-effort, never blocks
        logger.warning("logic screen failed; simulating all candidates: %s", e)
        return {}

    out: dict[str, float] = {}
    for item in data if isinstance(data, list) else []:
        try:
            idx = int(item["i"])
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < len(expressions):
            out[expressions[idx]] = score
    return out


def select_by_logic(
    expressions: list[str],
    scores: dict[str, float],
    *,
    min_score: float = DEFAULT_MIN_SCORE,
    keep_at_least: int = 3,
) -> list[str]:
    """Keep candidates scoring >= min_score, preserving order. Unscored
    expressions (LLM unavailable / didn't return them) pass through — the screen
    only ever REMOVES economically-nonsensical candidates it actively flagged.
    Guarantees at least `keep_at_least` (the best-scored) so a harsh LLM round
    never starves the sim step."""
    if not scores:
        return expressions
    kept = [e for e in expressions if scores.get(e, min_score) >= min_score]
    if len(kept) >= keep_at_least:
        return kept
    # Too few passed — fall back to the top-scored keep_at_least.
    ranked = sorted(expressions, key=lambda e: scores.get(e, 0.0), reverse=True)
    return ranked[:keep_at_least]
