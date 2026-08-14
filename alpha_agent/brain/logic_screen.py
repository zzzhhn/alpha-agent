"""Phase E optimization (AlphaEval 'Financial Logic' dimension): pre-screen GA
candidates with an LLM BEFORE the slow BRAIN simulation.

BRAIN sims are the bottleneck (minutes each, serial). Not every generated
expression makes economic sense — a ratio of two unrelated raw prices, a
double-negation, a nonsense field pairing. An LLM that knows finance scores each
candidate's economic logic in bounded sequential batches; we simulate only the ones that
score above a bar. This cuts wasted sims and raises the quality of what surfaces.

Best-effort and OPTIONAL: with no LLM client the screen is a no-op (everything
passes), so the miner still runs unattended without an LLM key.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from alpha_agent.evolution.llm_factor_proposer import _strip_md_fence
from alpha_agent.llm.base import LLMClient, Message
from alpha_agent.brain.hypotheses import (
    audit_expression_semantics,
    hypothesis_for,
    map_expression_fields,
    research_context_key,
)
from alpha_agent.brain.surrogate import proxy_composite

logger = logging.getLogger(__name__)

_WALL_CLOCK_S = 180
# Kimi-for-coding is a reasoning model, so keep each request bounded while
# leaving enough time for a small candidate group.  Requests stay sequential:
# the existing client has no rate-limit coordination and concurrent batches
# would turn one slow screen into a provider burst.
_BATCH_SIZE = 5
_BATCH_TIMEOUT_S = 60.0
_MAX_BATCH_RETRIES = 1
# 8000 leaves room for reasoning plus a scored array for one small batch.
_OUTPUT_TOKEN_CAP = 8000
# Keep candidates scoring at least this (0-10) — 5 = "plausible economic logic".
DEFAULT_MIN_SCORE = 5.0
OPTIONS_MIN_EVIDENCE_SCORE = 5.75


class LogicScreenResult(dict):
    """Mapping-compatible score result with truthful screen lifecycle metadata.

    Existing callers can continue to compare the return value with a plain
    ``dict[str, float]``.  New callers should use ``status``, ``error_type`` and
    ``detail`` to distinguish a completed screen from a bypass, timeout, or
    parse/provider error without persisting exception text that may contain
    credentials or request payloads.
    """

    def __init__(
        self,
        scores: dict[str, float] | None = None,
        *,
        status: str,
        error_type: str | None = None,
        detail: str | None = None,
        telemetry: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(scores or {})
        self.status = status
        self.error_type = error_type
        self.detail = detail
        self.telemetry = dict(telemetry or {})

    @property
    def scores(self) -> dict[str, float]:
        return dict(self)

    def __getitem__(self, key):
        # Expose status metadata through mapping-style access too, while keeping
        # ordinary dict equality/iteration limited to expression scores.
        if key in {"scores", "status", "error_type", "detail", "scored_n", "telemetry"}:
            return self.metadata()[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in {"scores", "status", "error_type", "detail", "scored_n", "telemetry"}:
            return self.metadata().get(key, default)
        return super().get(key, default)

    def __contains__(self, key):
        if key in {"scores", "status", "error_type", "detail", "scored_n", "telemetry"}:
            return True
        return super().__contains__(key)

    def metadata(self) -> dict[str, Any]:
        """JSON-safe status payload for a run/candidate audit record."""
        return {
            "scores": dict(self),
            "status": self.status,
            "error_type": self.error_type,
            "detail": self.detail,
            "scored_n": len(self),
            "telemetry": dict(self.telemetry),
        }

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


def _extract_scores(data: Any, expressions: list[str]) -> dict[str, float]:
    """Extract valid expression scores without retaining model prose."""
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


_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,119}$")


def _safe_label(value: Any) -> str | None:
    """Return a bounded non-secret diagnostic label, never arbitrary text."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _SAFE_LABEL.fullmatch(value) else None


def _client_labels(llm_client: LLMClient) -> tuple[str | None, str | None]:
    """Read provider/model identifiers only when they are already exposed safely."""
    provider = _safe_label(getattr(llm_client, "_provider", None))
    if provider is None:
        provider_by_class = {
            "KimiClient": "kimi",
            "LiteLLMClient": "litellm",
            "OpenAIClient": "openai",
            "OllamaClient": "ollama",
        }
        provider = provider_by_class.get(type(llm_client).__name__)
    model = _safe_label(getattr(llm_client, "_model", None))
    return provider, model


def _failure_kind(exc: BaseException) -> str:
    """Classify retryable failures without inspecting exception messages/bodies."""
    import asyncio

    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    try:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            return "provider_http"
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.TransportError):
            return "transport"
    except ImportError:  # pragma: no cover - httpx is a core dependency
        pass
    if isinstance(exc, (ConnectionError, OSError)):
        return "transport"
    return "error"


async def _score_batch(
    llm_client: LLMClient,
    expressions: list[str],
    *,
    deadline: float,
) -> tuple[dict[str, float], str, str | None, int, bool]:
    """Score one bounded batch, retrying only timeout/transport failures.

    Returns scores, final state, sanitized error type, retry count, and whether
    any attempt timed out. A provider HTTP response or parse failure is never
    retried, even if it is otherwise transient-looking.
    """
    import asyncio

    numbered = "\n".join(f"{i}. {e}" for i, e in enumerate(expressions))
    retries = 0
    timed_out = False
    last_kind = "error"
    last_error_type: str | None = None
    for attempt in range(_MAX_BATCH_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {}, "timeout", "TimeoutError", retries, True
        timeout_s = min(_BATCH_TIMEOUT_S, remaining)
        try:
            response = await asyncio.wait_for(
                llm_client.chat(
                    messages=[Message(role="user", content=_PROMPT % numbered)],
                    max_tokens=_OUTPUT_TOKEN_CAP,
                ),
                timeout=timeout_s,
            )
            data = _json_payload(response.content or "")
            scores = _extract_scores(data, expressions)
            if not scores:
                return {}, "error", "NoUsableScores", retries, timed_out
            return scores, "completed", None, retries, timed_out
        except asyncio.TimeoutError as exc:
            kind = "timeout"
            error_type = type(exc).__name__ or "TimeoutError"
            timed_out = True
        except Exception as exc:  # noqa: BLE001 — persist only type/status
            kind = _failure_kind(exc)
            error_type = type(exc).__name__
            last_kind = kind
            last_error_type = error_type

        last_kind = kind
        last_error_type = error_type
        if kind not in {"timeout", "transport"} or attempt >= _MAX_BATCH_RETRIES:
            final_state = "timeout" if kind == "timeout" else "error"
            return {}, final_state, last_error_type, retries, timed_out
        if deadline - time.monotonic() <= 0.05:
            return {}, "timeout" if kind == "timeout" else "error", last_error_type, retries, timed_out
        retries += 1

    return {}, "timeout" if last_kind == "timeout" else "error", last_error_type, retries, timed_out


def _screen_telemetry(
    *,
    started_at: float,
    batch_count: int,
    completed: int = 0,
    timed_out: int = 0,
    errors: int = 0,
    partial: int = 0,
    retries: int = 0,
    error_types: dict[str, int] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-safe batch telemetry persisted with each candidate."""
    return {
        "elapsed_ms": max(0, round((time.monotonic() - started_at) * 1000)),
        "timeout_s": _BATCH_TIMEOUT_S,
        "batch_count": batch_count,
        "completed_batches": completed,
        "timed_out_batches": timed_out,
        "error_batches": errors,
        "partial_batches": partial,
        "retry_count": retries,
        "error_types": dict(error_types or {}),
        "provider": provider,
        "model": model,
    }


async def score_economic_logic(
    llm_client: Optional[LLMClient], expressions: list[str]
) -> LogicScreenResult:
    """Score expressions in bounded sequential batches.

    A failed batch never discards scores from earlier batches. Unscored
    expressions remain available to the caller's deterministic evidence screen.
    The mapping contains ``{expression: score}`` and remains backward compatible
    with plain-dict callers.  ``status``/``error_type``/``detail`` distinguish a
    completed, partial, bypassed, timeout, or provider-error screen.  Missing
    scores never block mining; the caller records the explicit status instead of
    implying that every candidate was successfully screened."""
    started_at = time.monotonic()
    provider = model = None
    if llm_client is None:
        return LogicScreenResult(
            status="bypassed",
            detail="no logic-screen LLM configured",
            telemetry=_screen_telemetry(
                started_at=started_at,
                batch_count=0,
            ),
        )
    if not expressions:
        return LogicScreenResult(
            status="bypassed",
            detail="no expressions",
            telemetry=_screen_telemetry(started_at=started_at, batch_count=0),
        )
    provider, model = _client_labels(llm_client)
    batches = [
        expressions[offset : offset + _BATCH_SIZE]
        for offset in range(0, len(expressions), _BATCH_SIZE)
    ]
    deadline = started_at + _WALL_CLOCK_S
    scores: dict[str, float] = {}
    completed = timed_out = errors = partial = retries = 0
    error_types: dict[str, int] = {}
    first_error_type: str | None = None

    for batch_index, batch in enumerate(batches):
        batch_scores, state, error_type, batch_retries, saw_timeout = await _score_batch(
            llm_client,
            batch,
            deadline=deadline,
        )
        scores.update(batch_scores)
        retries += batch_retries
        if saw_timeout:
            timed_out += 1
        if state == "completed":
            completed += 1
            if len(batch_scores) < len(batch):
                partial += 1
        elif state == "timeout":
            timed_out += 0 if saw_timeout else 1
        else:
            errors += 1
        if error_type:
            first_error_type = first_error_type or error_type
            error_types[error_type] = error_types.get(error_type, 0) + 1
        if time.monotonic() >= deadline:
            # Remaining batches had no request budget; record them as timed out
            # without manufacturing an exception or leaking provider details.
            timed_out += len(batches) - batch_index - 1
            break

    telemetry = _screen_telemetry(
        started_at=started_at,
        batch_count=len(batches),
        completed=completed,
        timed_out=timed_out,
        errors=errors,
        partial=partial,
        retries=retries,
        error_types=error_types,
        provider=provider,
        model=model,
    )
    if len(scores) == len(expressions):
        status = "completed"
    elif scores:
        status = "partial"
    elif timed_out and not errors:
        status = "timeout"
    else:
        status = "error"
    detail = (
        f"scored {len(scores)}/{len(expressions)} expressions across {len(batches)} batches"
    )
    if timed_out:
        detail += f"; {timed_out} batch(es) timed out"
    if errors:
        detail += f"; {errors} batch(es) failed"
    if retries:
        detail += f"; retried {retries} batch(es)"
    if status == "timeout":
        logger.warning("logic screen unavailable: status=timeout error_type=TimeoutError")
    elif status == "error":
        logger.warning(
            "logic screen unavailable: status=error error_type=%s",
            first_error_type or "UnknownError",
        )
    return LogicScreenResult(
        scores,
        status=status,
        error_type=("TimeoutError" if status == "timeout" else first_error_type),
        detail=detail,
        telemetry=telemetry,
    )


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


def _behavior_cluster(expr: str, mechanism: str) -> str:
    """Cheap behavioral cluster used before PnL exists.

    It deliberately collapses the dominant PCR-gated call-minus-put anchor even
    when a second leg or tenor makes the syntax look different.
    """
    e = expr or ""
    if "trade_when" in e and re.search(r"\bpcr\w*", e) and re.search(
        r"(?:implied|iv)\w*call", e
    ) and re.search(r"(?:implied|iv)\w*put", e):
        return "pcr_skew_anchor"
    return mechanism


def options_candidate_evidence(
    expr: str,
    *,
    logic_score: float,
    mechanism: str,
    field_metadata: list[dict],
    mechanism_evidence: dict,
    candidate_settings: dict | None = None,
    surrogate_prediction: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Score one options candidate before an expensive BRAIN simulation."""
    settings = candidate_settings or {}
    mapping = map_expression_fields(expr, field_metadata)
    semantic = audit_expression_semantics(mechanism, expr, field_metadata)
    coverage = float(mapping["coverage"])
    mapped_ratio = float(mapping["mapped_ratio"])
    coverage_score = max(
        0.0,
        min(10.0, coverage * 10.0 * (0.5 + 0.5 * mapped_ratio)),
    )
    if semantic["status"] == "unverified":
        semantic_score = 5.0
    else:
        semantic_score = 10.0 * float(semantic["semantic_fidelity"])

    mechanisms = mechanism_evidence.get("mechanisms", mechanism_evidence)
    contexts = mechanism_evidence.get("contexts", {})
    hist = mechanisms.get(mechanism, {})

    def posterior_score(item: dict) -> float:
        attempts = int(item.get("attempts", 0) or 0)
        good = int(item.get("good", 0) or 0)
        gates = int(item.get("gates_passed", item.get("passed", 0)) or 0)
        passed = int(item.get("passed", 0) or 0)
        concentrated = int(item.get("concentrated", 0) or 0)
        low_sub = int(item.get("low_sub_universe", 0) or 0)
        high_turnover = int(item.get("high_turnover", 0) or 0)
        score = 10.0 * (
            0.55 * (good + 1.5) / (attempts + 3.0)
            + 0.25 * (gates + 1.0) / (attempts + 4.0)
            + 0.20 * (passed + 0.5) / (attempts + 5.0)
        )
        if attempts:
            score -= 1.5 * concentrated / attempts
            score -= 1.0 * low_sub / attempts
            score -= 0.5 * high_turnover / attempts
        return max(0.0, min(10.0, score))

    history_score = posterior_score(hist)
    context_key = research_context_key(mechanism, expr, field_metadata, settings)
    context_hist = contexts.get(context_key, {})
    context_n = int(context_hist.get("attempts", 0) or 0)
    if context_n >= 3:
        context_weight = min(context_n / 12.0, 0.70)
        history_score = (
            (1.0 - context_weight) * history_score
            + context_weight * posterior_score(context_hist)
        )

    op_count = len(re.findall(r"[a-zA-Z_]\w*\(", expr or ""))
    complexity_score = max(2.0, 10.0 - 0.45 * max(op_count - 3, 0))
    concentration_score = 5.0
    concentration_score += 1.5 if "rank(" in (expr or "") else 0.0
    concentration_score += 1.0 if "group_neutralize(" in (expr or "") else 0.0
    concentration_score -= 2.0 if "trade_when(" in (expr or "") else 0.0
    concentration_score = max(0.0, min(10.0, concentration_score))
    syntactic_cluster = re.sub(r"\d+", "N", expr or "").replace(" ", "")
    behavioral_cluster = _behavior_cluster(expr, mechanism)
    # Keep syntax, pre-PnL behavior, and realized history as separate signals.
    cluster = behavioral_cluster
    novelty_score = 3.0 if behavioral_cluster == "pcr_skew_anchor" else 7.5
    selfcorr_checked = int(hist.get("selfcorr_checked", hist.get("self_corr_checked", 0)) or 0)
    selfcorr_passed = int(hist.get("selfcorr_passed", hist.get("self_corr_passed", 0)) or 0)
    if selfcorr_checked:
        # This is realized-history evidence, distinct from the syntax cluster.
        # A low pass rate means the mechanism has not demonstrated incremental
        # novelty, so do not let a cosmetic structural variant score as novel.
        realized_rate = selfcorr_passed / selfcorr_checked
        novelty_score = min(novelty_score, 2.0 + 5.0 * realized_rate)
        realized_novelty = "supported" if realized_rate >= 0.5 else "redundant"
    else:
        realized_rate = None
        realized_novelty = "unknown"
    alignment_score = _OPTIONS_OUTCOME_ALIGNMENT.get(mechanism, 4.5)
    attempts = int(hist.get("attempts", 0) or 0)
    # These counters can refer to the same failed simulation. Using their sum
    # would double-count one row and could blacklist a mechanism prematurely.
    failure_n = max(
        int(hist.get("concentrated", 0) or 0),
        int(hist.get("low_sub_universe", 0) or 0),
    )
    failure_rate = failure_n / max(attempts, 1)
    historically_failed = bool(
        attempts >= 4 and failure_rate >= 0.50
    )
    if semantic["material_mismatch"] or semantic["target_outcome_alignment"]["status"] != "aligned":
        lane = "explore"
    elif mechanism in {"skew_call_innovation_residual", "skew_term_residual"}:
        lane = "orthogonal"
    elif attempts >= 4 and failure_rate >= 0.30:
        lane = "repair"
    elif hypothesis_for(mechanism).confidence == "low":
        lane = "explore"
    else:
        lane = "orthogonal"

    proxy_score = proxy_composite(surrogate_prediction or {})
    if proxy_score is None:
        total = (
            0.15 * max(0.0, min(10.0, logic_score))
            + 0.15 * coverage_score
            + 0.20 * semantic_score
            + 0.20 * history_score
            + 0.15 * alignment_score
            + 0.10 * concentration_score
            + 0.10 * novelty_score
            + 0.05 * complexity_score
        )
    else:
        total = (
            0.10 * max(0.0, min(10.0, logic_score))
            + 0.15 * coverage_score
            + 0.20 * semantic_score
            + 0.15 * history_score
            + 0.10 * alignment_score
            + 0.10 * concentration_score
            + 0.10 * novelty_score
            + 0.05 * complexity_score
            + 0.15 * proxy_score
        )
    return {
        "score": round(total, 4),
        "coverage": round(coverage, 4),
        "semantic_fidelity": round(float(semantic["semantic_fidelity"]), 4),
        "semantic_score": round(semantic_score, 4),
        "semantic_status": semantic["status"],
        "semantic_mismatch": bool(semantic["material_mismatch"]),
        "high_confidence_mismatch": bool(semantic["high_confidence_mismatch"]),
        "matched_required_semantics": semantic["matched_required_semantics"],
        "missing_required_semantics": semantic["missing_required_semantics"],
        "target_outcome_alignment": semantic["target_outcome_alignment"],
        "field_details": semantic["field_details"],
        "mapped_ratio": round(mapped_ratio, 4),
        "datasets": "+".join(mapping["dataset_ids"]) or "unmapped",
        "history": round(history_score, 4),
        "historically_failed": historically_failed,
        "context_n": context_n,
        "alignment": alignment_score,
        "concentration": round(concentration_score, 4),
        "novelty": novelty_score,
        "realized_novelty": realized_novelty,
        "selfcorr_rate": round(realized_rate, 4) if realized_rate is not None else "unknown",
        "complexity": round(complexity_score, 4),
        "mechanism": mechanism,
        "cluster": cluster,
        "syntactic_cluster": syntactic_cluster,
        "behavioral_cluster": behavioral_cluster,
        "lane": lane,
        "proxy": round(proxy_score, 4) if proxy_score is not None else "inactive",
    }


def select_options_research_portfolio(
    expressions: list[str],
    scores: dict[str, float],
    *,
    target_n: int,
    group_of,
    field_metadata: list[dict] | None = None,
    mechanism_evidence: dict | None = None,
    settings_by_expr: dict[str, dict] | None = None,
    surrogate_predictions: dict[str, dict[str, float]] | None = None,
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
                candidate_settings=(settings_by_expr or {}).get(expr, {}),
                surrogate_prediction=(surrogate_predictions or {}).get(expr),
            )
            ranked.append((float(evidence["score"]), -idx, expr, evidence))
        ranked.sort(reverse=True)
        qualified = [
            item for item in ranked
            if item[0] >= min_evidence_score
            # A high-confidence paper claim with an unfulfilled official
            # semantic requirement must not consume a high-confidence slot.
            and not bool(item[3].get("high_confidence_mismatch"))
            and not bool(item[3].get("historically_failed"))
        ]
        selected: list[str] = []
        cluster_counts: dict[str, int] = {}
        mechanism_counts: dict[str, int] = {}

        def add_from_lane(lane: str, quota: int) -> None:
            for _, _, expr, evidence in qualified:
                if quota <= 0 or len(selected) >= target:
                    break
                if expr in selected or str(evidence["lane"]) != lane:
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
                quota -= 1

        orthogonal_n = min(2, target)
        repair_n = min(2, max(target - orthogonal_n, 0))
        explore_n = min(1, max(target - orthogonal_n - repair_n, 0))
        add_from_lane("orthogonal", orthogonal_n)
        add_from_lane("repair", repair_n)
        add_from_lane("explore", explore_n)
        for _, _, expr, evidence in qualified:
            if expr in selected:
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


def options_candidate_screen_records(
    expressions: list[str],
    scores: dict[str, float],
    *,
    target_n: int,
    group_of,
    field_metadata: list[dict] | None = None,
    mechanism_evidence: dict | None = None,
    settings_by_expr: dict[str, dict] | None = None,
    surrogate_predictions: dict[str, dict[str, float]] | None = None,
    min_evidence_score: float = OPTIONS_MIN_EVIDENCE_SCORE,
    selected: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return durable evidence and an exact portfolio decision for each option.

    The selector historically returned only expressions.  This companion keeps
    that compatibility while exposing the same evidence gates as explicit reason
    codes for the run-candidate ledger.
    """
    metadata = field_metadata or []
    history = mechanism_evidence or {}
    settings_map = settings_by_expr or {}
    predictions = surrogate_predictions or {}
    selected_exprs = selected
    if selected_exprs is None:
        selected_exprs = select_options_research_portfolio(
            expressions,
            scores,
            target_n=target_n,
            group_of=group_of,
            field_metadata=field_metadata,
            mechanism_evidence=mechanism_evidence,
            settings_by_expr=settings_by_expr,
            surrogate_predictions=surrogate_predictions,
            min_evidence_score=min_evidence_score,
        )
    selected_set = set(selected_exprs)

    records: dict[str, dict[str, Any]] = {}
    for expr in expressions:
        mechanism = str(group_of(expr))
        evidence = options_candidate_evidence(
            expr,
            logic_score=scores.get(expr, DEFAULT_MIN_SCORE),
            mechanism=mechanism,
            field_metadata=metadata,
            mechanism_evidence=history,
            candidate_settings=settings_map.get(expr, {}),
            surrogate_prediction=predictions.get(expr),
        )
        records[expr] = {
            "evidence": evidence,
            "evidence_score": float(evidence["score"]),
            "llm_score": scores.get(expr),
            "mechanism": mechanism,
            "selected": expr in selected_set,
        }

    selected_evidence = [
        records[expr]["evidence"] for expr in selected_exprs if expr in records
    ]
    selected_mechanisms: dict[str, int] = {}
    selected_clusters: dict[str, int] = {}
    for item in selected_evidence:
        mechanism = str(item["mechanism"])
        cluster = str(item["cluster"])
        selected_mechanisms[mechanism] = selected_mechanisms.get(mechanism, 0) + 1
        selected_clusters[cluster] = selected_clusters.get(cluster, 0) + 1

    for expr, record in records.items():
        evidence = record["evidence"]
        if record["selected"]:
            code = "selected"
            text = "selected for simulation"
        elif bool(evidence.get("high_confidence_mismatch")):
            code = "high_confidence_semantic_mismatch"
            text = "high-confidence hypothesis is missing required official semantics"
        elif bool(evidence.get("historically_failed")):
            code = "historically_failed"
            text = "mechanism has repeated historical gate failures"
        elif float(evidence["score"]) < min_evidence_score:
            code = "below_evidence_threshold"
            text = f"evidence score {float(evidence['score']):.2f} < {min_evidence_score:.2f}"
        elif selected_clusters.get(str(evidence["cluster"]), 0) >= 1:
            code = "cluster_cap"
            text = f"behavior cluster '{evidence['cluster']}' already selected"
        elif selected_mechanisms.get(str(evidence["mechanism"]), 0) >= 2:
            code = "mechanism_cap"
            text = f"mechanism '{evidence['mechanism']}' already has two selected candidates"
        elif len(selected_exprs) >= min(max(int(target_n), 0), len(expressions)):
            code = "portfolio_budget"
            text = "portfolio budget reached"
        else:
            code = "withheld_by_portfolio"
            text = "withheld by the options diversity portfolio"
        record["reason_code"] = code
        record["reason_text"] = text
    return records


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
