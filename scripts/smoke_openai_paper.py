"""Offline by default; one explicit, non-executing Sol decision replay with --live."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values

from alpha_agent.llm.model_profiles import SOL_PROFILE, estimate_standard_cost
from alpha_agent.paper.bot_models import BotConfig, DecisionParseError, parse_decision
from alpha_agent.paper.bot_policy import MODEL_TIMEOUT_SECONDS
from alpha_agent.paper.bot_prompt import PROMPT_VERSION, build_decision_messages

API_BASE = "https://api.openai.com/v1"
FIXTURE = ROOT / "tests/fixtures/openai_paper_smoke.json"
TOKEN_LIMIT = 4096


def build_client(provider, key, api_base, model, *, reasoning_effort=None):
    # Even importing LiteLLM may fetch its remote price map. Keep the complete
    # default CLI path offline and use the packaged map for explicit live runs.
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
    from alpha_agent.api.byok import _build_byok_client

    return _build_byok_client(provider, key, api_base, model, reasoning_effort=reasoning_effort)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context-file", type=Path, default=FIXTURE)
    p.add_argument("--live", action="store_true", help="Make one billable request; never submit orders")
    p.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    p.add_argument("--reasoning-effort", choices=SOL_PROFILE.reasoning_efforts)
    return p


def prepare(path: Path):
    if path.stat().st_size > 131072:
        raise ValueError("input_too_large")
    run = json.loads(path.read_text())

    def unpack(value):
        return json.loads(value) if isinstance(value, str) else value

    context = unpack(run["context"])
    config = BotConfig.model_validate(unpack(run["config_snapshot"]))
    if not isinstance(context, dict) or not isinstance(context.get("context_id"), str):
        raise ValueError("missing_context_id")
    context_id = str(run["id"])
    if context["context_id"] != context_id or not context_id:
        raise ValueError("context_mismatch")
    calls = run.get("llm_calls", 0)
    if type(calls) is not int or not 0 <= calls <= 3:
        raise ValueError("invalid_call_count")
    if len(json.dumps(context, ensure_ascii=False, allow_nan=False).encode()) > 64000:
        raise ValueError("context_too_large")
    # Change only the in-memory provider/model for this replay.
    config = config.model_copy(update={"provider": "openai", "model": SOL_PROFILE.model})
    return context_id, build_decision_messages(config, context, llm_calls=calls)


def read_key(env_file: Path) -> str:
    # Explicit env file wins; do not accidentally use another shell's account.
    key = (dotenv_values(env_file).get("OPENAI_API_KEY") if env_file.exists()
           else os.environ.get("OPENAI_API_KEY"))
    if not key or not key.strip():
        raise ValueError("credential_missing")
    return key.strip()


def error_category(exc: Exception) -> str:
    """Use structured codes only; upstream messages may contain secrets/payloads."""
    body = getattr(exc, "body", None)
    body = body if isinstance(body, dict) else {}
    error = body.get("error", body)
    code = error.get("code") if isinstance(error, dict) else None
    code = code or getattr(exc, "code", None)
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if code in ("credit_balance_exhausted", "insufficient_quota", "billing_hard_limit_reached"):
        return "quota_exhausted"
    if status == 429:
        return "rate_limited_or_quota"
    if status in (401, 403):
        return "auth_or_access_failed"
    if status == 404:
        return "model_unavailable"
    if isinstance(exc, TimeoutError) or type(exc).__name__ in ("Timeout", "APITimeoutError", "ReadTimeout"):
        return "timeout"
    if type(exc).__name__ == "UnsupportedParamsError":
        return "unsupported_parameters"
    return "request_failed"


async def run_smoke(args) -> tuple[dict, int]:
    report = {
        "mode": "live" if args.live else "dry_run",
        "input_source": "synthetic_fixture" if args.context_file == FIXTURE else "provided_context",
        "model": SOL_PROFILE.model, "reasoning_effort": args.reasoning_effort or "provider_default",
        "prompt_version": PROMPT_VERSION, "max_completion_tokens": TOKEN_LIMIT,
        "llm_calls": 0, "orders_submitted": 0, "production_writes": 0,
    }
    try:
        context_id, messages = prepare(args.context_file)
    except (OSError, ValueError, KeyError, TypeError):
        return {**report, "status": "invalid_input"}, 2
    report["input_bytes"] = sum(len(m.content.encode()) for m in messages)
    if not args.live:
        return {**report, "status": "prepared_not_called"}, 0
    try:
        key = read_key(args.env_file)
    except (OSError, ValueError):
        return {**report, "status": "credential_missing"}, 2

    client = None
    try:
        client = build_client("openai", key, API_BASE, SOL_PROFILE.model,
                              reasoning_effort=args.reasoning_effort)
        del key
        report["llm_calls"] = 1
        response = await asyncio.wait_for(
            client.chat(messages, temperature=0.3, max_tokens=TOKEN_LIMIT),
            timeout=MODEL_TIMEOUT_SECONDS,
        )
        report.update({
            "response_model": response.model if response.model in (SOL_PROFILE.model, f"openai/{SOL_PROFILE.model}") else "other_or_unknown",
            "prompt_tokens": response.prompt_tokens, "completion_tokens": response.completion_tokens,
            "cached_prompt_tokens": response.cached_prompt_tokens, "reasoning_tokens": response.reasoning_tokens,
            "finish_reason": response.finish_reason if response.finish_reason in ("stop", "length", "max_tokens") else "unknown",
            "estimated_cost": estimate_standard_cost(response, api_base=API_BASE),
        })
        if response.finish_reason in ("length", "max_tokens"):
            return {**report, "status": "output_truncated"}, 1
        if report["response_model"] == "other_or_unknown":
            return {**report, "status": "unexpected_model"}, 1
        if response.finish_reason != "stop":
            return {**report, "status": "unexpected_finish_reason"}, 1
        if not response.content or not response.content.strip():
            return {**report, "status": "empty_response"}, 1
        try:
            decision = parse_decision(response.content, context_id)
        except DecisionParseError as exc:
            return {**report, "status": "invalid_decision", "parse_status": exc.kind}, 1
        return {**report, "status": "valid_decision", "parse_status": "valid",
                "decision": decision.decision, "proposed_action_count": len(decision.actions),
                "research_requested_count": len(decision.research_tickers)}, 0
    except Exception as exc:
        return {**report, "status": error_category(exc)}, 1
    finally:
        if client is not None:
            await client.close()


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    started = time.monotonic()
    previous_logging = logging.root.manager.disable
    try:
        # Upstream libraries can print request/error details. The only public
        # output from this command is the allow-listed report below.
        logging.disable(logging.CRITICAL)
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            report, code = asyncio.run(run_smoke(args))
    except Exception:
        report, code = {"status": "smoke_failed", "orders_submitted": 0}, 1
    finally:
        logging.disable(previous_logging)
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
