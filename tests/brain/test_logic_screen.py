"""Phase E: the LLM financial-logic pre-screen (AlphaEval 'Financial Logic').
Scores candidates' economic sense before the slow BRAIN sim; must be a safe
no-op without an LLM and must never starve the sim step."""
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
    import asyncio

    class _TimeoutLLM(_FakeLLM):
        async def chat(self, messages, **kw):
            await asyncio.sleep(0)
            raise AssertionError("wait_for should be patched")

    async def _timeout(awaitable, *, timeout):
        close = getattr(awaitable, "close", None)
        if close:
            close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", _timeout)
    result = await score_economic_logic(_TimeoutLLM(""), ["a"])
    assert result == {}
    assert result.status == "timeout"
    assert result["error_type"] == "TimeoutError"
    assert "secret" not in (result.detail or "")


def test_default_min_score_is_plausible_bar():
    assert DEFAULT_MIN_SCORE == 5.0
