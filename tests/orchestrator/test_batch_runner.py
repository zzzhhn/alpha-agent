import asyncio
import pytest

from alpha_agent.orchestrator.batch_runner import run_batched

pytestmark = pytest.mark.asyncio


async def test_run_batched_returns_all_results():
    async def square(t):
        await asyncio.sleep(0.001)
        return int(t) ** 2

    results = await run_batched(["1", "2", "3", "4", "5"], square, batch_size=2)
    assert sorted(results.values()) == [1, 4, 9, 16, 25]
    assert set(results.keys()) == {"1", "2", "3", "4", "5"}


async def test_run_batched_isolates_per_ticker_failure():
    async def maybe_fail(t):
        if t == "BAD":
            raise RuntimeError("oops")
        return f"ok:{t}"

    results = await run_batched(["A", "BAD", "C"], maybe_fail, batch_size=2)
    assert results["A"] == "ok:A"
    assert results["C"] == "ok:C"
    assert isinstance(results["BAD"], Exception)
    assert "oops" in str(results["BAD"])


async def test_run_batched_respects_concurrency_cap():
    """At most batch_size coroutines should be live at once."""
    in_flight = 0
    peak = 0

    async def track(t):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        return t

    await run_batched([str(i) for i in range(20)], track, batch_size=4)
    assert peak <= 4
