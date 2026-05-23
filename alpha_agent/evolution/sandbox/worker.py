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


def _install_seccomp_linux() -> None:
    """Allow only the minimal syscall set needed for numpy compute + shm IO.
    Any other syscall hits the default-KILL path and the worker dies; the
    runner sees a broken pipe + respawns."""
    import pyseccomp as seccomp  # noqa: PLC0415 - lazy import; macOS skips this branch
    f = seccomp.SyscallFilter(defaction=seccomp.KILL)
    for name in (
        "read", "write", "mmap", "mremap", "munmap", "brk", "futex",
        "sigreturn", "rt_sigreturn", "rt_sigaction", "rt_sigprocmask",
        "exit_group", "exit", "shm_open", "shm_unlink",
        "fstat", "newfstatat", "lseek", "close",
        "getpid", "gettid",
        "clock_gettime", "clock_nanosleep",
    ):
        try:
            f.add_rule(seccomp.ALLOW, name)
        except Exception:
            pass  # syscall not available on this kernel/arch; skip silently is OK
                  # because the default is KILL, so missing rules just stay blocked
    f.load()


def _harden_once() -> None:
    global _HARDENED
    if _HARDENED:
        return
    _install_rlimits()
    if sys.platform == "linux":
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
