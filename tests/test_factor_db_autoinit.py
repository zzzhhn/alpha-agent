"""Test that storage.factor_db.get_engine() auto-creates schema on first
acquisition.

Regression guard for the bug surfaced 2026-05-06: scripts that hit the DB
directly (verify_insider_alpha.py, ad-hoc workers) saw `OperationalError:
no such table: factors` because init_schema() was only ever called when
the API route module `alpha_agent.api.routes.factors_db` was imported.

Fix: get_engine() now runs `Base.metadata.create_all` once per process
(guarded by `_schema_ready` flag).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import inspect


@pytest.fixture
def isolated_sqlite(monkeypatch):
    """Point factor_db at a brand-new empty sqlite file and reset its module
    state so each test gets a fresh engine + schema-ready flag."""
    tmp = Path(tempfile.mkdtemp()) / "isolated_factor_db.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp}")
    # Reset factor_db module-level singletons so the test sees a cold start.
    import alpha_agent.storage.factor_db as fdb
    fdb._engine = None
    fdb._schema_ready = False
    yield fdb, tmp
    # Cleanup: clear module state again so subsequent tests don't see our DB.
    fdb._engine = None
    fdb._schema_ready = False


def test_get_engine_creates_schema_on_first_acquisition(isolated_sqlite):
    """First get_engine() call should leave the DB with the `factors` and
    `factor_runs` tables present, even though we never explicitly called
    init_schema()."""
    fdb, tmp_path = isolated_sqlite
    assert tmp_path.exists() is False or tmp_path.stat().st_size == 0, (
        "test fixture leaked a previous DB"
    )

    engine = fdb.get_engine()

    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    assert "factors" in table_names, f"factors table missing; got {table_names}"
    assert "factor_runs" in table_names, f"factor_runs table missing; got {table_names}"


def test_get_engine_idempotent(isolated_sqlite):
    """Calling get_engine() twice must not re-run create_all (the
    `_schema_ready` flag flips after the first call)."""
    fdb, _ = isolated_sqlite
    fdb.get_engine()
    assert fdb._schema_ready is True
    # Second call: same engine, no error.
    e2 = fdb.get_engine()
    assert e2 is fdb._engine


def test_record_run_works_without_explicit_init(isolated_sqlite):
    """End-to-end: write a fake factor row and a run row through the
    public API. This is the exact path that was failing in
    verify_insider_alpha.py before the fix."""
    fdb, _ = isolated_sqlite
    factor_id = fdb.upsert_factor(
        name="test_factor",
        expression="rank(close)",
        operators_used=["rank"],
        hypothesis="cheap test",
        last_run_summary={
            "direction": "long_short", "neutralize": "none",
            "benchmark": "SPY", "test_sharpe": 1.0, "test_ic": 0.05,
            "alpha_t": 2.0, "alpha_p": 0.05, "psr": 0.8,
            "overfit_flag": False,
        },
    )
    assert factor_id, "upsert_factor must return a non-empty id"

    fdb.record_run(
        factor_id=factor_id,
        panel_version="sp500_v3",
        direction="long_short",
        neutralize="none",
        benchmark_ticker="SPY",
        top_pct=0.30, bottom_pct=0.30,
        transaction_cost_bps=0.0,
        test_sharpe=1.0, test_ic=0.05, test_psr=0.8,
        alpha_annualized=0.05, alpha_t=2.0, alpha_p=0.05,
        beta=0.1, r_squared=0.05, overfit_flag=False,
        daily_ic=[0.01, 0.02, -0.01, 0.03],
    )

    runs = fdb.get_factor_runs(factor_id, limit=10)
    assert len(runs) == 1
    assert runs[0]["panel_version"] == "sp500_v3"
