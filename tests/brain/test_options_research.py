from alpha_agent.brain.hypotheses import (
    audit_expression_semantics,
    classify_field_semantics,
    hypothesis_for,
    hypothesis_payload,
    map_expression_fields,
    research_context_key,
)
from alpha_agent.brain.fastexpr import (
    _matched_tenor_pairs,
    build_options_catalog,
    generate_brain_candidates,
)
from alpha_agent.brain.logic_screen import options_candidate_evidence
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


def test_semantic_audit_does_not_upgrade_pcr_oi_to_opening_flow():
    metadata = [{
        "id": "pcr_oi_120",
        "dataset": "option9",
        "coverage": 0.92,
        "name": "Put-call open interest ratio",
        "description": "Ratio of put open interest to call open interest",
        "type": "MATRIX",
    }]
    semantics = classify_field_semantics(metadata[0])
    assert semantics["measure_kind"] == "open_interest"
    assert not semantics["opening_flow"]
    audit = audit_expression_semantics(
        "pcr_dynamics", "rank(ts_delta(pcr_oi_120, 20))", metadata
    )
    assert "buyer initiated flow" in audit["missing_required_semantics"]
    assert audit["status"] == "mismatch"
    payload = hypothesis_payload(
        "pcr_dynamics", "rank(ts_delta(pcr_oi_120, 20))", metadata, {}
    )
    assert payload["semantic_audit"]["missing_required_semantics"]
    assert payload["semantic_audit"]["field_details"][0]["measure_kind"] == "open_interest"


def test_high_confidence_semantic_mismatch_is_withheld():
    metadata = [
        {
            "id": "implied_volatility_call_60", "dataset": "option8",
            "coverage": 0.92, "name": "Call IV 60d", "description": "call implied volatility",
            "type": "MATRIX",
        },
        {
            "id": "implied_volatility_put_120", "dataset": "option8",
            "coverage": 0.92, "name": "Put IV 120d", "description": "put implied volatility",
            "type": "MATRIX",
        },
    ]
    expr = "rank(subtract(implied_volatility_call_60, implied_volatility_put_120))"
    from alpha_agent.brain.logic_screen import select_options_research_portfolio

    assert select_options_research_portfolio(
        [expr], {expr: 9.0}, target_n=1, group_of=lambda _: "iv_skew_level",
        field_metadata=metadata, mechanism_evidence={}
    ) == []


def test_official_semantic_catalog_feeds_options_generation():
    metadata = [
        {"id": "desk_call_iv_7d", "name": "Call IV 7d", "description": "call implied volatility", "type": "MATRIX"},
        {"id": "desk_put_iv_7d", "name": "Put IV 7d", "description": "put implied volatility", "type": "MATRIX"},
        {"id": "desk_pcr_oi_7d", "name": "Put-call OI 7d", "description": "put-call open interest ratio", "type": "MATRIX"},
    ]
    catalog = build_options_catalog(metadata)
    assert catalog["iv_call"] == ("desk_call_iv_7d",)
    assert catalog["iv_put"] == ("desk_put_iv_7d",)
    assert catalog["pcr_oi"] == ("desk_pcr_oi_7d",)
    generated = generate_brain_candidates(
        9, rng_seed=7, family_focus="options", option_metadata=metadata
    )
    assert any("desk_call_iv_7d" in expr or "desk_put_iv_7d" in expr for expr in generated)


def test_official_call_put_fields_pair_on_shared_tenor():
    assert _matched_tenor_pairs(
        ("desk_call_iv_30d", "desk_call_iv_60d"),
        ("desk_put_iv_60d", "desk_put_iv_120d"),
    ) == (("desk_call_iv_60d", "desk_put_iv_60d"),)
    assert _matched_tenor_pairs(
        ("desk_call_iv_30d",), ("desk_put_iv_120d",)
    ) == ()


def test_catalog_falls_back_as_a_pair_when_live_tenors_do_not_match():
    catalog = build_options_catalog([
        {
            "id": "desk_call_iv_30d",
            "name": "Call IV 30d",
            "description": "call implied volatility",
        },
        {
            "id": "desk_put_iv_120d",
            "name": "Put IV 120d",
            "description": "put implied volatility",
        },
    ])
    assert catalog["iv_call"] == (
        "implied_volatility_call_150",
        "implied_volatility_call_180",
    )
    assert catalog["iv_put"] == (
        "implied_volatility_put_150",
        "implied_volatility_put_180",
    )


def test_history_failure_counters_do_not_double_count_same_attempt():
    expr = "rank(ts_delta(implied_volatility_call_60, 20))"
    evidence = options_candidate_evidence(
        expr,
        logic_score=8.0,
        mechanism="iv_momentum",
        field_metadata=[],
        mechanism_evidence={
            "mechanisms": {
                "iv_momentum": {
                    "attempts": 4,
                    "concentrated": 1,
                    "low_sub_universe": 1,
                }
            }
        },
    )
    assert not evidence["historically_failed"]


def test_surrogate_omits_prediction_outside_training_context():
    rows = []
    for i in range(80):
        good = i % 2 == 0
        rows.append({
            "expression": "rank(ts_delta(implied_volatility_call_60, 20))" if good else "rank(pcr_oi_120)",
            "settings": {
                "universe": "TOP3000" if good else "TOP500",
                "neutralization": "SUBINDUSTRY", "delay": 1,
                "decay": 12 if good else 0, "truncation": 0.08,
            },
            "grade": "GOOD" if good else "INFERIOR",
            "fail_checks": "" if good else "CONCENTRATED_WEIGHT",
            "self_correlation": 0.35 if good else 0.90,
            "self_correlation_adj": 0.30 if good else 0.88,
            "created_at": f"2026-01-{(i // 4) + 1:02d}T0{i % 4}:00:00Z",
        })
    model = fit_options_surrogate(rows, META)
    assert model.active
    assert model.predict(
        rows[0]["expression"], {**rows[0]["settings"], "universe": "TOP1000"}, META
    ) == {}
