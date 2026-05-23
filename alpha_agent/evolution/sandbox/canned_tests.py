"""Three canned tests per LLM-authored operator: signature, NaN propagation,
shape preservation. The validator (3c) calls run_canned_tests once per new
operator; only candidates whose new ops all pass move to the OOS validation
stage. UX: exactly 3 tests with stable names so the UI can render them
in a known order with structured failure detail per test."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from alpha_agent.evolution.sandbox.errors import SandboxError
from alpha_agent.evolution.sandbox.runner import SandboxRunner


@dataclass(frozen=True)
class CannedTestResult:
    """passed=True iff all three tests passed; tests carries per-test outcome
    in stable order [signature, nan_propagation, shape_preservation]."""
    passed: bool
    tests: list[dict]  # entries: {"name": str, "passed": bool, "detail": str}


def _classify(out, expected_n: int) -> tuple[bool, str]:
    """Map an evaluate() result to (passed, detail) for a per-test outcome.
    A SandboxError is always a fail. A non-ndarray result is always a fail.
    A shape mismatch (expected (N,), got something else) is a fail."""
    if isinstance(out, SandboxError):
        return False, f"{out.kind.value}: {out.detail[:200]}"
    if not isinstance(out, np.ndarray):
        return False, f"returned {type(out).__name__}, expected ndarray"
    if out.shape != (expected_n,):
        return False, f"returned shape {out.shape}, expected ({expected_n},)"
    return True, ""


def run_canned_tests(runner: SandboxRunner, op_code: str, op_name: str,
                     signature: str) -> CannedTestResult:
    """Run the 3-test harness against `op_code`. The `signature` arg is
    currently informational (recorded in evidence by the validator); the
    harness probes behavior, not the signature string itself."""
    tests: list[dict] = []

    # Test 1: signature. Small deterministic ndarray probes that the named
    # function exists and accepts ndarray input without crashing.
    sig_input = np.arange(8, dtype=np.float64)
    out = runner.evaluate(op_code=op_code, op_name=op_name, args={"x": sig_input})
    passed, detail = _classify(out, expected_n=8)
    tests.append({"name": "signature", "passed": passed, "detail": detail})

    # Test 2: NaN propagation. All-NaN input must not crash; must return
    # an ndarray of the same length (the operator may produce NaNs in the
    # output; that is fine, we only enforce no-crash + shape).
    nan_input = np.full(8, np.nan, dtype=np.float64)
    out = runner.evaluate(op_code=op_code, op_name=op_name, args={"x": nan_input})
    passed, detail = _classify(out, expected_n=8)
    tests.append({"name": "nan_propagation", "passed": passed, "detail": detail})

    # Test 3: shape preservation. (N,) input -> (N,) output, with N != 8 to
    # catch hardcoded sizes.
    shape_input = np.linspace(0.0, 1.0, 16)
    out = runner.evaluate(op_code=op_code, op_name=op_name, args={"x": shape_input})
    passed, detail = _classify(out, expected_n=16)
    tests.append({"name": "shape_preservation", "passed": passed, "detail": detail})

    return CannedTestResult(passed=all(t["passed"] for t in tests), tests=tests)
