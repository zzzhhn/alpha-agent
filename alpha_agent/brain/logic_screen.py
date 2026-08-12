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

_WALL_CLOCK_S = 180
# Generous cap: Kimi-for-coding (k2.6) is a reasoning model that spends output
# tokens on internal thinking before the JSON — too small a cap returns empty
# content (the screen then degrades to a harmless no-op). 8000 leaves room for
# the reasoning plus a scored array for a full batch.
_OUTPUT_TOKEN_CAP = 8000
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


def _json_payload(content: str):
    """Parse strict JSON, fenced JSON, or a JSON value after brief model prose."""
    cleaned = _strip_md_fence(content or "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, char in enumerate(cleaned):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[idx:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("logic screen response contains no JSON payload")


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
        data = _json_payload(resp.content or "")
    except Exception as e:  # noqa: BLE001 — screen is best-effort, never blocks
        logger.warning("logic screen failed; simulating all candidates: %s", e)
        return {}

    if isinstance(data, dict):
        data = data.get("scores") or data.get("results") or data.get("candidates") or []
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


def select_diverse_by_group(
    expressions: list[str],
    scores: dict[str, float],
    *,
    target_n: int,
    group_of,
) -> list[str]:
    """Rank by logic, then take one candidate per mechanism before repeats.

    This is a cheap pre-simulation novelty gate. It preserves the simulation
    budget while preventing one high-scoring template family from consuming all
    slots. Within each mechanism, the LLM score still determines priority.
    """
    target = min(max(int(target_n), 0), len(expressions))
    ranked = select_by_logic(expressions, scores, target_n=len(expressions))
    buckets: dict[str, list[str]] = {}
    for expr in ranked:
        buckets.setdefault(str(group_of(expr)), []).append(expr)
    selected: list[str] = []
    depth = 0
    while len(selected) < target:
        added = False
        for bucket in buckets.values():
            if depth < len(bucket):
                selected.append(bucket[depth])
                added = True
                if len(selected) >= target:
                    break
        if not added:
            break
        depth += 1
    return selected


_OPTIONS_RESEARCH_PRIORITY = (
    "skew_term_blend",
    "skew_call_innovation_blend",
    "iv_term",
    "iv_momentum",
    "vrp",
    "pcr_dynamics",
    "iv_skew_level",
    "iv_skew_dynamics",
    "option_breakeven",
)


def select_options_research_portfolio(
    expressions: list[str],
    scores: dict[str, float],
    *,
    target_n: int,
    group_of,
) -> list[str]:
    """Allocate a small options budget by evidence, not shuffled bucket order.

    Two anchor-plus-residual candidates receive the first slots, followed by the
    strongest independent mechanisms from the latest BRAIN evidence.  This keeps
    one representative per mechanism before repeats, but no longer gives an
    unvalidated breakeven construction the same chance as a near-miss IV-term
    signal. LLM scores rank variants *within* a mechanism only.
    """
    target = min(max(int(target_n), 0), len(expressions))
    buckets: dict[str, list[str]] = {}
    for expr in expressions:
        buckets.setdefault(str(group_of(expr)), []).append(expr)
    for bucket in buckets.values():
        bucket.sort(key=lambda expr: scores.get(expr, 5.0), reverse=True)

    ordered_groups = [g for g in _OPTIONS_RESEARCH_PRIORITY if g in buckets]
    ordered_groups.extend(g for g in buckets if g not in ordered_groups)
    selected: list[str] = []
    depth = 0
    while len(selected) < target:
        added = False
        for group in ordered_groups:
            bucket = buckets[group]
            if depth < len(bucket):
                selected.append(bucket[depth])
                added = True
                if len(selected) >= target:
                    break
        if not added:
            break
        depth += 1
    return selected


def select_by_logic(
    expressions: list[str],
    scores: dict[str, float],
    *,
    min_score: float = DEFAULT_MIN_SCORE,
    keep_at_least: int = 3,
    target_n: int | None = None,
) -> list[str]:
    """Keep candidates scoring >= min_score, preserving order. Unscored
    expressions (LLM unavailable / didn't return them) pass through — the screen
    only ever REMOVES economically-nonsensical candidates it actively flagged.
    Guarantees at least `keep_at_least` (the best-scored) so a harsh LLM round
    never starves the sim step."""
    if not scores:
        return expressions[:target_n] if target_n is not None else expressions
    if target_n is not None:
        # A screen should rank the pool, not silently shrink the requested
        # simulation budget.  Keep all candidates above the bar first, then
        # backfill from the highest-scored below-bar candidates until target_n
        # is reached.  Python's stable sort preserves generator order for ties.
        target = min(max(int(target_n), 0), len(expressions))
        ranked = sorted(
            enumerate(expressions),
            key=lambda item: scores.get(item[1], min_score),
            reverse=True,
        )
        preferred = [
            item for item in ranked if scores.get(item[1], min_score) >= min_score
        ]
        selected = preferred[:target]
        if len(selected) < target:
            selected_ids = {idx for idx, _ in selected}
            selected.extend(
                item for item in ranked
                if item[0] not in selected_ids
            )
        return [expr for _, expr in selected[:target]]
    kept = [e for e in expressions if scores.get(e, min_score) >= min_score]
    if len(kept) >= keep_at_least:
        return kept
    # Too few passed — fall back to the top-scored keep_at_least.
    ranked = sorted(expressions, key=lambda e: scores.get(e, 0.0), reverse=True)
    return ranked[:keep_at_least]
