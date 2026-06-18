"""Audit which syscalls the sandbox worker actually uses on THIS kernel.

Runs a representative numpy op through the real SandboxRunner with the seccomp
filter in LOG mode (ALPHA_SANDBOX_SECCOMP_ACTION=log): every syscall is allowed,
but any syscall NOT on worker._ALLOWED_SYSCALLS is logged to the kernel audit
ring buffer. We then read those back from `dmesg`, resolve the numbers to names
via pyseccomp, and print the set that the allow-list is still missing.

This is a tuning tool, not a test. It is invoked manually via the
_seccomp_audit.yml workflow on a real Linux runner; macOS has no seccomp.

Usage (on Linux):
    sudo dmesg -C                 # clear the ring buffer first
    ALPHA_SANDBOX_SECCOMP_ACTION=log python scripts/seccomp_audit.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import numpy as np


def _run_representative_ops() -> list[str]:
    """Exercise the worker across a few numpy code paths; return result reprs."""
    # Force the subprocess sandbox (not the in-process serverless branch).
    os.environ.pop("SERVERLESS", None)
    os.environ["ALPHA_SANDBOX_SECCOMP_ACTION"] = "log"

    from alpha_agent.evolution.sandbox.runner import SandboxRunner

    runner = SandboxRunner()
    outcomes: list[str] = []
    x = np.arange(256, dtype=np.float64)
    ops = [
        ("scale", "def scale(x):\n    return x * 2.0 + 1.0\n"),
        ("reduce", "def reduce(x):\n    import numpy as np\n    return np.cumsum(x)\n"),
        ("matmul", "def matmul(x):\n    import numpy as np\n"
                   "    m = x[:64].reshape(8, 8)\n    return (m @ m).ravel()\n"),
    ]
    for name, code in ops:
        res = runner.evaluate(code, name, args={"x": x})
        if isinstance(res, np.ndarray):
            outcomes.append(f"{name}: ok shape={res.shape}")
        else:
            outcomes.append(f"{name}: ERROR {res!r}")
    runner.close()
    return outcomes


def _missing_syscalls() -> list[str]:
    """Read dmesg, resolve logged syscall numbers, drop the allow-listed ones."""
    import pyseccomp

    from alpha_agent.evolution.sandbox.worker import _ALLOWED_SYSCALLS

    dmesg = subprocess.run(
        ["sudo", "dmesg"], capture_output=True, text=True, check=False
    ).stdout
    nums = sorted({int(n) for n in re.findall(r"syscall=(\d+)", dmesg)})
    allowed = set(_ALLOWED_SYSCALLS)
    missing: list[str] = []
    for n in nums:
        try:
            name = pyseccomp.resolve_syscall(pyseccomp.Arch.NATIVE, n)
        except Exception:  # noqa: BLE001 - unknown number on this arch; report raw
            missing.append(f"<num {n}>")
            continue
        if isinstance(name, bytes):
            name = name.decode()
        if name not in allowed:
            missing.append(name)
    return sorted(set(missing))


def main() -> int:
    if sys.platform != "linux":
        print("not linux; seccomp is a no-op here. run this on the CI runner.")
        return 0
    outcomes = _run_representative_ops()
    print("=== op outcomes (must all be 'ok' for the allow-list to be usable) ===")
    for line in outcomes:
        print("  ", line)
    missing = _missing_syscalls()
    print("=== syscalls used but NOT on _ALLOWED_SYSCALLS ===")
    if missing:
        print("MISSING_SYSCALLS:", ", ".join(missing))
    else:
        print("MISSING_SYSCALLS: (none) -- allow-list is complete for this kernel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
