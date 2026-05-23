"""Phase 3b: /api/healthz/sandbox observability endpoint test.

The endpoint must always return 200 with a JSON body containing
pool_size, workers, total_calls (from SandboxRunner.stat()) plus an
init_error field. If init_error is non-null the pool did NOT come up
(e.g. multiprocessing blocked); the endpoint still returns 200 so
callers can read the reason.
"""
from __future__ import annotations


def test_healthz_sandbox_reports_pool_size_and_init_error_field(client_with_db):
    """The endpoint must always return a JSON with keys pool_size, workers,
    total_calls (from SandboxRunner.stat()) plus an init_error field. If
    init_error is non-null the pool did NOT come up (e.g. multiprocessing
    blocked); the endpoint still returns 200 so callers can read the reason."""
    r = client_with_db.get("/api/healthz/sandbox")
    assert r.status_code == 200, r.text
    body = r.json()
    # Either the pool initialized cleanly (pool_size + workers present), or
    # init_error reports why it failed.
    if body.get("init_error") is None:
        assert body["pool_size"] == 2
        assert "total_calls" in body
        assert len(body["workers"]) == 2
    else:
        # On a hostile runtime (no fork/spawn), the endpoint still surfaces
        # the reason instead of 500ing. This is the design.
        assert isinstance(body["init_error"], str)
        assert len(body["init_error"]) > 0
