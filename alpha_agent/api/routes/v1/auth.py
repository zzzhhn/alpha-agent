"""v1 Auth endpoints — token generation for API access."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alpha_agent.api.security import create_token, verify_token

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    """Token request body."""

    username: str = Field(description="Username or service identifier")
    role: str = Field(default="viewer", description="Role: admin, viewer, service")


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class TokenVerifyResponse(BaseModel):
    """Token verification response."""

    valid: bool
    sub: str = ""
    role: str = ""


@router.post("/token", response_model=TokenResponse)
async def get_token(req: TokenRequest) -> TokenResponse:
    """Generate a JWT access token.

    In demo mode, any username is accepted.
    In production, this would validate against a user store.
    """
    if not req.username:
        raise HTTPException(status_code=400, detail="Username required")

    token = create_token(sub=req.username, role=req.role)
    return TokenResponse(access_token=token)


@router.get("/verify", response_model=TokenVerifyResponse)
async def verify(token: str) -> TokenVerifyResponse:
    """Verify a JWT token and return its payload."""
    payload = verify_token(token)
    if payload is None:
        return TokenVerifyResponse(valid=False)

    return TokenVerifyResponse(
        valid=True,
        sub=payload.sub,
        role=payload.role,
    )
