"""Phase C: the GA loop and its composite fitness. The loop is exercised with a
synthetic injected fitness (no DB/kernel) so its search behaviour — determinism,
elitism/best-tracking, discovering a reachable target, honoring the wall-clock
budget — is tested in isolation. One slow test runs the full panel-backed
search end-to-end and asserts every returned candidate is grammatically valid."""
import math
from dataclasses import dataclass
import random

import pytest

from alpha_agent.evolution import ga_dsl
from alpha_agent.evolution import ga_search as gs


# ── composite fitness ─────────────────────────────────────────────────────
@dataclass
class _M:
    sharpe: float
    icir: float
    ic_spearman: float
    turnover: float


def test_composite_fitness_blends_and_penalizes_turnover():
    base = gs.composite_fitness(_M(1.0, 1.0, 0.02, 0.2))
    # higher turnover, everything else equal, must score strictly lower
    churny = gs.composite_fitness(_M(1.0, 1.0, 0.02, 0.8))
    assert churny < base
    # higher Sharpe must score strictly higher
    assert gs.composite_fitness(_M(2.0, 1.0, 0.02, 0.2)) > base


def test_composite_fitness_nan_is_unfit():
    assert gs.composite_fitness(_M(float("nan"), 1.0, 0.02, 0.2)) == float("-inf")
    assert gs.composite_fitness(_M(1.0, float("inf"), 0.02, 0.2)) == float("-inf")


# ── evolve loop with a synthetic fitness ──────────────────────────────────
def _reward_vwap(expr: str) -> float:
    # A target reachable via operand mutation / random subtrees.
    return 2.0 if "vwap" in expr else 0.001 * len(expr)


def test_evolve_is_deterministic_under_fixed_rng():
    a = gs.evolve(random.Random(42), [], _reward_vwap, pop_size=20, generations=5)
    b = gs.evolve(random.Random(42), [], _reward_vwap, pop_size=20, generations=5)
    assert a == b


def test_evolve_returns_sorted_distinct_finite_scores():
    out = gs.evolve(random.Random(3), [], _reward_vwap, pop_size=20, generations=5)
    exprs = [e for e, _ in out]
    scores = [s for _, s in out]
    assert len(exprs) == len(set(exprs))          # distinct
    assert scores == sorted(scores, reverse=True)  # fittest first
    assert all(math.isfinite(s) for s in scores)   # no -inf leaks out


def test_evolve_discovers_a_reachable_target():
    out = gs.evolve(random.Random(1), [], _reward_vwap, pop_size=40, generations=15)
    assert out, "GA returned nothing"
    top_expr, top_score = out[0]
    assert "vwap" in top_expr and top_score == pytest.approx(2.0)


def test_evolve_respects_wall_clock_budget():
    calls = {"n": 0}

    def counting_fitness(expr: str) -> float:
        calls["n"] += 1
        return _reward_vwap(expr)

    # Clock jumps past the deadline immediately, so no generation runs — only the
    # initial population is scored (pop_size calls), not pop_size*(gens+1).
    ticks = iter([0.0] + [100.0] * 50)
    gs.evolve(
        random.Random(1), [], counting_fitness,
        pop_size=12, generations=10, budget_s=1.0, clock=lambda: next(ticks),
    )
    assert calls["n"] == 12


# ── full panel-backed search (slow: needs the parquet + kernel) ───────────
def test_ga_candidates_wraps_top_k_as_rawproposals(monkeypatch):
    from alpha_agent.evolution.llm_factor_proposer import RawProposal

    monkeypatch.setattr(
        gs, "run_ga_search",
        lambda **kw: ["rank(returns)", "ts_mean(vwap, 20)"],
    )
    cands = gs.ga_candidates(top_k=2)
    assert all(isinstance(c, RawProposal) for c in cands)
    assert [c.expression for c in cands] == ["rank(returns)", "ts_mean(vwap, 20)"]
    # GA candidates never author operators — they must pass a clean list through.
    assert all(c.new_operators == [] for c in cands)


@pytest.mark.slow
def test_run_ga_search_returns_valid_candidates_on_real_panel():
    from alpha_agent.core.factor_ast import expression_to_tree, validate_expression

    exprs = gs.run_ga_search(
        pop_size=10, generations=2, top_k=5, budget_s=90.0,
        seed_exprs=["rank(ts_mean(returns, 20))"], rng_seed=1,
    )
    assert 1 <= len(exprs) <= 5
    for e in exprs:
        # every returned candidate passes the real grammar validator
        validate_expression(e, ga_dsl.used_operators(expression_to_tree(e)))
