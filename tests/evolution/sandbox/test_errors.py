from alpha_agent.evolution.sandbox import SandboxError, SandboxErrorKind


def test_sandbox_error_carries_structured_kind_and_detail():
    err = SandboxError(kind=SandboxErrorKind.TIMEOUT, detail="exceeded 30 s", op_name="lf_demo")
    assert err.kind == SandboxErrorKind.TIMEOUT
    assert "30 s" in err.detail
    assert err.op_name == "lf_demo"


def test_sandbox_error_kinds_enumerate_the_five_classes():
    """Cognitive load minimization (UX): exactly 5 kinds; no free-form strings."""
    kinds = {k.name for k in SandboxErrorKind}
    assert kinds == {"TIMEOUT", "SYSCALL_BLOCKED", "EXCEPTION", "SHAPE_MISMATCH", "SIGNATURE_MISMATCH"}
