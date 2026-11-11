"""QUANT-4: the calibration endpoint exposes the applied map's size and levels."""
from datetime import UTC, datetime

from alpha_agent.api.routes.evolution import _level_count, calibration


def test_level_count_counts_distinct_outputs():
    assert _level_count({"x": [0.4, 0.5, 0.6, 0.7], "y": [0.0, 0.6032, 0.6032, 1.0]}) == 3
    assert _level_count({"x": [], "y": []}) is None
    assert _level_count(None) is None


class _Pool:
    def __init__(self, latest, applied):
        self.latest, self.applied = latest, applied

    async def fetchrow(self, sql, *args):
        return self.applied if "applied = true" in sql else self.latest


async def test_unapplied_latest_fit_reports_the_active_applied_map(monkeypatch):
    latest = {"as_of": datetime(2026, 11, 10, tzinfo=UTC), "n_pairs": 40, "applied": False,
              "isotonic_map": None, "buckets": "[]"}
    applied = {"as_of": datetime(2026, 9, 26, tzinfo=UTC), "n_pairs": 981,
               "isotonic_map": '{"x": [0.1, 0.2, 0.3], "y": [0.3384, 0.3718, 0.4032]}'}
    pool = _Pool(latest, applied)

    async def fake_pool():
        return pool

    monkeypatch.setattr("alpha_agent.api.routes.evolution.get_db_pool", fake_pool)
    out = await calibration()
    assert out["applied"] is False and out["n_pairs"] == 40
    assert out["active"] == {"as_of": "2026-09-26T00:00:00+00:00", "n_pairs": 981, "levels": 3}
