"""Verify NextAuth.js v5 JWTs issued by the frontend.

NextAuth.js v5 (session strategy "jwt") signs the session JWT with
HS256 using AUTH_SECRET / NEXTAUTH_SECRET. The backend shares that
secret via env and verifies locally - no DB lookup, no callback to the
frontend.

The `sub` claim carries the user_id (set in the frontend's jwt callback,
spec section 3.6).
"""
from __future__ import annotations

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError


class JwtError(Exception):
    """Raised when a JWT is missing, malformed, expired, or wrongly signed."""


def verify_jwt(token: str, secret: str) -> dict:
    """Verify `token` against `secret` (HS256). Returns the claims dict.

    Raises JwtError on: expired token, bad signature, malformed token, or
    a missing `sub` claim. The raised message never contains the token.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except ExpiredSignatureError as e:
        raise JwtError("token expired") from e
    except JWTError as e:
        raise JwtError(f"invalid token: {type(e).__name__}") from e
    if not payload.get("sub"):
        raise JwtError("token missing 'sub' (user_id) claim")
    return payload
