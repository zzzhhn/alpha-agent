"""Security layer — JWT authentication and rate limiting.

Blueprint p3: OAuth2/JWT authentication, token bucket rate limiting
(1000 requests/minute), audit logging for all state changes.

In demo/interview mode, authentication can be disabled via
ALPHACORE_AUTH_ENABLED=false environment variable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# JWT secret — in production, load from environment
_JWT_SECRET = "alphacore-demo-secret-change-in-prod"
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_SECONDS = 3600  # 1 hour

# Rate limiting
_RATE_LIMIT_REQUESTS = 1000
_RATE_LIMIT_WINDOW_SECONDS = 60

_security = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# JWT helpers (minimal implementation — no PyJWT dependency)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT payload."""

    sub: str  # user/service identifier
    exp: float  # expiry timestamp
    role: str  # "admin" | "viewer" | "service"


def create_token(sub: str, role: str = "viewer") -> str:
    """Create a minimal JWT token (HS256).

    For demo purposes — production should use a proper JWT library.
    """
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}))
    payload_data = {
        "sub": sub,
        "role": role,
        "exp": time.time() + _JWT_EXPIRY_SECONDS,
        "iat": time.time(),
    }
    payload = _b64url_encode(json.dumps(payload_data))
    signature = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{signature}"


def verify_token(token: str) -> TokenPayload | None:
    """Verify and decode a JWT token. Returns None if invalid."""
    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature = parts
    expected_sig = _sign(f"{header_b64}.{payload_b64}")

    if not hmac.compare_digest(signature, expected_sig):
        logger.warning("JWT signature mismatch")
        return None

    try:
        payload_str = _b64url_decode(payload_b64)
        data = json.loads(payload_str)
    except (json.JSONDecodeError, Exception):
        return None

    exp = data.get("exp", 0)
    if time.time() > exp:
        logger.debug("JWT expired")
        return None

    return TokenPayload(
        sub=data.get("sub", ""),
        exp=exp,
        role=data.get("role", "viewer"),
    )


def _b64url_encode(data: str) -> str:
    import base64
    return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()


def _b64url_decode(data: str) -> str:
    import base64
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data).decode()


def _sign(message: str) -> str:
    import base64
    sig = hmac.new(
        _JWT_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


# --------------------------------------------------------------------------- #
# Rate Limiter (token bucket per IP)
# --------------------------------------------------------------------------- #


class RateLimiter:
    """Token bucket rate limiter per client IP.

    Blueprint: 1000 requests per minute per API key.
    """

    def __init__(
        self,
        max_requests: int = _RATE_LIMIT_REQUESTS,
        window_seconds: int = _RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, client_id: str) -> bool:
        """Return True if the request is allowed, False if rate limited."""
        now = time.time()
        cutoff = now - self._window

        # Remove expired entries
        bucket = self._buckets[client_id]
        self._buckets[client_id] = [t for t in bucket if t > cutoff]

        if len(self._buckets[client_id]) >= self._max:
            return False

        self._buckets[client_id].append(now)
        return True

    def remaining(self, client_id: str) -> int:
        """Return remaining requests in current window."""
        now = time.time()
        cutoff = now - self._window
        bucket = self._buckets[client_id]
        active = sum(1 for t in bucket if t > cutoff)
        return max(0, self._max - active)


# --------------------------------------------------------------------------- #
# FastAPI Middleware
# --------------------------------------------------------------------------- #

_rate_limiter = RateLimiter()


class SecurityMiddleware(BaseHTTPMiddleware):
    """Combined auth + rate limiting middleware.

    Skips authentication for:
    - /api/health (health check)
    - /api/v1/auth/* (token endpoints)
    - /static/* (dashboard HTML)
    - When ALPHACORE_AUTH_ENABLED=false

    Always enforces rate limiting.
    """

    _SKIP_AUTH_PATHS = frozenset({
        "/api/health",
        "/api/v1/auth/token",
        "/docs",
        "/openapi.json",
    })

    def __init__(self, app: object, auth_enabled: bool = False) -> None:
        super().__init__(app)
        self._auth_enabled = auth_enabled

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Rate limiting (always active)
        if not _rate_limiter.check(client_ip):
            remaining = _rate_limiter.remaining(client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Retry after {_RATE_LIMIT_WINDOW_SECONDS}s.",
                headers={"X-RateLimit-Remaining": str(remaining)},
            )

        # Authentication (skip for certain paths and static files)
        if self._auth_enabled and not self._should_skip_auth(path):
            token = _extract_token(request)
            if token is None:
                raise HTTPException(
                    status_code=401,
                    detail="Missing or invalid Bearer token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = verify_token(token)
            if payload is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Attach user info to request state
            request.state.user = payload

        # Add rate limit headers
        response = await call_next(request)
        remaining = _rate_limiter.remaining(client_ip)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT_REQUESTS)
        return response

    def _should_skip_auth(self, path: str) -> bool:
        if path in self._SKIP_AUTH_PATHS:
            return True
        if path.startswith("/static/"):
            return True
        return False


def _extract_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None
