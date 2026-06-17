"""Skip the seccomp-hardened sandbox tests when seccomp can't initialize.

The SandboxRunner hardens each worker with seccomp via pyseccomp (Linux only;
macOS skips the seccomp branch and harden is a no-op). On a Linux host whose
pyseccomp cannot load libseccomp, harden() raises "Unable to find libseccomp"
and these tests fail for an environment reason, not a code regression. Skip
them there so the strict CI gate stays green where seccomp is genuinely
unavailable, while still running them on macOS and on Linux with a working
libseccomp.
"""
import sys

import pytest


def _seccomp_unavailable_on_linux() -> bool:
    if sys.platform != "linux":
        return False  # macOS / other: harden() no-ops, tests are valid
    try:
        import pyseccomp as _s

        # Constructing a filter loads libseccomp; no .load(), so no syscall
        # restriction is applied to this process.
        _s.SyscallFilter(defaction=_s.KILL)
        return False
    except Exception:
        return True


_SKIP = _seccomp_unavailable_on_linux()


@pytest.fixture(autouse=True)
def _require_working_seccomp():
    if _SKIP:
        pytest.skip(
            "libseccomp unavailable on this Linux host (pyseccomp cannot load it); "
            "seccomp-hardened sandbox tests require it"
        )
