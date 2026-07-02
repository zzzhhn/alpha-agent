"""Phase B2: an adversarial skeptic pass.

Loop Engineering's most important rule: don't let the same agent that GENERATES
a factor also decide it's good — a backtest that looks great can be look-ahead
bias, data leakage, survivorship, cost-blindness, or parameters tuned to the
past. The code gates (purged walk-forward + deflated Sharpe + self-correlation)
catch the mechanical failures; this LLM pass adds a semantic second opinion,
prompted as a skeptic whose only job is to find why the result might be lying.

It NEVER blocks a proposal — the human is the final gate. It annotates each
survivor with a risk_level + concerns so the briefing can surface the
"looks-good-but-flagged-risky" bucket. Pure: takes an LLMClient + evidence,
returns a verdict; no DB, no HTTP. Any failure returns None (skip) so it can
never break a propose.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from alpha_agent.evolution.llm_factor_proposer import _strip_md_fence
from alpha_agent.llm.base import LLMClient, Message

_log = logging.getLogger(__name__)

_WALL_CLOCK_S = 60
_OUTPUT_TOKEN_CAP = 800
_RISK_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class SkepticVerdict:
    risk_level: str  # low | medium | high
    concerns: list[str] = field(default_factory=list)
    summary: str = ""

    def to_jsonable(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "concerns": list(self.concerns),
            "summary": self.summary,
        }


def _build_prompt(expression: str, evidence: dict) -> str:
    return (
        "You are a skeptical quant risk reviewer. You did NOT create this factor."
        " Your only job is to find why its backtest might be LYING. A good-looking"
        " result can be look-ahead bias, data leakage, survivorship, cost-"
        "blindness, or parameters tuned to fit the past.\n\n"
        f"CANDIDATE EXPRESSION: {expression}\n\n"
        "BACKTEST EVIDENCE (out-of-sample, purged walk-forward):\n"
        f"  per-fold Sharpe: {evidence.get('sharpes')}\n"
        f"  OOS IC: {evidence.get('ic_oos')}\n"
        f"  deflated Sharpe: {evidence.get('deflated_sharpe')}\n"
        f"  self-correlation vs saved factors: {evidence.get('self_correlation')} "
        f"(vs {evidence.get('self_correlation_with')})\n\n"
        "Assess the risk that this result will NOT survive live trading. Output"
        " STRICT JSON only:\n"
        '{"risk_level": "low"|"medium"|"high", "concerns": ["..."], "summary": "one line"}\n'
        "- concerns: 0 to 4 short, concrete risks grounded ONLY in the evidence"
        ' (e.g. "one strong fold, others flat — likely regime-fit", "deflated'
        ' Sharpe near zero", "moderate self-correlation with a saved factor").\n'
        "- Do not invent numbers. If the evidence looks clean, say risk_level"
        ' "low" with few or no concerns.\n'
        "- JSON only, no prose, no markdown fences. First char {, last char }."
    )


async def assess_candidate(
    llm_client: LLMClient, expression: str, evidence: dict
) -> SkepticVerdict | None:
    """One skeptic round-trip. Returns None (skip, don't block) on timeout,
    empty content, or unparseable output."""
    prompt = _build_prompt(expression, evidence)
    try:
        resp = await asyncio.wait_for(
            llm_client.chat(
                messages=[Message(role="user", content=prompt)],
                max_tokens=_OUTPUT_TOKEN_CAP,
            ),
            timeout=_WALL_CLOCK_S,
        )
    except Exception as e:  # noqa: BLE001 - skeptic must never block a propose
        _log.warning("skeptic assess chat failed: %s", e)
        return None

    raw = (resp.content or "").strip()
    if not raw:
        _log.warning("skeptic assess: empty LLM content")
        return None
    try:
        data = json.loads(_strip_md_fence(raw))
    except (json.JSONDecodeError, ValueError) as e:
        _log.debug("skeptic assess: unparseable output (%s): %s", e, raw[:120])
        return None
    if not isinstance(data, dict):
        return None

    level = data.get("risk_level", "")
    if level not in _RISK_LEVELS:
        level = "medium"
    raw_concerns = data.get("concerns", [])
    concerns = (
        [str(c)[:200] for c in raw_concerns if isinstance(c, str)][:4]
        if isinstance(raw_concerns, list)
        else []
    )
    summary = str(data.get("summary", ""))[:300]
    return SkepticVerdict(risk_level=level, concerns=concerns, summary=summary)
