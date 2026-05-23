"""SandboxRunner: persistent worker pool + shared-memory ndarray IPC.

Pool layout: a list of _WorkerHandle slots, size = POOL_SIZE_DEFAULT (2).
Requests are dispatched round-robin. A worker is REPLACED on the next call
that lands on its slot if:
  (a) the process is dead (uncaught exception killed it, or seccomp KILL),
  (b) its call count >= RECYCLE_AFTER_CALLS, or
  (c) its age >= RECYCLE_AFTER_SECONDS.

The recycle policy bounds blast radius from any latent operator that
accumulates state or destabilizes the worker over time."""
from __future__ import annotations

import multiprocessing as mp
import os
import time
from dataclasses import dataclass, field
from multiprocessing import shared_memory
from typing import Any

import numpy as np

from alpha_agent.evolution.sandbox.errors import SandboxError, SandboxErrorKind
from alpha_agent.evolution.sandbox.worker import eval_op_inprocess, worker_main

POOL_SIZE_DEFAULT = 2
RECYCLE_AFTER_CALLS = 1000
RECYCLE_AFTER_SECONDS = 600
_IPC_POLL_TIMEOUT_S = 35  # slightly above the worker's 30s alarm

# Vercel Python serverless cannot spawn a multiprocessing pool with shared
# memory; /dev/shm is not writable in the function sandbox and the spawn
# context hangs on shared_memory.SharedMemory(create=True). When SERVERLESS
# is set (api/index.py defaults it to "true"), bypass the subprocess pool
# entirely and run operator eval in-process via eval_op_inprocess. AutoDL or
# any non-Vercel deployment leaves SERVERLESS unset and gets the full
# subprocess sandbox.
_SERVERLESS = os.environ.get("SERVERLESS", "").lower() == "true"


@dataclass
class _WorkerHandle:
    process: mp.Process
    conn: Any
    calls: int = 0
    started_at: float = field(default_factory=time.monotonic)
    last_error: str | None = None


class SandboxRunner:
    """Persistent pool of worker subprocesses. Thread-safe ONLY for sequential
    calls (the validator and runtime dispatch are sequential per panel pass)."""

    def __init__(self, pool_size: int = POOL_SIZE_DEFAULT) -> None:
        self.pool_size = pool_size
        self._workers: list[_WorkerHandle | None] = [None] * pool_size
        self._next_idx = 0
        self._total_calls = 0
        self._serverless = _SERVERLESS
        # In serverless mode the spawn context is never used; skipping the
        # initialization avoids importing multiprocessing.popen_spawn_posix
        # which itself touches platform features the Vercel sandbox blocks.
        self._ctx = None if self._serverless else mp.get_context("spawn")

    def _spawn(self) -> _WorkerHandle:
        parent_conn, child_conn = self._ctx.Pipe()
        p = self._ctx.Process(target=worker_main, args=(child_conn,), daemon=True)
        p.start()
        return _WorkerHandle(process=p, conn=parent_conn)

    def _get_worker(self, idx: int) -> _WorkerHandle:
        h = self._workers[idx]
        needs_replacement = (
            h is None
            or not h.process.is_alive()
            or h.calls >= RECYCLE_AFTER_CALLS
            or (time.monotonic() - h.started_at) >= RECYCLE_AFTER_SECONDS
        )
        if needs_replacement:
            if h is not None:
                self._kill(h)
            h = self._spawn()
            self._workers[idx] = h
        return h

    def _kill(self, h: _WorkerHandle) -> None:
        try:
            h.conn.send({"_cmd": "shutdown"})
        except Exception:  # noqa: BLE001 - best-effort shutdown signal
            pass
        h.process.join(timeout=1)
        if h.process.is_alive():
            h.process.terminate()
            h.process.join(timeout=1)
        try:
            h.conn.close()
        except Exception:  # noqa: BLE001 - already closed is fine
            pass

    def evaluate(self, op_code: str, op_name: str,
                 args: dict[str, Any],
                 kwargs: dict | None = None,
                 expected_shape: tuple | None = None) -> np.ndarray | SandboxError:
        self._total_calls += 1
        if self._serverless:
            # In-process exec branch: no subprocess pool, no shared memory.
            # eval_op_inprocess returns either an ndarray or a SandboxError
            # with the same kind discriminants the subprocess path returns,
            # so downstream consumers see one contract regardless of mode.
            return eval_op_inprocess(  # type: ignore[return-value]
                op_code=op_code,
                op_name=op_name,
                args=args,
                kwargs=kwargs,
                expected_shape=expected_shape,
            )
        idx = self._next_idx
        self._next_idx = (self._next_idx + 1) % self.pool_size
        h = self._get_worker(idx)
        h.calls += 1
        in_shms: list[shared_memory.SharedMemory] = []
        arg_specs: dict[str, Any] = {}
        # Marshal ndarrays into shared memory; scalars pass through directly.
        for name, value in args.items():
            if isinstance(value, np.ndarray):
                shm = shared_memory.SharedMemory(create=True, size=max(value.nbytes, 1))
                np.ndarray(value.shape, dtype=value.dtype, buffer=shm.buf)[:] = value
                arg_specs[name] = (shm.name, str(value.dtype), tuple(value.shape))
                in_shms.append(shm)
            else:
                arg_specs[name] = value
        try:
            h.conn.send({
                "op_code": op_code, "op_name": op_name,
                "args": arg_specs, "kwargs": kwargs or {},
                "expected_shape": expected_shape,
            })
            if not h.conn.poll(_IPC_POLL_TIMEOUT_S):
                h.last_error = "runner-side IPC timeout"
                self._kill(h)
                self._workers[idx] = None
                return SandboxError(SandboxErrorKind.TIMEOUT,
                                    "runner-side IPC timeout", op_name)
            reply = h.conn.recv()
        except (EOFError, BrokenPipeError, ConnectionResetError) as e:
            # Worker died (likely seccomp KILL or RLIMIT KILL). Surface as
            # EXCEPTION because from this side we cannot distinguish seccomp
            # KILL from a crash without checking exitcode (which is a future
            # enhancement; if exitcode == -9 we could switch to SYSCALL_BLOCKED).
            h.last_error = f"{type(e).__name__}: {e}"
            self._kill(h)
            self._workers[idx] = None
            return SandboxError(SandboxErrorKind.EXCEPTION,
                                f"worker died: {h.last_error}", op_name)
        finally:
            for shm in in_shms:
                try:
                    shm.close()
                    shm.unlink()
                except FileNotFoundError:
                    pass
        if reply.get("ok"):
            out_shm = shared_memory.SharedMemory(name=reply["result_shm"])
            try:
                out = np.ndarray(
                    reply["result_shape"],
                    dtype=np.dtype(reply["result_dtype"]),
                    buffer=out_shm.buf,
                ).copy()
            finally:
                out_shm.close()
                try:
                    out_shm.unlink()
                except FileNotFoundError:
                    pass
            return out
        # Structured error: map reply["kind"] to SandboxErrorKind enum.
        try:
            kind = SandboxErrorKind(reply.get("kind", "exception"))
        except ValueError:
            kind = SandboxErrorKind.EXCEPTION
        return SandboxError(kind, reply.get("detail", ""), op_name)

    def stat(self) -> dict:
        return {
            "pool_size": self.pool_size,
            "total_calls": self._total_calls,
            "workers": [
                {
                    "alive": (h is not None and h.process.is_alive()),
                    "calls": (h.calls if h else 0),
                    "last_error": (h.last_error if h else None),
                    "age_s": (time.monotonic() - h.started_at) if h else None,
                }
                for h in self._workers
            ],
        }

    def close(self) -> None:
        if self._serverless:
            # No pool to tear down.
            return
        for h in self._workers:
            if h is not None:
                self._kill(h)
        self._workers = [None] * self.pool_size
