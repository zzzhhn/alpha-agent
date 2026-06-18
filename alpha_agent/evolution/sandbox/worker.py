"""Sandbox worker subprocess entrypoint.

Lifecycle:
  1. Module-level imports run BEFORE seccomp is installed (numpy itself
     needs many syscalls during its own import; sealing too early
     would kill the worker before it can do anything).
  2. worker_main(conn) sits in a message loop reading dicts from the pipe.
  3. On FIRST real request: installs RLIMIT + (Linux) seccomp filter.
  4. Per request: builds FRESH globals dict, exec's op_code, calls op_name
     with bound args, writes result ndarray to shared memory, sends back
     a reply dict.
  5. On {"_cmd": "shutdown"} or any uncaught exception during recv: exits.

The reply dict shape is one of:
  {"ok": True,  "result_shm": str, "result_shape": tuple, "result_dtype": str}
  {"ok": False, "kind": <one of 5 SandboxErrorKind values>, "detail": str}

The kind strings match SandboxErrorKind.value (lowercase) so the runner
can map directly via SandboxErrorKind(reply["kind"])."""
from __future__ import annotations

import os
import resource
import signal
import sys
import traceback
from multiprocessing import shared_memory
from multiprocessing.connection import Connection
from typing import Any

import numpy as np


_HARDENED = False
_PER_CALL_TIMEOUT_S = 30


def _install_rlimits() -> None:
    """Wall-clock CPU cap + memory cap + no fork + small fd budget.

    Each setrlimit only lowers the soft limit; the hard limit is preserved
    at its existing value.  Non-root processes cannot raise the hard limit.
    macOS defines RLIMIT_AS but the kernel silently ignores all values other
    than RLIM_INFINITY, so setrlimit raises ValueError there; wrap in
    try/except rather than branching on sys.platform to stay forward-portable."""
    try:
        _, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
        resource.setrlimit(resource.RLIMIT_CPU, (60, cpu_hard))
    except (ValueError, OSError):
        pass  # RLIMIT_CPU not enforceable on this platform

    try:
        _, as_hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, as_hard))
    except (ValueError, OSError):
        pass  # macOS: RLIMIT_AS is defined but not enforceable

    try:
        _, nproc_hard = resource.getrlimit(resource.RLIMIT_NPROC)
        resource.setrlimit(resource.RLIMIT_NPROC, (0, nproc_hard))
    except (ValueError, OSError):
        pass  # macOS does not always honor this; seccomp is the real defense on Linux

    try:
        _, nofile_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, nofile_hard))
    except (ValueError, OSError):
        pass  # defensive; RLIMIT_NOFILE is widely supported but wrap for safety


# Action applied to syscalls NOT on the allow-list. "kill" (prod default) maps
# to SCMP_ACT_KILL_PROCESS: a disallowed syscall kills the WHOLE worker, the
# runner sees a broken pipe and respawns it. (The older SCMP_ACT_KILL_THREAD
# killed only the offending thread, which could leave the worker's main thread
# blocked on the dead thread's futex -> the runner saw an IPC timeout instead of
# a clean death.) Override via the ALPHA_SANDBOX_SECCOMP_ACTION env var:
#   "log" -> SCMP_ACT_LOG: allow every syscall but log the un-allow-listed ones
#            to the audit ring buffer. Audit/tuning mode used to discover the
#            syscalls a new kernel/glibc/numpy build needs (read them back from
#            `dmesg`, add the legitimate ones below), without killing the worker.
#   "off" -> skip seccomp entirely (RLIMIT hardening still applies).
_SECCOMP_ACTION = os.environ.get("ALPHA_SANDBOX_SECCOMP_ACTION", "kill").strip().lower()

# Syscalls a CPython 3.12 + numpy 2.x worker legitimately makes AFTER hardening,
# on x86-64 Linux (glibc 2.39 / ubuntu-noble): memory management, futex/thread
# sync, signal handling (the per-call SIGALRM timeout), pipe + POSIX
# shared-memory IO, randomness, time, and process/resource lookups. The
# genuinely dangerous escape vectors are deliberately ABSENT, so they hit the
# default-deny action: execve/execveat (no new programs), the socket family (no
# network), ptrace / process_vm_* (no cross-process memory), and module / mount
# / namespace / reboot ops. The operator is additionally boxed at the Python
# layer (restricted builtins + numpy-only imports), so it cannot even reach
# allow-listed syscalls like openat/clone directly; seccomp is the backstop.
#
# NOTE: shm_open() is glibc-implemented as openat("/dev/shm/<name>"), so openat
# MUST be allowed for shared-memory IPC to work at all -- its absence is why the
# original minimal list KILLed the worker on the very first request on Linux.
_ALLOWED_SYSCALLS = (
    # --- memory ---
    "read", "write", "readv", "writev", "pread64", "pwrite64",
    "mmap", "mremap", "munmap", "mprotect", "brk", "madvise",
    "mbind",  # glibc malloc sets a NUMA policy when a new arena grows (error path)
    # --- futex / threads / scheduling ---
    "futex", "rseq", "set_robust_list", "get_robust_list", "set_tid_address",
    "clone", "clone3", "sched_yield", "sched_getaffinity", "sched_setaffinity",
    "membarrier", "getcpu",
    # --- signals (per-call SIGALRM timeout) ---
    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigreturn",
    "rt_sigtimedwait", "sigaltstack", "setitimer", "getitimer", "alarm",
    "tgkill", "restart_syscall",
    # --- fds: pipe IPC + shared-memory create/attach ---
    # ioctl: CPython's io layer calls isatty() (ioctl TCGETS) when the exception
    # machinery touches stderr on the error path. Safe here: the operator cannot
    # reach ioctl from Python (no os/fcntl/termios import), and the worker has no
    # controlling TTY (stdio are pipes), so TIOCSTI-style injection is impossible.
    "ioctl",
    "close", "dup", "dup2", "dup3", "fcntl", "lseek", "ftruncate",
    "fstat", "newfstatat", "statx", "lstat", "stat",
    "openat", "open", "unlink", "unlinkat", "readlink", "readlinkat",
    "pipe2", "poll", "ppoll", "select", "pselect6",
    "epoll_create1", "epoll_ctl", "epoll_wait", "epoll_pwait", "eventfd2",
    "memfd_create", "getdents64",
    # --- randomness (glibc / PYTHONHASHSEED) ---
    "getrandom",
    # --- time ---
    "clock_gettime", "clock_getres", "clock_nanosleep", "nanosleep",
    "gettimeofday", "time",
    # --- process / resource info ---
    "getpid", "gettid", "getuid", "geteuid", "getgid", "getegid",
    "getrlimit", "prlimit64", "getrusage", "sysinfo", "uname", "arch_prctl",
    # --- exit ---
    "exit", "exit_group",
)


def _seccomp_default_action(seccomp):
    """Resolve the configured default (non-allow-listed) action."""
    if _SECCOMP_ACTION == "log":
        return seccomp.LOG
    if _SECCOMP_ACTION == "allow":
        return seccomp.ALLOW
    # prod default: kill the whole process on a disallowed syscall.
    return getattr(seccomp, "KILL_PROCESS", seccomp.KILL)


def _install_seccomp_linux() -> None:
    """Default-deny syscall filter: allow only _ALLOWED_SYSCALLS; everything
    else hits the default action (KILL_PROCESS in prod). See _ALLOWED_SYSCALLS
    and _SECCOMP_ACTION for the threat model and the audit/tuning escape hatch."""
    import pyseccomp as seccomp  # noqa: PLC0415 - lazy import; macOS skips this branch
    f = seccomp.SyscallFilter(defaction=_seccomp_default_action(seccomp))
    for name in _ALLOWED_SYSCALLS:
        try:
            f.add_rule(seccomp.ALLOW, name)
        except Exception:
            pass  # syscall absent on this kernel/arch; default-deny keeps it blocked
    f.load()


def _harden_once() -> None:
    global _HARDENED
    if _HARDENED:
        return
    if _SECCOMP_ACTION == "off" or sys.platform != "linux":
        _install_rlimits()
        _HARDENED = True
        return
    # Resolve libseccomp BEFORE _install_rlimits() drops RLIMIT_NPROC to 0.
    # pyseccomp binds the C library at import time via
    # ctypes.util.find_library("seccomp"), which resolves the soname by forking
    # a helper subprocess (gcc / `ldconfig -p`). Once NPROC is 0 that fork fails,
    # find_library returns None, and pyseccomp raises RuntimeError("Unable to
    # find libseccomp"). Importing here (module cache) makes the later lazy
    # import inside _install_seccomp_linux() a no-op: the filter still loads at
    # the same point with identical security posture, but the library is
    # resolved while forking is still allowed.
    import pyseccomp  # noqa: F401, PLC0415 - pre-resolve before rlimits drop NPROC
    _install_rlimits()
    _install_seccomp_linux()
    _HARDENED = True


class _TimeoutError(Exception):
    pass


def _alarm_handler(signum, frame) -> None:
    raise _TimeoutError()


def _attach_array(spec, keep) -> np.ndarray:
    """Wrap (shm_name, dtype, shape) as a live ndarray view; keep the SHM
    handle alive until the reply is sent (closed in the finally block)."""
    shm_name, dtype_str, shape = spec
    shm = shared_memory.SharedMemory(name=shm_name)
    keep.append(shm)
    return np.ndarray(tuple(shape), dtype=np.dtype(dtype_str), buffer=shm.buf)


_ALLOWED_IMPORTS = frozenset({"numpy", "numpy.core", "numpy.lib"})


def _make_restricted_import():
    """Return an __import__ that only allows numpy sub-modules.

    op_code is allowed to write `import numpy as np` even though numpy is
    already injected into the globals dict, because LLM-authored operators
    commonly include the import for readability / self-containedness.  All
    other module imports are blocked with ImportError."""
    import builtins as _b

    _real_import = _b.__import__

    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root not in _ALLOWED_IMPORTS and name not in _ALLOWED_IMPORTS:
            raise ImportError(f"import of {name!r} is not allowed in sandbox")
        return _real_import(name, globals, locals, fromlist, level)

    return _restricted_import


def _restricted_builtins() -> dict:
    """A minimal subset of builtins; the rest are unreachable from op_code.
    No open / no eval / no compile / no arbitrary __import__ / no getattr /
    no setattr.  __import__ is present but restricted to numpy only."""
    safe_names = (
        "abs", "all", "any", "bool", "dict", "enumerate", "float",
        "int", "len", "list", "max", "min", "range", "round", "set",
        "sorted", "str", "sum", "tuple", "zip",
        "isinstance", "ValueError", "TypeError", "Exception",
    )
    import builtins as _b
    ns = {n: getattr(_b, n) for n in safe_names if hasattr(_b, n)}
    ns["True"] = True
    ns["False"] = False
    ns["None"] = None
    ns["__import__"] = _make_restricted_import()
    return ns


def _process_one(msg: dict) -> dict:
    """Run one request and return the reply dict. Does NOT touch the pipe."""
    op_code = msg["op_code"]
    op_name = msg["op_name"]
    arg_specs = msg.get("args") or {}
    kwargs = msg.get("kwargs") or {}
    expected_shape = msg.get("expected_shape")
    keep: list = []
    try:
        args = {k: _attach_array(v, keep) if isinstance(v, tuple) else v
                for k, v in arg_specs.items()}
        ns: dict[str, Any] = {"np": np, "__builtins__": _restricted_builtins()}
        # FRESH globals per call: worker reuse cannot leak operator-A state into operator-B.
        exec(compile(op_code, "<sandbox>", "exec"), ns)
        fn = ns.get(op_name)
        if not callable(fn):
            return {"ok": False, "kind": "signature_mismatch",
                    "detail": f"no callable named {op_name!r} in op_code"}
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(_PER_CALL_TIMEOUT_S)
        try:
            result = fn(**args, **kwargs)
        finally:
            signal.alarm(0)
        if not isinstance(result, np.ndarray):
            return {"ok": False, "kind": "shape_mismatch",
                    "detail": f"op returned {type(result).__name__}, expected ndarray"}
        if expected_shape is not None and tuple(result.shape) != tuple(expected_shape):
            return {"ok": False, "kind": "shape_mismatch",
                    "detail": f"expected {tuple(expected_shape)}, got {tuple(result.shape)}"}
        out_shm = shared_memory.SharedMemory(create=True, size=max(result.nbytes, 1))
        # NOTE: shm.size may exceed result.nbytes (rounded to page); we record
        # the canonical result.shape + dtype so the runner reconstructs the
        # exact view, not the page-padded raw buffer.
        np.ndarray(result.shape, dtype=result.dtype, buffer=out_shm.buf)[:] = result
        try:
            reply = {"ok": True, "result_shm": out_shm.name,
                     "result_shape": tuple(result.shape),
                     "result_dtype": str(result.dtype)}
        finally:
            out_shm.close()  # parent unlinks after consuming
        return reply
    except _TimeoutError:
        return {"ok": False, "kind": "timeout",
                "detail": f"exceeded {_PER_CALL_TIMEOUT_S} s"}
    except Exception as e:  # noqa: BLE001 - structured response, not silent
        return {"ok": False, "kind": "exception",
                "detail": f"{type(e).__name__}: {e}\n{traceback.format_exc()[:1500]}"}
    finally:
        for shm in keep:
            try:
                shm.close()
            except Exception:
                pass


def eval_op_inprocess(
    op_code: str,
    op_name: str,
    args: dict[str, Any],
    kwargs: dict | None = None,
    expected_shape: tuple | None = None,
) -> "np.ndarray | object":
    """Execute op_code in restricted globals IN THE CALLING PROCESS.

    Used by SandboxRunner when SERVERLESS=true (Vercel Python runtime cannot
    spawn the multiprocessing worker pool because /dev/shm is unavailable in
    the function sandbox). Sacrifices process-level isolation for runtime
    compatibility; defense-in-depth via restricted __builtins__ + restricted
    __import__ still applies, and the Vercel function itself is sandboxed at
    a higher level.

    Returns either an ndarray result or a SandboxError. Does NOT use shared
    memory, does NOT install RLIMIT/seccomp (those would affect the main
    FastAPI process), does NOT use SIGALRM (the Vercel function maxDuration
    of 300s caps runaway code instead)."""
    from alpha_agent.evolution.sandbox.errors import SandboxError, SandboxErrorKind

    try:
        ns: dict[str, Any] = {"np": np, "__builtins__": _restricted_builtins()}
        exec(compile(op_code, "<sandbox-inprocess>", "exec"), ns)
    except Exception as e:  # noqa: BLE001 - structured error
        return SandboxError(
            SandboxErrorKind.EXCEPTION,
            f"compile/exec failed: {type(e).__name__}: {e}",
            op_name,
        )

    fn = ns.get(op_name)
    if not callable(fn):
        return SandboxError(
            SandboxErrorKind.SIGNATURE_MISMATCH,
            f"no callable named {op_name!r} in op_code",
            op_name,
        )

    try:
        result = fn(**args, **(kwargs or {}))
    except Exception as e:  # noqa: BLE001 - structured error
        return SandboxError(
            SandboxErrorKind.EXCEPTION,
            f"{type(e).__name__}: {e}\n{traceback.format_exc()[:1500]}",
            op_name,
        )

    if not isinstance(result, np.ndarray):
        return SandboxError(
            SandboxErrorKind.SHAPE_MISMATCH,
            f"op returned {type(result).__name__}, expected ndarray",
            op_name,
        )
    if expected_shape is not None and tuple(result.shape) != tuple(expected_shape):
        return SandboxError(
            SandboxErrorKind.SHAPE_MISMATCH,
            f"expected {tuple(expected_shape)}, got {tuple(result.shape)}",
            op_name,
        )
    return result.copy()


def worker_main(conn: Connection) -> None:
    while True:
        try:
            msg = conn.recv()
        except (EOFError, ConnectionResetError):
            return
        if not isinstance(msg, dict):
            continue
        if msg.get("_cmd") == "shutdown":
            return
        try:
            _harden_once()
        except Exception as e:  # noqa: BLE001 - structured response, then exit
            try:
                conn.send({"ok": False, "kind": "exception",
                           "detail": f"harden failed: {type(e).__name__}: {e}"})
            except Exception:
                pass
            return  # if hardening fails, the worker is no longer safe; exit
        reply = _process_one(msg)
        try:
            conn.send(reply)
        except (BrokenPipeError, EOFError):
            return
