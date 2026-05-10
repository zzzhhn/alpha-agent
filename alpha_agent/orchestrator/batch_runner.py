"""Bounded-concurrency runner for ticker iteration.

Cron handlers wrap their per-ticker work in a coroutine and pass a list of
tickers + batch_size; we gather with bounded concurrency so a 500-ticker
slow cron takes ~10min instead of either 500min (serial) or hammering the
yfinance/EDGAR rate limits (unbounded gather).
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


async def run_batched(
    items: list[str],
    fn: Callable[[str], Awaitable[T]],
    *,
    batch_size: int = 20,
) -> dict[str, T | Exception]:
    """Run fn(item) for each item with at most batch_size in flight.

    Per-item exceptions are captured (not raised) so one bad ticker does NOT
    abort the batch. Caller inspects results dict for Exception instances.
    """
    sem = asyncio.Semaphore(batch_size)

    async def _bounded(item: str) -> tuple[str, Any]:
        async with sem:
            try:
                return item, await fn(item)
            except Exception as e:  # noqa: BLE001 — intentional aggregation
                return item, e

    pairs = await asyncio.gather(*[_bounded(t) for t in items])
    return dict(pairs)
