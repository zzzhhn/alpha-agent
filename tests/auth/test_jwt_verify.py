import time

import pytest
from jose import jwt

from alpha_agent.auth.jwt_verify import JwtError, verify_jwt

_SECRET = "test-secret-not-real-0123456789"


def _make_token(**overrides) -> str:
    now = int(time.time())
    payload = {
        "sub": "42",
        "iat": now,
        "exp": now + 3600,
        "email": "user@example.com",
    }
    payload.update(overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def test_valid_token_returns_payload():
    token = _make_token()
    payload = verify_jwt(token, _SECRET)
    assert payload["sub"] == "42"
    assert payload["email"] == "user@example.com"


def test_expired_token_raises():
    token = _make_token(exp=int(time.time()) - 10)
    with pytest.raises(JwtError, match="expired"):
        verify_jwt(token, _SECRET)


def test_wrong_signature_raises():
    token = _make_token()
    with pytest.raises(JwtError):
        verify_jwt(token, "a-completely-different-secret-value")


def test_missing_sub_raises():
    token = _make_token(sub=None)
    # jose drops None claims; building without sub then verifying must fail.
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600}
    bare = jwt.encode(payload, _SECRET, algorithm="HS256")
    with pytest.raises(JwtError, match="sub"):
        verify_jwt(bare, _SECRET)


def test_malformed_token_raises():
    with pytest.raises(JwtError):
        verify_jwt("not.a.jwt", _SECRET)
