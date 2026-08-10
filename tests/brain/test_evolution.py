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
        {"expression": "group_rank(ts_rank(divide(ebit, equity), 126), subindustry)", "outcome": "flagged"},
        {"expression": "group_rank(ts_rank(divide(ebit, equity), 60), subindustry)", "outcome": "flagged"},
        {"expression": "group_rank(divide(eps, close), industry)", "outcome": "rejected"},
    ]
    st = ev.build_evolution_state(rows)
    # two of the three collapse to one signature (window-only difference)
    assert len(st.avoid_signatures) == 2
    assert st.ratio_usage[("ebit", "equity")] == 2
    assert st.ratio_usage[("eps", "close")] == 1
    # 2 flagged / 3 considered = 0.67 >= 0.4 → rotate to industry
    assert st.flagged_rate > 0.4 and st.prefer_industry is True


def test_build_state_low_flag_rate_keeps_subindustry():
    rows = [{"expression": "group_rank(divide(ebit, equity), subindustry)", "outcome": "passed"}] * 4
    st = ev.build_evolution_state(rows)
    assert st.flagged_rate == 0.0 and st.prefer_industry is False


def test_empty_history_is_empty_state():
    st = ev.build_evolution_state([])
    assert st.avoid_signatures == frozenset() and st.prefer_industry is False


def test_options_mechanisms_are_not_collapsed_to_one_family():
    cases = {
        "ts_delta(subtract(implied_volatility_call_150, implied_volatility_put_150), 20)": "iv_skew_dynamics",
        "ts_zscore(pcr_oi_120, 60)": "pcr_dynamics",
        "divide(call_breakeven_60, forward_price_60)": "option_breakeven",
        "subtract(implied_volatility_call_60, implied_volatility_call_270)": "iv_term",
        "subtract(ts_std_dev(returns, 120), implied_volatility_mean_120)": "vrp",
    }
    for expr, expected in cases.items():
        assert ev.options_mechanism_of(expr) == expected


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
