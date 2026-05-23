"""Cross-platform smoke tests for the worker subprocess (happy path).
Security-specific tests (seccomp-blocked syscalls) are deferred to a
Linux-only test in a later phase; here we just verify the happy paths +
the 2 structured error paths (signature mismatch, runtime exception)."""
import multiprocessing as mp

import numpy as np

from alpha_agent.evolution.sandbox.worker import worker_main


def _run_one(op_code, op_name, args, kwargs=None, expected_shape=None, timeout=10.0):
    parent_conn, child_conn = mp.Pipe()
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=worker_main, args=(child_conn,))
    p.start()
    try:
        parent_conn.send({
            "op_code": op_code, "op_name": op_name, "args": args,
            "kwargs": kwargs or {}, "expected_shape": expected_shape,
        })
        if parent_conn.poll(timeout):
            return parent_conn.recv()
        return {"ok": False, "kind": "timeout", "detail": "test poll timeout"}
    finally:
        try:
            parent_conn.send({"_cmd": "shutdown"})
        except Exception:
            pass
        p.join(timeout=2)
        if p.is_alive():
            p.terminate()
            p.join(timeout=1)


def test_worker_executes_simple_op():
    op_code = "import numpy as np\ndef lf_double(x):\n    return x * 2"
    from multiprocessing import shared_memory
    arr = np.arange(10, dtype=np.float64)
    shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
    np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)[:] = arr
    try:
        reply = _run_one(op_code=op_code, op_name="lf_double",
                         args={"x": (shm.name, str(arr.dtype), tuple(arr.shape))},
                         expected_shape=(10,))
        assert reply.get("ok") is True, reply
        out_shm = shared_memory.SharedMemory(name=reply["result_shm"])
        try:
            result = np.ndarray(reply["result_shape"], dtype=reply["result_dtype"],
                                buffer=out_shm.buf).copy()
            assert np.array_equal(result, arr * 2)
        finally:
            out_shm.close()
            out_shm.unlink()
    finally:
        shm.close()
        shm.unlink()


def test_worker_returns_signature_mismatch_when_function_missing():
    op_code = "def some_other_name(x):\n    return x"
    reply = _run_one(op_code=op_code, op_name="lf_expected", args={}, expected_shape=None)
    assert reply.get("ok") is False
    assert reply.get("kind") == "signature_mismatch"


def test_worker_returns_exception_on_runtime_error():
    op_code = "def lf_boom(x):\n    raise ValueError('bad input')"
    from multiprocessing import shared_memory
    arr = np.zeros(3)
    shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
    np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)[:] = arr
    try:
        reply = _run_one(op_code=op_code, op_name="lf_boom",
                         args={"x": (shm.name, str(arr.dtype), tuple(arr.shape))})
        assert reply.get("ok") is False
        assert reply.get("kind") == "exception"
        assert "bad input" in reply.get("detail", "")
    finally:
        shm.close()
        shm.unlink()
