"""Phase E2: encrypted vault for WorldQuant BRAIN credentials.

BRAIN authenticates with username+password (HTTPBasicAuth), so both secrets are
packed as JSON and sealed with the SAME AES-GCM box + BYOK_MASTER_KEY the LLM
BYOK path uses, stored in `user_byok` under provider='worldquant_brain'. The
plaintext password is never returned to any client — it is only decrypted
server-side to build a BrainClient for a mining run. The user enters it once in
the settings form; it is never handled in plaintext outside this module."""
from __future__ import annotations

import json
import os
from typing import Optional

from alpha_agent.auth.crypto_box import decrypt, encrypt

BRAIN_PROVIDER = "worldquant_brain"
_BRAIN_API_BASE = "https://api.worldquantbrain.com"


def _master() -> bytes:
    m = os.environ.get("BYOK_MASTER_KEY")
    if not m:
        raise RuntimeError("BYOK_MASTER_KEY not configured")
    return m.encode("utf-8")


async def save_brain_credentials(
    pool, user_id: int, username: str, password: str
) -> str:
    """Encrypt {username, password} and upsert into user_byok. Returns the
    username's last-4 for a non-secret status display."""
    payload = json.dumps({"username": username, "password": password})
    ciphertext, nonce = encrypt(payload, _master())
    last4 = username[-4:] if len(username) >= 4 else username
    await pool.execute(
        """
        INSERT INTO user_byok
            (user_id, provider, ciphertext, nonce, last4, base_url, encrypted_at)
        VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (user_id, provider) DO UPDATE SET
            ciphertext = EXCLUDED.ciphertext, nonce = EXCLUDED.nonce,
            last4 = EXCLUDED.last4, encrypted_at = now()
        """,
        user_id, BRAIN_PROVIDER, ciphertext, nonce, last4, _BRAIN_API_BASE,
    )
    return last4


async def load_brain_credentials(
    pool, user_id: int
) -> Optional[tuple[str, str]]:
    """Decrypt (username, password) for the user, or None if not set."""
    row = await pool.fetchrow(
        "SELECT ciphertext, nonce FROM user_byok WHERE user_id=$1 AND provider=$2",
        user_id, BRAIN_PROVIDER,
    )
    if row is None:
        return None
    plaintext = decrypt(row["ciphertext"], row["nonce"], _master())
    data = json.loads(plaintext)
    return data["username"], data["password"]


async def brain_status(pool, user_id: int) -> dict:
    """Non-secret connection status for the settings UI (never the password)."""
    row = await pool.fetchrow(
        "SELECT last4, encrypted_at FROM user_byok WHERE user_id=$1 AND provider=$2",
        user_id, BRAIN_PROVIDER,
    )
    if row is None:
        return {"connected": False}
    return {
        "connected": True,
        "username_last4": row["last4"],
        "saved_at": row["encrypted_at"].isoformat() if row["encrypted_at"] else None,
    }
