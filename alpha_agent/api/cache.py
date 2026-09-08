"""Thread-safe TTL in-memory cache for API responses."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable


def _estimated_bytes(value: Any) -> int:
    """Estimate Python container storage without serializing/copying large payloads."""
    seen: set[int] = set()

    def size(item):
        if id(item) in seen:
            return 0
        seen.add(id(item))
        result = sys.getsizeof(item)
        if isinstance(item, dict):
            result += sum(size(k) + size(v) for k, v in item.items())
        elif isinstance(item, (list, tuple, set, frozenset)):
            result += sum(size(v) for v in item)
        return result

    return size(value)


class TTLCache:
    """Simple dict-backed cache with per-key expiry.

    Thread-safe via a reentrant lock so FastAPI's async workers
    can safely read/write concurrently.
    """

    def __init__(self, default_ttl: float = 300.0, *, max_entries: int = 128,
                 max_bytes: int = 8 * 1024 * 1024) -> None:
        if max_entries < 1 or max_bytes < 1:
            raise ValueError("Cache limits must be positive")
        self._ttl = default_ttl
        self._store: OrderedDict[str, tuple[float, Any, int]] = OrderedDict()
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._bytes = 0
        self._generation = 0
        self._loading: dict[tuple, list] = {}

    def _remove(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry is not None:
            self._bytes -= entry[2]

    def _purge(self) -> None:
        now = time.monotonic()
        for key, entry in list(self._store.items()):
            if now >= entry[0]:
                self._remove(key)

    def get(self, key: str) -> Any | None:
        """Return cached value if fresh, else ``None``."""
        with self._lock:
            self._purge()
            entry = self._store.get(key)
            if entry is None:
                return None
            self._store.move_to_end(key)
            return entry[1]

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store *value* under *key* with optional custom TTL."""
        with self._lock:
            self._purge()
            self._remove(key)
            size = _estimated_bytes(value) + sys.getsizeof(key)
            if size > self._max_bytes:
                return  # Return oversized results to callers without retaining them.
            expires_at = time.monotonic() + (ttl if ttl is not None else self._ttl)
            self._store[key] = (expires_at, value, size)
            self._bytes += size
            while len(self._store) > self._max_entries or self._bytes > self._max_bytes:
                self._remove(next(iter(self._store)))

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[Any]],
                          ttl: float | None = None) -> Any:
        """Coalesce public reads per key/loop; no detached tasks or cached errors.

        Callers must supply a complete PUBLIC cache key, never use this for
        BYOK, private holdings, mutations or user-specific responses.
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        slot = (asyncio.get_running_loop(), key)
        with self._lock:
            if slot not in self._loading and len(self._loading) >= 32:
                entry = None
            else:
                entry = self._loading.setdefault(slot, [asyncio.Lock(), 0])
                entry[1] += 1
        if entry is None:
            return await loader()
        try:
            async with entry[0]:
                cached = self.get(key)
                if cached is not None:
                    return cached
                with self._lock:
                    generation = self._generation
                result = await loader()
                with self._lock:
                    if generation == self._generation:
                        self.set(key, result, ttl)
                return result
        finally:
            with self._lock:
                entry[1] -= 1
                if entry[1] == 0:
                    self._loading.pop(slot, None)

    def invalidate(self, key: str) -> None:
        """Remove a single key."""
        with self._lock:
            self._generation += 1
            self._remove(key)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._generation += 1
            self._store.clear()
            self._bytes = 0
