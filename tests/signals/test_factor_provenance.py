"""QUANT-0: the factor signal discloses which expression and panel date it used."""
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np

from alpha_agent.signals import factor


def test_custom_expression_reports_frozen_panel_and_its_last_date():
    panel = SimpleNamespace(dates=np.array(["2026-10-29", "2026-10-30"], dtype="datetime64[D]"))
    out = factor.factor_provenance("group_neutralize(zscore(ts_zscore(volume,20)),sector)", panel, live=False)
    assert out == {
        "expression": "group_neutralize(zscore(ts_zscore(volume,20)),sector)",
        "is_custom": True,
        "panel": "frozen_research_parquet",
        "data_date": "2026-10-30",
    }


def test_preset_on_live_panel_is_not_custom():
    panel = SimpleNamespace(dates=["2026-11-09", "2026-11-10"])
    out = factor.factor_provenance(factor.SHORT_TERM_FACTOR_EXPR, panel, live=True)
    assert out["is_custom"] is False
    assert out["panel"] == "live_daily_prices"
    assert out["data_date"] == "2026-11-10"


def test_fetch_attaches_factor_source_without_changing_z(monkeypatch):
    expr = "rank(close)"
    monkeypatch.setattr(factor, "_resolve_default_expr", lambda: expr)

    def fake_eval(as_of, expr=None):
        factor._LAST_EVAL[expr] = {"expression": expr, "is_custom": True,
                                   "panel": "frozen_research_parquet", "data_date": "2026-10-30"}
        return {"NVDA": 1.15}

    monkeypatch.setattr(factor, "_evaluate_for_universe", fake_eval)
    monkeypatch.setattr(factor, "_fetch_info_for", lambda ticker: {})
    score = factor._fetch("NVDA", datetime(2026, 11, 11, tzinfo=UTC))
    assert score["z"] == 1.15
    assert score["raw"]["factor_source"]["data_date"] == "2026-10-30"
    assert score["raw"]["factor_source"]["panel"] == "frozen_research_parquet"
