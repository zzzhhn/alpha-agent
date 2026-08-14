"""Pure tests for the per-horizon basket sleeve metrics."""

from datetime import date, timedelta

import pytest

from alpha_agent.api.routes.basket_edge import _horizon_from_rows


def _rows(n_dates: int = 10) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for day in range(n_dates):
        d = date(2026, 1, 1) + timedelta(days=day)
        for name in range(20):
            # Top/bottom quintiles have stable, distinct sleeve returns while
            # the middle is flat. This makes the long, short, and spread
            # semantics independently observable without a database fixture.
            if name < 4:
                ret = -0.01
            elif name >= 16:
                ret = 0.02
            else:
                ret = 0.0
            rows.append({"date": d, "composite": float(name), "fwd_ret": ret})
    return rows


def test_horizon_keeps_long_and_short_sleeves_separate() -> None:
    result = _horizon_from_rows(5, _rows())

    assert result.insufficient is False
    assert result.n_days == 10
    assert result.long_mean_return == pytest.approx(0.02)
    assert result.short_mean_return == pytest.approx(-0.01)
    assert result.long_short_spread == pytest.approx(0.03)


def test_horizon_nulls_metrics_below_date_floor() -> None:
    result = _horizon_from_rows(20, _rows(n_dates=9))

    assert result.insufficient is True
    assert result.n_days == 9
    assert result.long_mean_return is None
    assert result.short_mean_return is None
    assert result.long_short_spread is None
