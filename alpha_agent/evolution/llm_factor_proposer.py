"""Phase 3c LLM factor proposer. Consumes a Diagnostic + a BYOK LLMClient,
returns a list of RawProposal. Pure async function; no DB, no sandbox, no HTTP.

Hard caps:
  n up to 8 per call (clamp to [1, 8]).
  max_tokens 8000 (room for n=5 proposals + operator code).
  Wall-clock 60 s on the LLM call.

Server-side validation:
  - Top-level JSON must have proposals: list.
  - Each proposal must have expression (non-empty str).
  - new_operators must be a list (default empty); each entry's name must
    match ^lf_[a-z_][a-z0-9_]{1,30}$ and must have python_impl + signature.
  - Non-conforming new_operator entries are DROPPED (forgiveness UX).
  - One retry on JSON parse failure; second failure raises ValueError so the
    calling endpoint can return a structured 502."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from alpha_agent.evolution.diagnostics import Diagnostic
from alpha_agent.llm.base import LLMClient, Message

_LF_NAME = re.compile(r"^lf_[a-z_][a-z0-9_]{1,30}$")
_HARD_N_CAP = 8
_OUTPUT_TOKEN_CAP = 8000
_WALL_CLOCK_S = 60


@dataclass(frozen=True)
class RawProposal:
    expression: str
    new_operators: list[dict] = field(default_factory=list)
    rationale: str = ""


def _build_prompt(d: Diagnostic, n: int) -> str:
    return (
        "You are an alpha-research factor inventor. Given the diagnostic below,"
        f" propose {n} candidate factor expressions, each optionally introducing"
        " 0 to 2 new operators (sandboxed at runtime; must be pure NumPy).\n\n"
        "DIAGNOSTIC:\n"
        f"  current_expression: {d.current_expression}\n"
        f"  weak_signal: {d.weak_signal} (IC={d.weak_signal_ic})\n"
        f"  symptom: {d.symptom_summary}\n\n"
        "CONSTRAINTS:\n"
        "- Output strict JSON: {\"proposals\":[{...}, ...]}.\n"
        "- Each proposal: {expression, new_operators, rationale}.\n"
        "- Operators may use the existing AST DSL (rank, ts_mean, ts_std, "
        "subtract, add, multiply, divide, etc.) plus any new_operators you declare.\n"
        "- New operator names must match ^lf_[a-z_][a-z0-9_]{1,30}$ (lf_ prefix).\n"
        "- New operator python_impl must be a function definition whose name "
        "matches the declared name, with numpy as its only import.\n"
        "- No I/O, no network, no subprocess.\n"
        "- Return JSON only, no prose."
    )


def _validate_new_ops(raw: list) -> list[dict]:
    """Drop entries that fail the name regex or are missing required fields."""
    ok: list[dict] = []
    if not isinstance(raw, list):
        return ok
    for op in raw:
        if not isinstance(op, dict):
            continue
        name = op.get("name", "")
        if not isinstance(name, str) or not _LF_NAME.match(name):
            continue
        if not isinstance(op.get("python_impl", ""), str):
            continue
        if not isinstance(op.get("signature", ""), str):
            continue
        ok.append({
            "name": name,
            "signature": op.get("signature", ""),
            "python_impl": op["python_impl"],
            "doc": op.get("doc", "") or "",
        })
    return ok


def _parse_response(text: str, n: int) -> list[RawProposal]:
    data = json.loads(text)
    raws = data.get("proposals", [])
    out: list[RawProposal] = []
    if not isinstance(raws, list):
        raise ValueError("response.proposals is not a list")
    for p in raws[:n]:
        if not isinstance(p, dict):
            continue
        expr = p.get("expression", "")
        if not isinstance(expr, str) or not expr.strip():
            continue
        out.append(RawProposal(
            expression=expr.strip(),
            new_operators=_validate_new_ops(p.get("new_operators", [])),
            rationale=str(p.get("rationale", ""))[:1000],
        ))
    return out


async def propose_factors(
    llm_client: LLMClient, diagnostic: Diagnostic, n: int = 5,
) -> list[RawProposal]:
    """Run one LLM round-trip with at most one structured retry on JSON parse
    failure. Raises ValueError on the second failure so the caller can return
    a structured 502."""
    n = min(max(int(n), 1), _HARD_N_CAP)
    prompt = _build_prompt(diagnostic, n)
    msgs = [Message(role="user", content=prompt)]
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = await asyncio.wait_for(
                llm_client.chat(messages=msgs, max_tokens=_OUTPUT_TOKEN_CAP),
                timeout=_WALL_CLOCK_S,
            )
            return _parse_response(resp.content, n)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            continue
    raise ValueError(f"could not parse LLM response after retry: {last_err}")
