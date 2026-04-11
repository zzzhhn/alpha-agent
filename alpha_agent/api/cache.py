"""Thread-safe TTL in-memory cache for API responses."""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    """Simple dict-backed cache with per-key expiry.

    Thread-safe via a reentrant lock so FastAPI's async workers
    can safely read/write concurrently.
    """

    def __init__(self, default_ttl: float = 300.0) -> None:
        self._ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        """Return cached value if fresh, else ``None``."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store *value* under *key* with optional custom TTL."""
        with self._lock:
            expires_at = time.monotonic() + (ttl if ttl is not None else self._ttl)
            self._store[key] = (expires_at, value)

    def invalidate(self, key: str) -> None:
        """Remove a single key."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()
