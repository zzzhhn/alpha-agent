from alpha_agent.brain.hypotheses import (
    hypothesis_for,
    map_expression_fields,
    research_context_key,
)
from alpha_agent.brain.surrogate import fit_options_surrogate
from alpha_agent.brain.tuning import options_settings_for


META = [
    {
        "id": "implied_volatility_call_60",
        "dataset": "option8",
        "coverage": 0.91,
    },
    {"id": "pcr_oi_120", "dataset": "option9", "coverage": 0.62},
]


def test_hypothesis_mapping_keeps_source_target_and_official_fields_separate():
    expr = "rank(ts_delta(implied_volatility_call_60, 20))"
    hypothesis = hypothesis_for("iv_momentum")
    mapping = map_expression_fields(expr, META)
    assert hypothesis.confidence == "high"
    assert "stock returns" in hypothesis.target
    assert mapping == {
        "field_ids": ["implied_volatility_call_60"],
        "dataset_ids": ["option8"],
        "coverage": 0.91,
        "mapped_ratio": 1.0,
    }
    assert "option8|TOP3000" in research_context_key(
        "iv_momentum", expr, META, {"universe": "TOP3000"}
    )


def test_failure_feedback_repairs_concentration_without_shrinking_universe():
    expr = "rank(ts_delta(implied_volatility_call_60, 20))"
    evidence = {
        "mechanisms": {
            "iv_momentum": {
                "attempts": 10,
                "concentrated": 6,
                "low_sub_universe": 8,
            }
        }
    }
    settings = options_settings_for(expr, evidence)
    assert settings["truncation"] == 0.04
    assert settings["universe"] == "TOP3000"


def test_surrogate_requires_holdout_evidence_and_predicts_only_when_validated():
    rows = []
    for i in range(80):
        good = i % 2 == 0
        rows.append({
            "expression": (
                "group_neutralize(rank(ts_delta(implied_volatility_call_60, 20)), subindustry)"
                if good
                else "group_neutralize(reverse(rank(ts_zscore(pcr_oi_120, 60))), sector)"
            ),
            "settings": {
                "universe": "TOP3000" if good else "TOP500",
                "neutralization": "SUBINDUSTRY",
                "delay": 1,
                "decay": 12 if good else 0,
                "truncation": 0.08,
            },
            "grade": "GOOD" if good else "INFERIOR",
            "fail_checks": "" if good else "CONCENTRATED_WEIGHT,LOW_SUB_UNIVERSE_SHARPE",
            "self_correlation": 0.35 if good else 0.90,
            "self_correlation_adj": 0.30 if good else 0.88,
            "created_at": f"2026-01-{(i // 4) + 1:02d}T0{i % 4}:00:00Z",
        })
    model = fit_options_surrogate(rows, META)
    assert model.active
    prediction = model.predict(rows[0]["expression"], rows[0]["settings"], META)
    assert prediction["good"] > 0.70
    assert prediction["concentration"] < 0.30
    assert prediction["marginal_proxy"] > 0.80


def test_surrogate_stays_inactive_with_too_little_history():
    model = fit_options_surrogate([], META)
    assert not model.active
    assert model.predict("rank(implied_volatility_call_60)", {}, META) == {}
