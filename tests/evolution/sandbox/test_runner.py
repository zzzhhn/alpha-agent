import numpy as np
import pytest

from alpha_agent.evolution.sandbox.errors import SandboxError, SandboxErrorKind
from alpha_agent.evolution.sandbox.runner import (
    POOL_SIZE_DEFAULT,
    SandboxRunner,
)


@pytest.fixture
def runner():
    r = SandboxRunner()
    yield r
    r.close()


def test_pool_starts_with_configured_size(runner):
    """Visibility UX: stat() reports the configured size up front."""
    assert runner.pool_size == POOL_SIZE_DEFAULT == 2


def test_evaluate_returns_ndarray_on_happy_path(runner):
    op_code = "import numpy as np\ndef lf_triple(x):\n    return x * 3"
    out = runner.evaluate(op_code=op_code, op_name="lf_triple",
                          args={"x": np.arange(5, dtype=np.float64)})
    assert isinstance(out, np.ndarray)
    assert np.array_equal(out, np.arange(5) * 3)


def test_evaluate_returns_sandbox_error_on_runtime_failure(runner):
    op_code = "def lf_die(x):\n    return undefined_name"
    out = runner.evaluate(op_code=op_code, op_name="lf_die",
                          args={"x": np.zeros(3)})
    assert isinstance(out, SandboxError)
    assert out.kind == SandboxErrorKind.EXCEPTION
    assert "undefined_name" in out.detail or "NameError" in out.detail


def test_evaluate_returns_signature_mismatch_when_name_missing(runner):
    out = runner.evaluate(op_code="def other(x): return x",
                          op_name="lf_expected", args={"x": np.zeros(1)})
    assert isinstance(out, SandboxError)
    assert out.kind == SandboxErrorKind.SIGNATURE_MISMATCH


def test_evaluate_returns_shape_mismatch_when_scalar_returned(runner):
    op_code = "def lf_scalar(x):\n    return float(x.sum())"
    out = runner.evaluate(op_code=op_code, op_name="lf_scalar",
                          args={"x": np.ones(4)})
    assert isinstance(out, SandboxError)
    assert out.kind == SandboxErrorKind.SHAPE_MISMATCH


def test_pool_recovers_after_an_exception_in_one_call(runner):
    """Forgiveness UX: a bad op never poisons the pool. The same worker
    keeps serving (the worker returns a structured error and stays alive)."""
    op_code_bad = "def lf_boom(x):\n    raise ValueError('boom')"
    r1 = runner.evaluate(op_code=op_code_bad, op_name="lf_boom",
                         args={"x": np.zeros(1)})
    assert isinstance(r1, SandboxError) and r1.kind == SandboxErrorKind.EXCEPTION
    # Next call should still succeed.
    r2 = runner.evaluate(op_code="def lf_ok(x): return x",
                         op_name="lf_ok", args={"x": np.ones(3)})
    assert isinstance(r2, np.ndarray) and np.array_equal(r2, np.ones(3))


def test_stat_tracks_calls_and_worker_status(runner):
    """Visibility UX: /api/healthz/sandbox reads this."""
    op_code = "def lf_id(x): return x"
    for _ in range(3):
        runner.evaluate(op_code=op_code, op_name="lf_id", args={"x": np.zeros(1)})
    stat = runner.stat()
    assert stat["pool_size"] == POOL_SIZE_DEFAULT
    assert stat["total_calls"] >= 3
    assert "workers" in stat and len(stat["workers"]) == POOL_SIZE_DEFAULT
    # At least one worker should be alive after work was done.
    assert any(w["alive"] for w in stat["workers"])
