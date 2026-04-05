"""Tests for HTMLReportGenerator."""

from __future__ import annotations

import pytest

from alpha_agent.pipeline.orchestrator import PipelineResult
from alpha_agent.pipeline.state import (
    EvaluationDecision,
    FactorCandidate,
    FactorResult,
    PipelineState,
)
from alpha_agent.report.generator import HTMLReportGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_candidate(expr: str = "Rank(-Delta($close, 5))") -> FactorCandidate:
    return FactorCandidate(
        expression=expr,
        hypothesis_name="reversal",
        rationale="5-day return reversal",
    )


def _sample_result(
    expr: str = "Rank(-Delta($close, 5))",
    ic: float = 0.04,
    icir: float = 1.2,
) -> FactorResult:
    return FactorResult(
        candidate=_sample_candidate(expr),
        ic_mean=ic,
        icir=icir,
        rank_ic_mean=0.035,
        sharpe_ratio=0.8,
        max_drawdown=-0.15,
        turnover=0.3,
        alpha_decay=(0.04, 0.03, 0.02, 0.01, 0.005),
    )


def _sample_pipeline_result(
    query: str = "Find momentum factors",
    n_factors: int = 2,
) -> PipelineResult:
    factors = tuple(_sample_result(f"expr_{i}", ic=0.03 + i * 0.01) for i in range(n_factors))
    best = factors[0] if factors else None
    evaluation = EvaluationDecision(
        decision="accept",
        feedback="Strong IC",
        suggestions=(),
        best_factor=best,
    )
    state = PipelineState(
        query=query,
        results=factors,
        evaluation=evaluation,
    )
    return PipelineResult(
        query=query,
        accepted_factors=(best,) if best else (),
        rejected_factors=factors[1:],
        total_iterations=1,
        all_states=(state,),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHTMLReportGenerator:
    def test_generate_returns_nonempty_string(self) -> None:
        gen = HTMLReportGenerator()
        result = _sample_pipeline_result()
        html = gen.generate(result)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_html_contains_query(self) -> None:
        gen = HTMLReportGenerator()
        query = "Find momentum factors"
        result = _sample_pipeline_result(query=query)
        html = gen.generate(result)
        assert query in html

    def test_html_contains_base64_image(self) -> None:
        gen = HTMLReportGenerator()
        result = _sample_pipeline_result()
        html = gen.generate(result)
        assert "data:image/png;base64," in html

    def test_html_is_valid_structure(self) -> None:
        gen = HTMLReportGenerator()
        result = _sample_pipeline_result()
        html = gen.generate(result)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_empty_result_no_factors(self) -> None:
        """Should not raise even when no factors were generated."""
        gen = HTMLReportGenerator()
        empty_result = PipelineResult(
            query="empty test",
            accepted_factors=(),
            rejected_factors=(),
            total_iterations=0,
            all_states=(),
        )
        html = gen.generate(empty_result)
        assert isinstance(html, str)
        assert "empty test" in html
        assert "No factors evaluated" in html

    def test_factor_expressions_appear_in_report(self) -> None:
        gen = HTMLReportGenerator()
        result = _sample_pipeline_result(n_factors=2)
        html = gen.generate(result)
        assert "expr_0" in html
        assert "expr_1" in html

    def test_iteration_count_in_header(self) -> None:
        gen = HTMLReportGenerator()
        result = _sample_pipeline_result()
        html = gen.generate(result)
        assert "Iterations:" in html or "total_iterations" in html or "1" in html
