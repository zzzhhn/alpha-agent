"""Per-factor simulation-settings adaptation (the smart retry)."""
from alpha_agent.brain import tuning as t
from alpha_agent.brain.client import (
    MAX_DRAWDOWN,
    MAX_TURNOVER,
    MIN_FITNESS,
    MIN_SHARPE,
    AlphaMetrics,
)


def _m(**kw) -> AlphaMetrics:
    base = dict(alpha_id="A", sharpe=1.6, fitness=1.2, turnover=0.1,
                returns=0.2, drawdown=0.05)
    base.update(kw)
    return AlphaMetrics(**base)


def test_base_settings_family_adaptive():
    fund = t.base_settings_for(
        "group_rank(ts_rank(divide(ebit, equity), 126), subindustry)"
    )
    tech = t.base_settings_for("group_rank(ts_std_dev(returns, 40), industry)")
    assert fund["decay"] == 0     # fundamentals keep the proven decay-0 config
    assert tech["decay"] == 12    # fast/technical signals get more decay
    assert fund["neutralization"] == "SUBINDUSTRY"


def test_diagnose_turnover_near_miss_only():
    assert t.diagnose(_m(turnover=MAX_TURNOVER * 1.4)) == "turnover"   # fixable
    assert t.diagnose(_m(turnover=MAX_TURNOVER * 3.0)) is None         # hopeless


def test_diagnose_sharpe_and_fitness():
    assert t.diagnose(_m(sharpe=MIN_SHARPE * 0.9)) == "sharpe"
    assert t.diagnose(_m(sharpe=MIN_SHARPE * 0.4)) is None
    assert t.diagnose(_m(sharpe=1.6, fitness=MIN_FITNESS * 0.9)) == "fitness"


def test_diagnose_drawdown_and_passing():
    assert t.diagnose(_m(drawdown=MAX_DRAWDOWN * 1.2)) == "drawdown"
    assert t.diagnose(_m()) is None  # everything already within the gates


def test_diagnose_prefers_brain_fail_check():
    # BRAIN says HIGH_TURNOVER failed even though the raw value looks borderline.
    m = _m(turnover=MAX_TURNOVER * 1.1,
           checks={"HIGH_TURNOVER": {"result": "FAIL", "value": 0.4}})
    assert t.diagnose(m) == "turnover"


def test_retry_variant_targets_problem():
    base = t.base_settings_for(
        "group_rank(ts_rank(divide(ebit, equity), 126), subindustry)"
    )
    assert t.retry_variant(base, "turnover")["decay"] > base["decay"]
    assert t.retry_variant(base, "sharpe")["universe"] == "TOP1000"
    assert t.retry_variant(base, "fitness")["universe"] == "TOP1000"
    assert t.retry_variant(base, "drawdown")["truncation"] == 0.04
    assert t.retry_variant(base, None) is None
