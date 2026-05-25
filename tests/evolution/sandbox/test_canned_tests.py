import pytest

from alpha_agent.evolution.sandbox.canned_tests import CannedTestResult, run_canned_tests
from alpha_agent.evolution.sandbox.runner import SandboxRunner


@pytest.fixture(scope="module")
def runner():
    r = SandboxRunner()
    yield r
    r.close()


def test_canned_passes_well_formed_op(runner):
    op_code = "import numpy as np\ndef lf_ok(x):\n    return np.where(np.isnan(x), 0.0, x * 2)"
    result = run_canned_tests(runner, op_code=op_code, op_name="lf_ok",
                              signature="(x: ndarray) -> ndarray")
    assert isinstance(result, CannedTestResult)
    assert result.passed is True, result.tests
    assert len(result.tests) == 3
    assert all(t["passed"] for t in result.tests)
    names = [t["name"] for t in result.tests]
    assert names == ["signature", "nan_propagation", "shape_preservation"]


def test_canned_fails_op_that_returns_scalar(runner):
    op_code = "def lf_scalar(x):\n    return float(x.sum())"
    result = run_canned_tests(runner, op_code=op_code, op_name="lf_scalar",
                              signature="(x: ndarray) -> ndarray")
    assert result.passed is False
    failed = [t for t in result.tests if not t["passed"]]
    # The scalar-return failure manifests as either shape_preservation or
    # nan_propagation failing (both probe shape). Signature passes because
    # the function exists by name.
    assert any(t["name"] in ("shape_preservation", "nan_propagation") for t in failed)


def test_canned_fails_op_that_crashes_on_nan(runner):
    op_code = ("def lf_intolerant(x):\n"
               "    if not (x == x).all():\n"
               "        raise ValueError('no NaN allowed')\n"
               "    return x")
    result = run_canned_tests(runner, op_code=op_code, op_name="lf_intolerant",
                              signature="(x: ndarray) -> ndarray")
    assert result.passed is False
    nan_test = [t for t in result.tests if t["name"] == "nan_propagation"][0]
    assert nan_test["passed"] is False
    assert "ValueError" in nan_test["detail"] or "no NaN" in nan_test["detail"]


def test_canned_reports_3_tests_in_order(runner):
    """Visibility UX: the UI renders tests in a fixed order."""
    op_code = "def lf_x(x): return x"
    result = run_canned_tests(runner, op_code=op_code, op_name="lf_x",
                              signature="(x: ndarray) -> ndarray")
    names = [t["name"] for t in result.tests]
    assert names == ["signature", "nan_propagation", "shape_preservation"]
