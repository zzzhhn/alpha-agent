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
import re
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
OPTIONS_MIN_EVIDENCE_SCORE = 5.75

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
    "skew_call_innovation_residual",
    "skew_term_residual",
    # Historical names remain readable in old ledgers and compatibility callers.
    "skew_term_blend",
    "skew_call_innovation_blend",
    "iv_skew_level",
    "iv_momentum",
    "iv_term",
    "vrp",
    "pcr_dynamics",
    "iv_skew_level",
    "iv_skew_dynamics",
    "option_breakeven",
)

_OPTIONS_OUTCOME_ALIGNMENT = {
    "skew_call_innovation_residual": 8.5,
    "iv_momentum": 8.0,
    "iv_skew_level": 8.0,
    "iv_skew_dynamics": 6.0,
    "skew_term_residual": 5.0,
    "pcr_dynamics": 3.5,
    "iv_term": 3.0,
    "vrp": 2.5,
    "option_breakeven": 3.0,
}


def _option_tokens(expr: str) -> set[str]:
    return set(re.findall(
        r"\b(?:implied_volatility\w*|historical_volatility\w*|pcr_oi_\w+|"
        r"call_breakeven_\w+|forward_price_\w+)\b",
        expr or "",
    ))


def _behavior_cluster(expr: str, mechanism: str) -> str:
    """Cheap behavioral cluster used before PnL exists.

    It deliberately collapses the dominant PCR-gated call-minus-put anchor even
    when a second leg or tenor makes the syntax look different.
    """
    e = expr or ""
    if "trade_when" in e and "pcr_oi_" in e and "implied_volatility_call" in e \
            and "implied_volatility_put" in e:
        return "pcr_skew_anchor"
    return mechanism


def options_candidate_evidence(
    expr: str,
    *,
    logic_score: float,
    mechanism: str,
    field_metadata: list[dict],
    mechanism_evidence: dict[str, dict[str, float | int]],
) -> dict[str, float | str]:
    """Score one options candidate before an expensive BRAIN simulation."""
    metadata = {str(item.get("id")): item for item in field_metadata}
    tokens = _option_tokens(expr)
    matched = [metadata[token] for token in tokens if token in metadata]
    mapped_ratio = len(matched) / len(tokens) if tokens else 0.0
    coverage = min(
        (float(item.get("coverage") or 0.0) for item in matched),
        # If the catalogue itself is unavailable, retain a neutral prior and
        # mark the run partial upstream.  If a catalogue was loaded but a field
        # is absent, fail that part of the evidence instead of fabricating 50%.
        default=0.50 if not field_metadata else 0.0,
    )
    coverage_score = max(
        0.0,
        min(10.0, coverage * 10.0 * (0.5 + 0.5 * mapped_ratio)),
    )

    hist = mechanism_evidence.get(mechanism, {})
    attempts = int(hist.get("attempts", 0) or 0)
    good = int(hist.get("good", 0) or 0)
    passed = int(hist.get("passed", 0) or 0)
    concentrated = int(hist.get("concentrated", 0) or 0)
    low_sub = int(hist.get("low_sub_universe", 0) or 0)
    good_posterior = (good + 1.5) / (attempts + 3.0)
    pass_posterior = (passed + 0.5) / (attempts + 5.0)
    history_score = 10.0 * (0.75 * good_posterior + 0.25 * pass_posterior)
    if attempts:
        history_score -= 1.5 * concentrated / attempts
        history_score -= 1.0 * low_sub / attempts
    history_score = max(0.0, min(10.0, history_score))

    op_count = len(re.findall(r"[a-zA-Z_]\w*\(", expr or ""))
    complexity_score = max(2.0, 10.0 - 0.45 * max(op_count - 3, 0))
    concentration_score = 5.0
    concentration_score += 1.5 if "rank(" in (expr or "") else 0.0
    concentration_score += 1.0 if "group_neutralize(" in (expr or "") else 0.0
    concentration_score -= 2.0 if "trade_when(" in (expr or "") else 0.0
    concentration_score = max(0.0, min(10.0, concentration_score))
    cluster = _behavior_cluster(expr, mechanism)
    novelty_score = 3.0 if cluster == "pcr_skew_anchor" else 7.5
    alignment_score = _OPTIONS_OUTCOME_ALIGNMENT.get(mechanism, 4.5)

    total = (
        0.20 * max(0.0, min(10.0, logic_score))
        + 0.20 * coverage_score
        + 0.20 * history_score
        + 0.15 * alignment_score
        + 0.10 * concentration_score
        + 0.10 * novelty_score
        + 0.05 * complexity_score
    )
    return {
        "score": round(total, 4),
        "coverage": round(coverage, 4),
        "mapped_ratio": round(mapped_ratio, 4),
        "history": round(history_score, 4),
        "alignment": alignment_score,
        "concentration": round(concentration_score, 4),
        "novelty": novelty_score,
        "complexity": round(complexity_score, 4),
        "mechanism": mechanism,
        "cluster": cluster,
    }


def select_options_research_portfolio(
    expressions: list[str],
    scores: dict[str, float],
    *,
    target_n: int,
    group_of,
    field_metadata: list[dict] | None = None,
    mechanism_evidence: dict[str, dict[str, float | int]] | None = None,
    min_evidence_score: float = OPTIONS_MIN_EVIDENCE_SCORE,
) -> list[str]:
    """Allocate an options budget as a ceiling, not a spending quota.

    With field/history evidence, weak candidates are withheld and behaviorally
    equivalent anchor variants share one slot.  The compatibility path without
    evidence retains the old deterministic mechanism ordering for callers that
    cannot yet expose metadata.
    """
    target = min(max(int(target_n), 0), len(expressions))
    if field_metadata is not None or mechanism_evidence is not None:
        metadata = field_metadata or []
        history = mechanism_evidence or {}
        ranked: list[tuple[float, int, str, dict[str, float | str]]] = []
        for idx, expr in enumerate(expressions):
            mechanism = str(group_of(expr))
            evidence = options_candidate_evidence(
                expr,
                logic_score=scores.get(expr, DEFAULT_MIN_SCORE),
                mechanism=mechanism,
                field_metadata=metadata,
                mechanism_evidence=history,
            )
            ranked.append((float(evidence["score"]), -idx, expr, evidence))
        ranked.sort(reverse=True)
        selected: list[str] = []
        cluster_counts: dict[str, int] = {}
        mechanism_counts: dict[str, int] = {}
        for score, _, expr, evidence in ranked:
            if score < min_evidence_score:
                continue
            cluster = str(evidence["cluster"])
            mechanism = str(evidence["mechanism"])
            if cluster_counts.get(cluster, 0) >= 1:
                continue
            if mechanism_counts.get(mechanism, 0) >= 2:
                continue
            selected.append(expr)
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
            mechanism_counts[mechanism] = mechanism_counts.get(mechanism, 0) + 1
            if len(selected) >= target:
                break
        return selected

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
