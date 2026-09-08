"""Request-local timings. No SQL, query strings, bodies or identities are recorded."""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi.responses import JSONResponse
from alpha_agent.storage.postgres import DBUnavailable

logger = logging.getLogger(__name__)


@dataclass
class DBTiming:
    wait_ms: float = 0
    query_ms: float = 0
    operations: int = 0


db_timing: ContextVar[DBTiming | None] = ContextVar("db_timing", default=None)


def install_performance(app):
    """Shared by local factory and the independent Vercel entry point."""
    app.add_middleware(PerformanceMiddleware)

    @app.exception_handler(DBUnavailable)
    async def database_busy(_request, _exc):
        return JSONResponse(
            status_code=503, content={"detail": "DB_UNAVAILABLE"},
            headers={"Retry-After": "2", "Cache-Control": "no-store"},
        )


class PerformanceMiddleware:
    """Pure ASGI: keeps streaming responses intact and measures time to headers.

    DB times are sums across instrumented operations, not wall time; parallel
    reads may therefore exceed app duration. Queries on manually held transaction
    connections are not counted. This is request timing, not SQL profiling.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        timing = DBTiming()
        token = db_timing.set(timing)
        start = time.monotonic()

        async def timed_send(message):
            if message["type"] == "http.response.start":
                elapsed = (time.monotonic() - start) * 1000
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"server-timing", (
                        f"app;dur={elapsed:.1f}, db_wait;dur={timing.wait_ms:.1f}, "
                        f"db_query;dur={timing.query_ms:.1f}"
                    ).encode("ascii")),
                ]
                if elapsed >= 1000 or message["status"] >= 500:
                    route = getattr(scope.get("route"), "path", "unmatched")
                    logger.warning(
                        "api_timing route=%s method=%s status=%s app_ms=%.1f "
                        "db_wait_ms=%.1f db_query_ms=%.1f db_ops=%d",
                        route, scope["method"], message["status"], elapsed,
                        timing.wait_ms, timing.query_ms, timing.operations,
                    )
            await send(message)

        try:
            await self.app(scope, receive, timed_send)
        finally:
            db_timing.reset(token)
