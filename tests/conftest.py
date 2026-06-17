import os

import pytest

from tests.storage.conftest import postgresql_proc, postgresql, test_db_url, applied_db  # noqa: F401


@pytest.fixture(autouse=True)
def _restore_environ():
    """Snapshot + restore os.environ around every test.

    Some helpers set process env directly (e.g. os.environ.setdefault(
    "SERVERLESS", "true") in the factor-backtest API helper) instead of via
    monkeypatch, leaking into later tests: a leaked SERVERLESS=true flips the
    SandboxRunner into serverless mode and fails its worker-status test, which
    passes standalone. Restoring the snapshot makes env state test-local
    regardless of how a test mutates it.
    """
    snapshot = dict(os.environ)
    # config_store keeps a process-global knob cache (_CACHE); a test that sets
    # a knob without refreshing leaks it into later tests. Clear it around each
    # test so config state is test-local too.
    try:
        from alpha_agent import config_store

        config_store._CACHE.clear()
    except Exception:
        config_store = None

    # confidence_calibration memoizes the active calibration map in a process
    # global (_cal_cache, 600s TTL). A test that stores+reads a calibration
    # leaves it cached, so a later test's load_active_calibration returns the
    # stale map instead of querying its own (clean) DB. Reset it per test.
    def _reset_cal_cache():
        try:
            from alpha_agent.backtest import confidence_calibration as _cc

            _cc._cal_cache["ts"] = None
            _cc._cal_cache["val"] = None
        except Exception:
            pass

    _reset_cal_cache()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
    if config_store is not None:
        config_store._CACHE.clear()
    _reset_cal_cache()


@pytest.fixture(autouse=True)
def _reset_db_pool():
    """Reset the process-global asyncpg pool around every test.

    alpha_agent.storage.postgres.get_pool is a singleton that RAISES
    ("Pool already exists for X; got Y") when reused with a different DSN. Each
    test gets a fresh ephemeral pytest-postgresql DB (a new DSN), so a pool
    leaked by one test makes the NEXT test's get_pool raise. That was the bulk
    of the CI DB-test errors (they passed standalone, failed in the full suite).

    SYNC + terminate() (not async close()): asyncpg pools are bound to the loop
    they were created in, so awaiting pool.close() from this fixture raises
    RuntimeError for sync tests and across pytest_asyncio's per-test loops (and
    it poisons the next test). terminate() force-closes connections synchronously
    with no loop dependency, freeing connections without the cross-loop error;
    we then null the singleton so get_pool rebuilds. Tests with their own `pool`
    fixture still await close_pool() in-loop first; this is the safety net.
    """
    from alpha_agent.storage import postgres

    def _reset():
        p = postgres._pool
        postgres._pool = None
        postgres._pool_dsn = None
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass

    _reset()
    yield
    _reset()
