"""Phase E: the LLM financial-logic pre-screen (AlphaEval 'Financial Logic').
Scores candidates' economic sense before the slow BRAIN sim; must be a safe
no-op without an LLM and must never starve the sim step."""
import asyncio

import httpx
import pytest

from alpha_agent.brain.logic_screen import (
    DEFAULT_MIN_SCORE,
    score_economic_logic,
    select_by_logic,
    select_diverse_by_group,
    select_options_research_portfolio,
)
from alpha_agent.llm.base import LLMResponse


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    async def chat(self, messages, **kw):
        return LLMResponse(
            content=self._content, model="fake", prompt_tokens=0, completion_tokens=0
        )


class _SequenceLLM:
    def __init__(self, responses):
        self._responses = iter(responses)
        self._provider = "test"
        self._model = "test-model"
        self.calls = 0
        self.messages = []

    async def chat(self, messages, **kw):
        self.calls += 1
        self.messages.append(messages)
        response = next(self._responses)
        if isinstance(response, BaseException):
            raise response
        return LLMResponse(
            content=response, model=self._model, prompt_tokens=0, completion_tokens=0
        )


# ── select_by_logic (pure) ────────────────────────────────────────────────
def test_select_no_scores_passes_everything():
    exprs = ["a", "b", "c"]
    assert select_by_logic(exprs, {}) == exprs  # no LLM => no-op


def test_select_filters_below_min_and_keeps_order():
    exprs = ["good1", "bad", "good2"]
    scores = {"good1": 8.0, "bad": 2.0, "good2": 6.0}
    # keep_at_least=1 so the floor doesn't re-admit the filtered-out 'bad'
    assert select_by_logic(exprs, scores, min_score=5.0, keep_at_least=1) == [
        "good1", "good2",
    ]


def test_select_unscored_expr_passes_through():
    # an expression the LLM didn't return a score for is not actively rejected
    exprs = ["scored_low", "unscored"]
    assert select_by_logic(exprs, {"scored_low": 1.0}, keep_at_least=1) == ["unscored"]


def test_select_keep_at_least_floor():
    exprs = ["a", "b", "c", "d"]
    scores = {e: 1.0 for e in exprs}  # all below bar
    kept = select_by_logic(exprs, scores, min_score=5.0, keep_at_least=2)
    assert len(kept) == 2  # never starves the sim step


def test_select_diverse_by_group_uses_mechanisms_before_repeats():
    exprs = ["skew-a", "skew-b", "vrp-a", "term-a", "term-b"]
    scores = {"skew-a": 10, "skew-b": 9, "vrp-a": 7, "term-a": 6, "term-b": 5}
    groups = {"skew-a": "skew", "skew-b": "skew", "vrp-a": "vrp",
              "term-a": "term", "term-b": "term"}
    selected = select_diverse_by_group(
        exprs, scores, target_n=3, group_of=groups.__getitem__)
    assert selected == ["skew-a", "vrp-a", "term-a"]


def test_options_small_budget_prefers_anchors_and_near_miss_mechanisms():
    exprs = ["pcr", "term", "skew-term", "vrp", "skew-mom", "breakeven"]
    groups = {
        "pcr": "pcr_dynamics", "term": "iv_term",
        "skew-term": "skew_term_blend", "vrp": "vrp",
        "skew-mom": "skew_call_innovation_blend",
        "breakeven": "option_breakeven",
    }
    selected = select_options_research_portfolio(
        exprs, {}, target_n=5, group_of=groups.__getitem__)
    assert selected == ["skew-term", "skew-mom", "term", "vrp", "pcr"]


def test_options_evidence_screen_treats_budget_as_ceiling():
    exprs = [
        "rank(implied_volatility_call_60)",
        "reverse(rank(ts_delta(pcr_oi_120, 20)))",
        "group_neutralize(rank(ts_delta(implied_volatility_call_60, 20)), subindustry)",
    ]
    groups = {
        exprs[0]: "iv_term",
        exprs[1]: "pcr_dynamics",
        exprs[2]: "iv_momentum",
    }
    metadata = [
        {"id": "implied_volatility_call_60", "coverage": 0.92},
        {"id": "pcr_oi_120", "coverage": 0.36},
    ]
    history = {
        "iv_term": {"attempts": 8, "good": 0, "passed": 0,
                    "concentrated": 4, "low_sub_universe": 4},
        "pcr_dynamics": {"attempts": 8, "good": 0, "passed": 0,
                         "concentrated": 5, "low_sub_universe": 1},
        "iv_momentum": {"attempts": 2, "good": 1, "passed": 0,
                        "concentrated": 0, "low_sub_universe": 0},
    }
    selected = select_options_research_portfolio(
        exprs,
        {expr: 7.0 for expr in exprs},
        target_n=3,
        group_of=groups.__getitem__,
        field_metadata=metadata,
        mechanism_evidence=history,
    )
    assert selected == [exprs[2]]


# ── score_economic_logic (LLM I/O) ────────────────────────────────────────
@pytest.mark.asyncio
async def test_score_no_client_is_noop():
    assert await score_economic_logic(None, ["a", "b"]) == {}


@pytest.mark.asyncio
async def test_score_parses_json_array():
    llm = _FakeLLM('[{"i":0,"score":8,"why":"value"},{"i":1,"score":3,"why":"noise"}]')
    scores = await score_economic_logic(llm, ["group_rank(x,sub)", "divide(a,a)"])
    assert scores == {"group_rank(x,sub)": 8.0, "divide(a,a)": 3.0}


@pytest.mark.asyncio
async def test_score_parses_wrapped_json_after_model_prose():
    llm = _FakeLLM('Analysis complete. {"scores":[{"i":0,"score":8}]}')
    assert await score_economic_logic(llm, ["rank(x)"]) == {"rank(x)": 8.0}


@pytest.mark.asyncio
async def test_score_bad_json_degrades_to_empty():
    llm = _FakeLLM("not json at all")
    result = await score_economic_logic(llm, ["a"])
    assert result == {}
    assert result.status == "error"
    assert result.error_type == "ValueError"
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_score_timeout_is_truthful_and_type_only(monkeypatch):
    llm = _SequenceLLM([asyncio.TimeoutError()])
    result = await score_economic_logic(llm, ["a"])
    assert result == {}
    assert result.status == "timeout"
    assert result["error_type"] == "TimeoutError"
    assert "secret" not in (result.detail or "")
    assert llm.calls == 1
    assert result.telemetry["mode"] == "full_pool"
    assert result.telemetry["call_count"] == 1
    assert result.telemetry["timeout_s"] == 240.0
    assert result.telemetry["expression_n"] == 1
    assert result.telemetry["scored_n"] == 0
    assert result.telemetry["completed_calls"] == 0
    assert result.telemetry["timed_out_calls"] == 1
    assert result.telemetry["error_calls"] == 0
    assert "retry_count" not in result.telemetry


@pytest.mark.asyncio
async def test_score_uses_one_patient_outer_timeout(monkeypatch):
    llm = _SequenceLLM(['[{"i":0,"score":8}]'])
    observed = []

    async def _capture_timeout(awaitable, *, timeout):
        observed.append(timeout)
        return await awaitable

    monkeypatch.setattr(asyncio, "wait_for", _capture_timeout)
    result = await score_economic_logic(llm, ["expr"])

    assert result.status == "completed"
    assert observed == [240.0]
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_score_full_pool_uses_one_call_and_keeps_all_scores():
    llm = _SequenceLLM([
        '[{"i":0,"score":8},{"i":1,"score":7},{"i":2,"score":6},'
        '{"i":3,"score":5},{"i":4,"score":4},{"i":5,"score":3}]',
    ])
    expressions = [f"expr-{i}" for i in range(6)]
    result = await score_economic_logic(llm, expressions)

    assert result.status == "completed"
    assert result == {
        "expr-0": 8.0,
        "expr-1": 7.0,
        "expr-2": 6.0,
        "expr-3": 5.0,
        "expr-4": 4.0,
        "expr-5": 3.0,
    }
    assert llm.calls == 1
    prompt = llm.messages[0][0].content
    assert prompt.count("Expressions:") == 1
    assert all(expression in prompt for expression in expressions)
    assert result.telemetry["mode"] == "full_pool"
    assert result.telemetry["call_count"] == 1
    assert result.telemetry["expression_n"] == 6
    assert result.telemetry["scored_n"] == 6
    assert result.telemetry["completed_calls"] == 1
    assert result.telemetry["timed_out_calls"] == 0
    assert result.telemetry["error_calls"] == 0
    assert result.telemetry["partial"] is False
    assert result.telemetry["provider"] == "test"
    assert result.telemetry["model"] == "test-model"


@pytest.mark.asyncio
async def test_score_partial_response_is_retained_without_retry():
    llm = _SequenceLLM([
        '[{"i":0,"score":9},{"i":2,"score":7}]',
    ])
    expressions = [f"expr-{i}" for i in range(4)]
    result = await score_economic_logic(llm, expressions)

    assert result.status == "partial"
    assert result == {"expr-0": 9.0, "expr-2": 7.0}
    assert llm.calls == 1
    assert result.telemetry["completed_calls"] == 1
    assert result.telemetry["timed_out_calls"] == 0
    assert result.telemetry["error_calls"] == 0
    assert result.telemetry["partial"] is True
    assert result.telemetry["scored_n"] == 2
    assert "retry_count" not in result.telemetry


@pytest.mark.asyncio
async def test_score_provider_http_error_is_not_retried():
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    error = httpx.HTTPStatusError("provider response", request=response.request, response=response)
    llm = _SequenceLLM([error])

    result = await score_economic_logic(llm, ["expr"])

    assert result.status == "error"
    assert result.error_type == "HTTPStatusError"
    assert llm.calls == 1
    assert result.telemetry["call_count"] == 1
    assert result.telemetry["completed_calls"] == 0
    assert result.telemetry["timed_out_calls"] == 0
    assert result.telemetry["error_calls"] == 1
    assert result.telemetry["error_types"] == {"HTTPStatusError": 1}


def test_default_min_score_is_plausible_bar():
    assert DEFAULT_MIN_SCORE == 5.0
