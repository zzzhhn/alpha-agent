"""Cross-sectional re-standardized dimension grading (2026-06-01 rewrite)."""
from __future__ import annotations

from alpha_agent.fusion.grades import (
    NO_GRADE,
    compute_dimension_thresholds,
    grade_dimensions,
)


def _bd(**signal_z: float) -> list[dict]:
    """Build a breakdown list from signal=z kwargs."""
    return [{"signal": s, "z": z} for s, z in signal_z.items()]


def test_dead_signal_dimension_is_not_gradeable():
    # Insider identical (constant 0) across the universe -> no spread -> "—".
    universe = [_bd(insider=0.0, factor=float(i)) for i in range(50)]
    th = compute_dimension_thresholds(universe)
    assert th["Insider"] is None
    assert th["Momentum"] is not None
    live, mu, sd = th["Momentum"]
    assert live == ("factor",)
    assert sd > 0


def test_too_few_observations_not_graded():
    universe = [_bd(factor=float(i)) for i in range(5)]  # < _MIN_UNIVERSE
    assert compute_dimension_thresholds(universe)["Momentum"] is None


def test_grade_spread_top_is_aplus_bottom_is_f_middle_neutral():
    # Uniform 0..99: re-z spans about -1.7..+1.7, so extremes hit A+/F.
    universe = [_bd(technicals=float(i)) for i in range(100)]
    th = compute_dimension_thresholds(universe)
    assert th["Technical"] is not None
    assert grade_dimensions(_bd(technicals=99.0), th)["Technical"] == "A+"
    assert grade_dimensions(_bd(technicals=0.0), th)["Technical"] == "F"
    assert grade_dimensions(_bd(technicals=50.0), th)["Technical"] == "C+"


def test_full_a_to_f_spectrum_for_continuous_dimension():
    universe = [_bd(technicals=float(i)) for i in range(100)]
    th = compute_dimension_thresholds(universe)
    grades = {
        grade_dimensions(_bd(technicals=float(i)), th)["Technical"]
        for i in range(100)
    }
    assert {"A+", "A", "B", "C+", "C", "D", "F"} <= grades


def test_neutral_point_mass_stays_neutral_not_stretched():
    # Sparse signal: 90 neutral (0) + 10 strong positive. Re-z must keep the
    # neutral mass near the neutral grade, NOT stretch it across A-to-F (the
    # bug a percentile mapping would introduce).
    universe = [_bd(news=0.0) for _ in range(90)] + [
        _bd(news=2.0) for _ in range(10)
    ]
    th = compute_dimension_thresholds(universe)
    assert th["Sentiment"] is not None
    neutral = grade_dimensions(_bd(news=0.0), th)["Sentiment"]
    strong = grade_dimensions(_bd(news=2.0), th)["Sentiment"]
    assert neutral in {"C", "C+", "D"}  # neutral, not A
    assert strong in {"A", "A+"}


def test_dilution_removed_dead_members_dropped():
    # political_impact & geopolitical_impact are constant -> dropped, so
    # Sentiment grades on news alone (not news/3), and live == ("news",).
    universe = [
        _bd(news=float(i), political_impact=0.0, geopolitical_impact=0.0)
        for i in range(100)
    ]
    th = compute_dimension_thresholds(universe)
    assert th["Sentiment"] is not None
    live, _mu, _sd = th["Sentiment"]
    assert live == ("news",)
    assert grade_dimensions(
        _bd(news=99.0, political_impact=0.0, geopolitical_impact=0.0), th
    )["Sentiment"] == "A+"


def test_missing_member_for_ticker_shows_no_grade():
    universe = [_bd(technicals=float(i)) for i in range(50)]
    th = compute_dimension_thresholds(universe)
    # This ticker has no technicals entry -> "—" even though Technical is
    # gradeable universe-wide.
    assert grade_dimensions(_bd(factor=1.0), th)["Technical"] == NO_GRADE
