# tests/test_run_health.py
"""Run-health / abstention gates (roadmap step 2).

A run that finished but is not trustworthy as tradable truth must be marked
non-tradable, not silently consumed. evaluate_gates is a pure decision over a
run's snapshots + a benchmark-availability bool: it returns the gated status
('complete' when healthy, 'partial' when a hard gate fails) plus machine-
readable reasons + metrics for forensics. No fabricated metrics — only what is
actually computable from the recorded data is reported.
"""
from alpha_agent.run_health import MIN_ELIGIBLE, evaluate_gates
from alpha_agent.storage.product_ledger import RatingSnapshot


def _snaps(n, tier="BUY"):
    return [RatingSnapshot(ticker=f"T{i}", tier=tier, eligible=True) for i in range(n)]


def test_healthy_run_passes_and_is_complete():
    res = evaluate_gates(_snaps(MIN_ELIGIBLE), benchmark_fresh=True)
    assert res.passed is True
    assert res.status == "complete"
    assert res.reasons == []
    assert res.metrics["eligible_count"] == MIN_ELIGIBLE
    assert res.metrics["benchmark_fresh"] is True


def test_too_few_eligible_is_partial():
    res = evaluate_gates(_snaps(MIN_ELIGIBLE - 1), benchmark_fresh=True)
    assert res.passed is False
    assert res.status == "partial"
    assert any(r.startswith("insufficient_eligible") for r in res.reasons)


def test_missing_benchmark_is_partial():
    res = evaluate_gates(_snaps(MIN_ELIGIBLE), benchmark_fresh=False)
    assert res.passed is False
    assert res.status == "partial"
    assert "no_benchmark" in res.reasons


def test_metrics_include_tier_distribution():
    snaps = _snaps(MIN_ELIGIBLE, tier="BUY") + _snaps(2, tier="SELL")
    res = evaluate_gates(snaps, benchmark_fresh=True)
    assert res.metrics["tier_counts"]["BUY"] == MIN_ELIGIBLE
    assert res.metrics["tier_counts"]["SELL"] == 2


def test_multiple_failures_reported_together():
    res = evaluate_gates(_snaps(0), benchmark_fresh=False)
    assert res.passed is False
    assert any(r.startswith("insufficient_eligible") for r in res.reasons)
    assert "no_benchmark" in res.reasons
