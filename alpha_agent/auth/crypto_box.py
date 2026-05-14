"""AES-256-GCM wrapper for server-side BYOK key encryption.

Single audit point for BYOK_MASTER_KEY. Every encrypt/decrypt of a user
API key funnels through here. The master key and plaintext are NEVER
logged, NEVER put in exception messages.

Storage contract: caller persists (ciphertext, nonce) together; nonce is
12 random bytes per encryption (safe for GCM with random nonces at our
volume). Master key is a base64-encoded 32-byte value from env.
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(Exception):
    """Raised on any encrypt/decrypt failure. Message never contains the
    plaintext, the master key, or the ciphertext bytes."""


def _load_key(master_key_b64: bytes) -> bytes:
    """Decode + validate the base64 master key into 32 raw bytes."""
    try:
        raw = base64.b64decode(master_key_b64, validate=True)
    except (ValueError, TypeError) as e:
        raise CryptoError(f"master key is not valid base64: {type(e).__name__}") from e
    if len(raw) != 32:
        raise CryptoError(
            f"master key must decode to 32 bytes (got {len(raw)})"
        )
    return raw


def encrypt(plaintext: str, master_key_b64: bytes) -> tuple[bytes, bytes]:
    """Encrypt `plaintext` under the master key. Returns (ciphertext, nonce).

    Raises CryptoError on a malformed master key. The 12-byte nonce is
    fresh per call and must be stored alongside the ciphertext.
    """
    key = _load_key(master_key_b64)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes, master_key_b64: bytes) -> str:
    """Decrypt `ciphertext` with `nonce` under the master key.

    Raises CryptoError if the key is wrong, the ciphertext was tampered
    with, or the master key is malformed.
    """
    key = _load_key(master_key_b64)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as e:
        raise CryptoError("decryption failed (wrong key or tampered data)") from e
    return plaintext.decode("utf-8")
