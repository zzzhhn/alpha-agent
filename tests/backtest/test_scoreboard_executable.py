"""Executable scoreboard receipts and returns, entirely offline."""
from dataclasses import asdict
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from alpha_agent.backtest.scoreboard import (
    compute_executable_scoreboard,
    compute_executable_scoreboard_from_rows,
)


def _history(n=3):
    sessions = [date(2026, 1, d) for d in (5, 6, 7, 8, 9, 12, 13, 14)]
    runs = [
        dict(id=i + 1, scheduled_for_date=d, run_type="daily_close", status="complete",
             finished_at=datetime(d.year, d.month, d.day, 22, tzinfo=UTC))
        for i, d in enumerate(sessions[:n])
    ]
    snapshots = [
        dict(run_id=run["id"], ticker=ticker, rank=rank, composite_z=5 - rank,
             eligible=True, in_universe=True)
        for run in runs for rank, ticker in enumerate(("A", "B", "C", "D"), 1)
    ]
    prices = [
        dict(ticker=ticker, date=d, close=100 * growth**i)
        for i, d in enumerate(sessions)
        for ticker, growth in (("A", 1.1), ("B", 1.1), ("C", 0.9), ("D", 0.9), ("SPY", 1.02))
    ]
    return runs, snapshots, prices


def _score(rows, **kwargs):
    return compute_executable_scoreboard_from_rows(*rows, top_n=2, **kwargs)


def _without(prices, tickers, day):
    return [p for p in prices if not (p["ticker"] in tickers and p["date"] == day)]


def test_returns_costs_and_relative_wealth():
    sb = _score(_history(), cost_bps=10)
    assert sb is not None
    assert sb.basis == "executable_v1"
    assert sb.days_evaluated == 3 and sb.excluded_days == 0
    assert sb.candidate_count == 12 and sb.unknown_count == 0
    assert sb.long_gross_cum == pytest.approx(1.1**3 - 1)
    # Identical names on every day still incur BOTH buy and sell fees daily.
    assert sb.long_net_cum == pytest.approx((1.1 - 0.001 - 0.001)**3 - 1)
    assert sb.long_net_cum < sb.long_gross_cum
    assert sb.short_gross_cum == pytest.approx(0.9**3 - 1)
    assert sb.spy_cum == pytest.approx(1.02**3 - 1)
    assert sb.long_minus_spy == pytest.approx(1.1**3 / 1.02**3 - 1)
    assert sb.cost_bps_used == 10
    assert sb.first_entry_date == date(2026, 1, 6)
    assert sb.last_exit_date == date(2026, 1, 9)
    assert sb.snapshot_run_ids == [1, 2, 3]
    assert all(d.evaluated and d.long_coverage == d.short_coverage == 1 for d in sb.daily_coverage)


def test_late_publication_uses_new_york_date_and_weekend_sessions():
    rows = _history()
    # Friday UTC is still Thursday in NY: enter Friday, exit Monday.
    rows[0][0]["finished_at"] = datetime(2026, 1, 9, 1, tzinfo=UTC)
    sb = _score(rows)
    day = sb.daily_coverage[0]
    assert day.entry_date == date(2026, 1, 9)
    assert day.exit_date == date(2026, 1, 12)
    assert sb.last_exit_date == date(2026, 1, 12)


def test_holiday_is_not_an_execution_session():
    rows = _history()
    # MLK Monday has no XNYS session. Add only the actual Tue/Wed endpoints.
    rows[0][0]["finished_at"] = datetime(2026, 1, 17, 1, tzinfo=UTC)
    for d in (20, 21):
        rows[2].extend(dict(ticker=t, date=date(2026, 1, d), close=100)
                       for t in ("A", "B", "C", "D", "SPY"))
    sb = _score(rows)
    assert sb.daily_coverage[0].entry_date == date(2026, 1, 20)
    assert sb.daily_coverage[0].exit_date == date(2026, 1, 21)


@pytest.mark.parametrize("ticker", ["A", "D"])
def test_missing_next_session_is_unknown_and_exact_half_coverage_is_allowed(ticker):
    runs, snapshots, prices = _history()
    # Later closes exist, but must never substitute for the missing Friday exit.
    prices = _without(prices, {ticker}, date(2026, 1, 9))
    sb = _score((runs, snapshots, prices))
    assert sb.days_evaluated == 3
    assert sb.candidate_count == 12 and sb.unknown_count == 1
    day = sb.daily_coverage[-1]
    assert day.long_candidate_count == day.short_candidate_count == 2
    assert (day.long_coverage, day.short_coverage) == (
        (0.5, 1) if ticker == "A" else (1, 0.5)
    )
    assert sb.long_gross_cum == pytest.approx(1.1**3 - 1)
    assert sb.short_gross_cum == pytest.approx(0.9**3 - 1)


def test_missing_entry_is_unknown_too():
    runs, snapshots, prices = _history()
    prices = _without(prices, {"A"}, date(2026, 1, 6))
    sb = _score((runs, snapshots, prices))
    assert sb.unknown_count == 1 and sb.candidate_count == 12
    assert sb.daily_coverage[0].long_known_count == 1


def test_losing_endpoint_is_kept_in_basket():
    rows = _history()
    for p in rows[2]:
        if p["ticker"] == "A" and p["date"] == date(2026, 1, 9):
            p["close"] = 0  # A total loss is known, not a missing observation.
    sb = _score(rows)
    assert sb.unknown_count == 0
    assert sb.daily_coverage[-1].long_known_count == 2
    assert sb.long_gross_cum == pytest.approx(1.1**2 * (1 + (-1 + 0.1) / 2) - 1)


@pytest.mark.parametrize("tickers", [{"A", "B"}, {"C", "D"}])
def test_under_half_of_either_basket_excludes_day_without_shrinking_denominator(tickers):
    runs, snapshots, prices = _history(4)
    prices = _without(prices, tickers, date(2026, 1, 6))
    sb = _score((runs, snapshots, prices))
    assert sb.days_evaluated == 3 and sb.excluded_days == 1
    assert sb.candidate_count == 16 and sb.unknown_count == 2
    assert not sb.daily_coverage[0].evaluated
    assert sb.first_entry_date == date(2026, 1, 7)
    assert sb.long_gross_cum == pytest.approx(1.1**3 - 1)


def test_spy_missing_interval_is_excluded_from_both_arms():
    runs, snapshots, prices = _history(4)
    prices = _without(prices, {"SPY"}, date(2026, 1, 6))
    # Excluded strategy interval has a huge return; prove it is not compounded.
    for p in prices:
        if p["ticker"] in {"A", "B"} and p["date"] == date(2026, 1, 6):
            p["close"] = 1
    sb = _score((runs, snapshots, prices))
    assert sb.days_evaluated == 3 and sb.excluded_days == 1
    assert sb.candidate_count == 16 and sb.unknown_count == 0
    assert sb.daily_coverage[0].long_coverage == 1
    assert not sb.daily_coverage[0].evaluated
    assert sb.long_gross_cum == pytest.approx(1.1**3 - 1)
    assert sb.spy_cum == pytest.approx(1.02**3 - 1)


@pytest.mark.parametrize("n", [0, 1, 2])
def test_fewer_than_three_days_returns_none(n):
    assert _score(_history(n)) is None


def test_exclusions_can_reduce_history_below_minimum():
    runs, snapshots, prices = _history()
    assert _score((runs, snapshots, _without(prices, {"SPY"}, date(2026, 1, 6)))) is None


def test_canonical_run_uses_latest_finish_then_highest_id():
    runs, snapshots, prices = _history()
    original = runs[0]
    # A higher id with an earlier finish must lose to the later publication.
    runs.extend([
        {**original, "id": 100},
        {**original, "id": 10, "finished_at": datetime(2026, 1, 6, 1, tzinfo=UTC)},
        {**original, "id": 11, "finished_at": datetime(2026, 1, 6, 1, tzinfo=UTC)},
        {**original, "id": 12, "finished_at": None},
        {**original, "id": 13, "status": "failed"},
        {**original, "id": 14, "run_type": "intraday"},
    ])
    snapshots.extend({**row, "run_id": 11} for row in list(snapshots) if row["run_id"] == 1)
    sb = _score((list(reversed(runs)), snapshots, prices))
    assert sb.snapshot_run_ids == [11, 2, 3]
    assert sb.candidate_count == 12
    assert sb.long_gross_cum == pytest.approx(1.1**3 - 1)


def test_canonical_run_without_eligible_members_does_not_fall_back():
    runs, snapshots, prices = _history(4)
    runs.append({**runs[0], "id": 99})
    sb = _score((runs, snapshots, prices))
    assert sb.snapshot_run_ids == [99, 2, 3, 4]
    assert sb.excluded_days == 1 and sb.candidate_count == 12
    assert sb.daily_coverage[0].long_coverage == 0


def test_window_applies_before_price_filtering():
    runs, snapshots, prices = _history(5)
    prices = _without(prices, {"SPY"}, date(2026, 1, 13))
    assert _score((runs, snapshots, prices), days=3) is None
    sb = _score((runs, snapshots, prices), days=4)
    assert sb.days_evaluated == 3 and sb.excluded_days == 1
    assert sb.snapshot_run_ids == [2, 3, 4, 5]


def test_eligibility_nulls_and_bottom_ticker_tie_break():
    runs, snapshots, prices = _history()
    for row in snapshots:
        if row["ticker"] in {"C", "D"}:
            row["composite_z"] = -1
    for p in prices:
        if p["ticker"] == "D":
            p["close"] = 100  # D would change the bottom return if selected.
    for run in runs:
        for changes in ({"eligible": False}, {"in_universe": False},
                        {"rank": None}, {"composite_z": None}):
            snapshots.append(dict(run_id=run["id"], ticker=f"INVALID{len(snapshots)}",
                                  rank=1, composite_z=-100, eligible=True,
                                  in_universe=True) | changes)
    sb = compute_executable_scoreboard_from_rows(
        runs, list(reversed(snapshots)), prices, top_n=1,
    )
    assert sb.candidate_count == 6 and sb.unknown_count == 0
    assert sb.short_gross_cum == pytest.approx(0.9**3 - 1)


async def test_loader_fetches_only_snapshot_tickers_and_exact_session_endpoints():
    rows = _history()

    class Pool:
        def __init__(self):
            self.calls = []

        async def fetch(self, sql, *args):
            self.calls.append((sql, args))
            return rows[len(self.calls) - 1]

    pool = Pool()
    sb = await compute_executable_scoreboard(pool, top_n=2, days=7, cost_bps=15)
    assert sb == _score(rows, days=7, cost_bps=15)
    assert "DISTINCT ON (scheduled_for_date)" in pool.calls[0][0]
    assert "finished_at DESC, id DESC" in pool.calls[0][0]
    assert pool.calls[0][1] == (7,)
    assert pool.calls[1][1] == ([1, 2, 3],)
    assert pool.calls[2][1] == (
        ["A", "B", "C", "D", "SPY"], [date(2026, 1, d) for d in (6, 7, 8, 9)],
    )


@pytest.mark.parametrize("old_exists,fail", [(True, False), (True, True), (False, False)])
async def test_route_attaches_independently_and_preserves_legacy_null(monkeypatch, old_exists, fail):
    from alpha_agent.api.routes import picks
    from alpha_agent.backtest import scoreboard

    old = scoreboard.Scoreboard(
        days=3, top_n=2, long_cum=0.1, short_cum=-0.1, market_cum=0,
        spread_cum=0.2, long_hit_rate=1, short_hit_rate=1, base_rate=0.5,
        spy_cum=0.02, mean_daily_turnover=0, long_net_cum=0.09, cost_bps_used=10,
        breakeven_cost_bps=None, beta=None, alpha_ann=None, alpha_t=None,
    ) if old_exists else None
    executable = _score(_history())
    loader = AsyncMock(side_effect=RuntimeError("unavailable")) if fail else AsyncMock(
        return_value=executable,
    )
    monkeypatch.setattr(picks, "get_db_pool", AsyncMock(return_value=object()))
    monkeypatch.setattr(scoreboard, "compute_picks_scoreboard", AsyncMock(return_value=old))
    monkeypatch.setattr(scoreboard, "compute_executable_scoreboard", loader)
    response = Response()
    result = await picks.picks_scoreboard(response, top_n=3, days=5)
    loader.assert_awaited_once()
    assert "s-maxage=3600" in response.headers["cache-control"]
    if old is None:
        assert result is None
    else:
        assert result.basis == "retrospective_v0"
        assert {key: getattr(result, key) for key in asdict(old)} == asdict(old)
        if fail:
            assert result.executable is None
        else:
            assert result.executable.model_dump() == asdict(executable)
            assert result.model_dump(mode="json")["executable"]["first_entry_date"] == "2026-01-06"
