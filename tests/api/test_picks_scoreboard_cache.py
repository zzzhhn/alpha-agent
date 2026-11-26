from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.routes import picks
from alpha_agent.backtest import scoreboard


@pytest.fixture
def scoreboard_client(monkeypatch):
    app = FastAPI()
    app.include_router(picks.router)
    monkeypatch.setattr(picks, "get_db_pool", AsyncMock(return_value=object()))
    return TestClient(app)


def test_executable_failure_with_empty_history_is_not_publicly_cached(
    scoreboard_client, monkeypatch,
):
    monkeypatch.setattr(scoreboard, "compute_picks_scoreboard", AsyncMock(return_value=None))
    monkeypatch.setattr(
        scoreboard, "compute_executable_scoreboard", AsyncMock(side_effect=TimeoutError),
    )
    response = scoreboard_client.get("/api/picks/scoreboard")
    assert response.headers.get("cache-control") == "no-store"
    assert response.status_code == 503


@pytest.fixture
def retrospective():
    return scoreboard.Scoreboard(
        days=9, top_n=10, long_cum=.06, short_cum=-.01, market_cum=.02,
        spread_cum=.05, long_hit_rate=.6, short_hit_rate=.55, base_rate=.54,
        spy_cum=.01, mean_daily_turnover=.1, long_net_cum=.05, cost_bps_used=10,
        breakeven_cost_bps=60, beta=1.1, alpha_ann=None, alpha_t=None,
    )


def test_executable_failure_preserves_retrospective_and_recovers(
    scoreboard_client, monkeypatch, retrospective,
):
    from datetime import date

    executable = scoreboard.ExecutableScoreboard(
        days_evaluated=9, excluded_days=0, top_n=10, long_gross_cum=.04,
        long_net_cum=.03, short_gross_cum=-.02, spy_cum=.01,
        long_minus_spy=.03, unknown_count=0, candidate_count=180,
        cost_bps_used=10, first_entry_date=date(2026, 11, 3),
        last_exit_date=date(2026, 11, 16), snapshot_run_ids=[42], daily_coverage=[],
    )
    monkeypatch.setattr(scoreboard, "compute_picks_scoreboard", AsyncMock(return_value=retrospective))
    monkeypatch.setattr(
        scoreboard, "compute_executable_scoreboard",
        AsyncMock(side_effect=[TimeoutError, executable]),
    )

    partial = scoreboard_client.get("/api/picks/scoreboard")
    assert partial.status_code == 200
    assert partial.headers["cache-control"] == "no-store"
    assert partial.json()["long_cum"] == retrospective.long_cum
    assert partial.json()["executable"] is None
    assert partial.json()["executable_status"] == "unavailable"

    recovered = scoreboard_client.get("/api/picks/scoreboard")
    assert recovered.status_code == 200
    assert recovered.headers["cache-control"] == "public, s-maxage=3600, stale-while-revalidate=86400"
    assert recovered.json()["executable_status"] == "available"
    assert recovered.json()["executable"]["snapshot_run_ids"] == [42]


def test_small_history_can_use_normal_cache(scoreboard_client, monkeypatch, retrospective):
    pool = AsyncMock()
    pool.fetch.return_value = []
    monkeypatch.setattr(picks, "get_db_pool", AsyncMock(return_value=pool))
    empty = scoreboard_client.get("/api/picks/scoreboard")
    assert empty.status_code == 200
    assert empty.json() is None
    assert empty.headers["cache-control"] == "public, s-maxage=3600, stale-while-revalidate=86400"

    monkeypatch.setattr(scoreboard, "compute_picks_scoreboard", AsyncMock(return_value=retrospective))
    insufficient = scoreboard_client.get("/api/picks/scoreboard")
    assert insufficient.status_code == 200
    assert insufficient.headers["cache-control"] == empty.headers["cache-control"]
    assert insufficient.json()["executable"] is None
    assert insufficient.json()["executable_status"] == "insufficient_history"
