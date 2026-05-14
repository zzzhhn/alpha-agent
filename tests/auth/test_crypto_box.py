"""Tests for the crypto_box module (AES-256-GCM BYOK encryption)."""
import base64

import pytest

from alpha_agent.auth.crypto_box import CryptoError, decrypt, encrypt

# Fixed 32-byte test master key (base64). NEVER a real key.
_TEST_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef")


def test_encrypt_decrypt_roundtrip():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    assert isinstance(ciphertext, bytes)
    assert isinstance(nonce, bytes)
    assert len(nonce) == 12
    assert ciphertext != b"sk-test-abc123"
    plaintext = decrypt(ciphertext, nonce, _TEST_KEY)
    assert plaintext == "sk-test-abc123"


def test_decrypt_wrong_key_raises():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    wrong = base64.b64encode(b"WRONGWRONGWRONGWRONGWRONGWRONG!!")
    with pytest.raises(CryptoError):
        decrypt(ciphertext, nonce, wrong)


def test_decrypt_tampered_ciphertext_raises():
    ciphertext, nonce = encrypt("sk-test-abc123", _TEST_KEY)
    tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(CryptoError):
        decrypt(tampered, nonce, _TEST_KEY)


def test_nonce_uniqueness_across_encryptions():
    nonces = {encrypt("sk-same", _TEST_KEY)[1] for _ in range(100)}
    assert len(nonces) == 100, "nonces must be unique per encryption"


def test_encrypt_rejects_malformed_master_key():
    with pytest.raises(CryptoError):
        encrypt("sk-test", b"not-base64-and-too-short")
