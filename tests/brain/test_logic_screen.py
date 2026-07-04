"""Phase E: the LLM financial-logic pre-screen (AlphaEval 'Financial Logic').
Scores candidates' economic sense before the slow BRAIN sim; must be a safe
no-op without an LLM and must never starve the sim step."""
import pytest

from alpha_agent.brain.logic_screen import (
    DEFAULT_MIN_SCORE,
    score_economic_logic,
    select_by_logic,
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
async def test_score_bad_json_degrades_to_empty():
    llm = _FakeLLM("not json at all")
    assert await score_economic_logic(llm, ["a"]) == {}


def test_default_min_score_is_plausible_bar():
    assert DEFAULT_MIN_SCORE == 5.0
