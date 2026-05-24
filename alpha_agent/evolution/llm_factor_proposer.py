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
import logging
import re
import sys
from dataclasses import dataclass, field

from alpha_agent.evolution.diagnostics import Diagnostic
from alpha_agent.llm.base import LLMClient, Message

# Vercel surfaces logger output to runtime logs only when written to stderr.
# Use both a logger and direct stderr print for the failure path so the raw
# upstream content is visible in `vercel logs` regardless of log config.
_log = logging.getLogger(__name__)


def _emit_diag(msg: str) -> None:
    """Best-effort diagnostic emit (logger + stderr) for Vercel visibility."""
    try:
        _log.error(msg)
    except Exception:  # noqa: BLE001 - logger should never block recovery path
        pass
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass

_LF_NAME = re.compile(r"^lf_[a-z_][a-z0-9_]{1,30}$")
_HARD_N_CAP = 8
_OUTPUT_TOKEN_CAP = 8000
# 240s wall clock to cover Kimi-for-Coding generating up to _OUTPUT_TOKEN_CAP
# tokens (observed 60-90s typical, 150s p99). Sits well under the Vercel
# function maxDuration (300s) so the lambda can return a clean 504 instead
# of being killed mid-response. Increased from 60s after 2026-05-24 incident:
# 60s was below Kimi's typical 8000-token generation time, asyncio.TimeoutError
# was bubbling up unhandled and the user saw an opaque 500 with empty body.
_WALL_CLOCK_S = 240


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


def _strip_md_fence(text: str) -> str:
    """LLMs commonly wrap JSON output in markdown fenced code blocks. Strip
    the opening ```json (or bare ```) and closing ``` so json.loads succeeds.

    Handles:
      ```json\n{...}\n```
      ```\n{...}\n```
      {...}                  (passthrough)
      ```json\n{...}         (open-only, in case content was truncated)
    """
    s = text.strip()
    if s.startswith("```"):
        # Drop the opening fence line, including optional language hint.
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1 :]
        else:
            # Single-line fence with no newline; just strip the leading marker.
            s = s.lstrip("`").lstrip()
    if s.endswith("```"):
        s = s[: -3].rstrip()
    return s


def _parse_response(text: str, n: int) -> list[RawProposal]:
    data = json.loads(_strip_md_fence(text))
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
    last_preview: str = ""
    for attempt in range(2):
        resp = None
        try:
            resp = await asyncio.wait_for(
                llm_client.chat(messages=msgs, max_tokens=_OUTPUT_TOKEN_CAP),
                timeout=_WALL_CLOCK_S,
            )
            # Capture upstream signature even on success-path failure: empty
            # content is a known silent-failure mode from Kimi-for-Coding
            # (UA gate, quota exhaustion) — surface it before json.loads
            # erases the evidence.
            raw = (resp.content or "")
            last_preview = raw[:500]
            if not raw.strip():
                _emit_diag(
                    f"[propose_factors] attempt={attempt} EMPTY LLM content; "
                    f"resp_type={type(resp).__name__} raw_len={len(raw)} "
                    f"resp_repr={repr(resp)[:300]}"
                )
                last_err = ValueError("LLM returned empty content")
                continue
            return _parse_response(raw, n)
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            _emit_diag(
                f"[propose_factors] attempt={attempt} parse_failed err={type(e).__name__}: {e}; "
                f"raw_preview={last_preview!r}"
            )
            continue
    # Final detail carries the upstream evidence so the 502 detail field tells
    # the user what actually happened, not just the parser symptom.
    raise ValueError(
        f"could not parse LLM response after retry: {last_err}; "
        f"raw_preview={last_preview[:200]!r}"
    )
