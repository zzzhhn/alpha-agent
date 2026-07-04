"""Phase F3: BRAIN self-evolution — learn from mining history to fight
homogenization / rising self-correlation."""
from alpha_agent.brain import evolution as ev
from alpha_agent.brain import fastexpr as fe


def test_expr_signature_ignores_windows_and_space():
    a = "group_rank(ts_rank(divide(ebit, equity), 60), subindustry)"
    b = "group_rank(ts_rank(divide(ebit, equity), 252), subindustry)"
    assert ev.expr_signature(a) == ev.expr_signature(b)  # differ only by window
    c = "group_rank(ts_rank(divide(ebitda, assets), 60), subindustry)"
    assert ev.expr_signature(a) != ev.expr_signature(c)  # different fields


def test_ratios_in_extracts_pairs():
    assert ev.ratios_in("add(divide(ebit, equity), divide(eps, close))") == [
        ("ebit", "equity"), ("eps", "close"),
    ]
    assert ev.ratios_in("group_rank(ts_rank(volume, 20), sector)") == []


def test_build_state_avoid_sigs_ratio_usage_and_rotation():
    rows = [
        {"expression": "group_rank(ts_rank(divide(ebit, equity), 126), subindustry)", "outcome": "passed"},
        {"expression": "group_rank(ts_rank(divide(ebit, equity), 60), subindustry)", "outcome": "flagged"},
        {"expression": "group_rank(divide(eps, close), industry)", "outcome": "rejected"},
    ]
    st = ev.build_evolution_state(rows)
    # two of the three collapse to one signature (window-only difference)
    assert len(st.avoid_signatures) == 2
    assert st.ratio_usage[("ebit", "equity")] == 2
    assert st.ratio_usage[("eps", "close")] == 1
    # 1 flagged / 3 considered = 0.33 >= 0.25 → rotate to industry
    assert st.flagged_rate > 0.25 and st.prefer_industry is True


def test_build_state_low_flag_rate_keeps_subindustry():
    rows = [{"expression": "group_rank(divide(ebit, equity), subindustry)", "outcome": "passed"}] * 4
    st = ev.build_evolution_state(rows)
    assert st.flagged_rate == 0.0 and st.prefer_industry is False


def test_empty_history_is_empty_state():
    st = ev.build_evolution_state([])
    assert st.avoid_signatures == frozenset() and st.prefer_industry is False


# ── generator honours the evolution hints ──────────────────────────────────
def test_generator_skips_avoided_signatures():
    # First, learn the signatures of a normal round.
    base = fe.generate_brain_candidates(15, rng_seed=5)
    avoid = frozenset(ev.expr_signature(e) for e in base)
    # Same seed, but now avoid those signatures → none may reappear.
    evolved = fe.generate_brain_candidates(15, rng_seed=5, avoid_signatures=avoid)
    assert all(ev.expr_signature(e) not in avoid for e in evolved)


def test_prefer_industry_rotates_neutralization():
    # With prefer_industry, the ratio templates should lean toward 'industry'.
    cands = fe.generate_brain_candidates(40, rng_seed=7, prefer_industry=True)
    industry = sum(1 for c in cands if "industry)" in c and "subindustry)" not in c)
    subind = sum(1 for c in cands if "subindustry)" in c)
    assert industry > 0  # rotation actually produces industry-neutral alphas
