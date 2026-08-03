"""FastAPI auth dependencies for Phase 4 protected routes.

`require_user` is the single gate: it pulls the bearer token, verifies
it with the shared NEXTAUTH_SECRET, and returns the integer user_id.
Any failure -> HTTP 401 with a structured detail (never a bare except,
never the token in the message).
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

from alpha_agent.auth.jwt_verify import JwtError, verify_jwt


async def require_cron(authorization: str | None = Header(default=None)) -> None:
    """Authenticate server-to-server cron calls with one shared bearer secret.

    Vercel Cron sends ``Authorization: Bearer $CRON_SECRET`` automatically.
    GitHub Actions uses the same secret. Missing server configuration fails
    closed so a deployment can never silently make write-capable jobs public.
    """
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="server cron auth not configured (CRON_SECRET missing)",
        )

    expected = f"Bearer {secret}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid cron authorization")


async def require_user(authorization: str | None = Header(default=None)) -> int:
    """Resolve the authenticated user_id from the Authorization header.

    Raises HTTPException(401) if the header is missing, not a Bearer
    token, the JWT fails verification, or the `sub` claim is not an int.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")

    token = authorization[len("Bearer ") :]
    secret = os.environ.get("NEXTAUTH_SECRET")
    if not secret:
        # Config error, not a client error - surface clearly (CLAUDE.md
        # silent-exception rule) but still 401 so the client redirects.
        raise HTTPException(
            status_code=401,
            detail="server auth not configured (NEXTAUTH_SECRET missing)",
        )

    try:
        payload = verify_jwt(token, secret)
    except JwtError as e:
        raise HTTPException(status_code=401, detail=f"auth failed: {e}") from e

    sub = payload["sub"]
    try:
        return int(sub)
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=401, detail="token 'sub' claim is not a valid user_id"
        ) from e
