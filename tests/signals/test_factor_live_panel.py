"""The preset factor reads the live daily_prices panel through asyncpg.

Production evidence (2026-11-12): the serverless bundle has no psycopg, so the
synchronous loader always failed and every preset evaluation used the frozen
research parquet (data date 2026-10-30) while being labelled as fresh work.
"""
from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest

from alpha_agent.factor_engine import factor_backtest as fb
from alpha_agent.signals import factor

START = date(2026, 7, 1)


def _rows(n_days: int, tickers: dict[str, float], jumps: dict[str, int] | None = None):
    """Synthetic closes: each ticker drifts at its own daily rate."""
    jumps = jumps or {}
    out = []
    for i in range(n_days):
        day = (START + timedelta(days=i)).isoformat()
        for t, drift in tickers.items():
            close = 100.0 * (1 + drift) ** i
            if t in jumps and i >= jumps[t]:
                close *= 0.5  # unadjusted 2:1 split in the feed
            out.append((day, t, close))
    return out


def test_panel_needs_minimum_history():
    assert fb.live_panel_from_rows(_rows(10, {"AAA": 0.001, "SPY": 0.0}), min_days=65) is None


def test_suspect_jump_ticker_is_excluded_and_reported():
    info: dict = {}
    rows = _rows(70, {"AAA": 0.001, "BBB": 0.002, "SPLT": 0.001, "SPY": 0.0005}, jumps={"SPLT": 40})
    panel = fb.live_panel_from_rows(rows, min_days=65, max_abs_daily_return=0.45, info=info)
    assert panel is not None
    assert set(panel.tickers) == {"AAA", "BBB"}
    assert info["excluded_suspect_jumps"] == ["SPLT"]
    assert panel.dates[-1] == (START + timedelta(days=69)).isoformat()


def test_without_threshold_nothing_is_excluded():
    rows = _rows(70, {"AAA": 0.001, "SPLT": 0.001, "SPY": 0.0}, jumps={"SPLT": 40})
    panel = fb.live_panel_from_rows(rows, min_days=65)
    assert "SPLT" in panel.tickers


def test_primed_live_panel_is_used_for_the_preset(monkeypatch):
    rows = _rows(70, {"UP": 0.004, "FLAT": 0.0, "DOWN": -0.003, "SPY": 0.0005})
    panel = fb.live_panel_from_rows(rows, min_days=65, max_abs_daily_return=0.45, info={})

    def parquet_must_not_load():
        raise AssertionError("frozen parquet used while a live panel was primed")

    def sync_loader_must_not_run(min_days=65):
        raise AssertionError("psycopg loader used while a live panel was primed")

    monkeypatch.setattr(fb, "_load_panel", parquet_must_not_load)
    monkeypatch.setattr(fb, "load_live_panel", sync_loader_must_not_run)
    monkeypatch.setitem(factor._PRIMED_LIVE, "panel", panel)
    monkeypatch.setitem(factor._PRIMED_LIVE, "info", {"excluded_suspect_jumps": ["SPLT"]})
    factor._SCORE_CACHE.clear()
    scores = factor._evaluate_for_universe(datetime.now(UTC), expr=factor.SHORT_TERM_FACTOR_EXPR)
    assert set(scores) <= {"UP", "FLAT", "DOWN"}
    source = factor._LAST_EVAL[factor.SHORT_TERM_FACTOR_EXPR]
    assert source["panel"] == "live_daily_prices"
    assert source["data_date"] == panel.dates[-1]
    assert source["excluded_suspect_jumps"] == ["SPLT"]
    # Per-ticker calls reuse one cross-section instead of re-ranking.
    again = factor._evaluate_for_universe(datetime.now(UTC), expr=factor.SHORT_TERM_FACTOR_EXPR)
    assert again is scores
    factor._SCORE_CACHE.clear()


def test_custom_expression_still_uses_the_parquet(monkeypatch):
    calls = {"parquet": 0}
    live = fb.live_panel_from_rows(_rows(70, {"A": 0.001, "B": 0.002, "SPY": 0.0}), min_days=65)

    def fake_parquet():
        calls["parquet"] += 1
        return live

    monkeypatch.setattr(fb, "_load_panel", fake_parquet)
    monkeypatch.setitem(factor._PRIMED_LIVE, "panel", live)
    factor._SCORE_CACHE.clear()
    expr = "rank(ts_mean(returns, 30))"
    factor._evaluate_for_universe(datetime.now(UTC), expr=expr)
    assert calls["parquet"] == 1
    assert factor._LAST_EVAL[expr]["panel"] == "frozen_research_parquet"
    factor._SCORE_CACHE.clear()


@pytest.mark.asyncio
async def test_prime_reads_the_live_table_through_asyncpg(applied_db, monkeypatch):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.executemany(
            "INSERT INTO daily_prices (date, ticker, close) VALUES ($1::text::date, $2, $3)",
            _rows(90, {"AAA": 0.001, "BBB": -0.001, "SPLT": 0.0, "SPY": 0.0}, jumps={"SPLT": 85}),
        )
    finally:
        await conn.close()
    monkeypatch.setitem(factor._PRIMED_LIVE, "panel", None)
    monkeypatch.setitem(factor._PRIMED_LIVE, "info", {})
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        receipt = await factor.prime_live_panel(pool)
        panel = factor._PRIMED_LIVE["panel"]
    finally:
        await pool.close()
    assert receipt == {
        "live": True,
        "data_date": (START + timedelta(days=89)).isoformat(),
        "excluded_suspect_jumps": 1,
    }
    # Bounded read: only the most recent LIVE_PANEL_SESSIONS sessions.
    assert len(panel.dates) == fb.LIVE_PANEL_SESSIONS


@pytest.mark.asyncio
async def test_prime_failure_falls_back_and_says_so(monkeypatch):
    class BrokenPool:
        async def fetch(self, *args, **kwargs):
            raise asyncpg.PostgresConnectionError("down")

    monkeypatch.setitem(factor._PRIMED_LIVE, "panel", object())
    monkeypatch.setitem(factor._PRIMED_LIVE, "info", {})
    receipt = await factor.prime_live_panel(BrokenPool())
    assert receipt == {"live": False, "error_type": "PostgresConnectionError"}
    assert factor._PRIMED_LIVE["panel"] is None
