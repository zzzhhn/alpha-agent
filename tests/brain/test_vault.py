"""Phase E2: the encrypted BRAIN credential vault. Both secrets round-trip
through the AES-GCM box + user_byok, the non-secret status never carries the
password, and a re-save upserts in place."""
import base64

import asyncpg
import pytest

from alpha_agent.brain import vault


@pytest.mark.asyncio
async def test_brain_vault_roundtrip_and_status(applied_db, monkeypatch):
    monkeypatch.setenv("BYOK_MASTER_KEY", base64.b64encode(b"k" * 32).decode())
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        await pool.execute(
            "INSERT INTO users (id, email) VALUES (1, 'u@example.com') "
            "ON CONFLICT (id) DO NOTHING"
        )
        # initially nothing stored
        assert await vault.brain_status(pool, 1) == {"connected": False}
        assert await vault.load_brain_credentials(pool, 1) is None

        last4 = await vault.save_brain_credentials(pool, 1, "brainuser1", "s3cret!")
        assert last4 == "ser1"

        st = await vault.brain_status(pool, 1)
        assert st["connected"] is True
        assert st["username_last4"] == "ser1"
        assert st["saved_at"]  # timestamp surfaced, no secret
        assert "password" not in st

        # both secrets decrypt back exactly
        assert await vault.load_brain_credentials(pool, 1) == ("brainuser1", "s3cret!")

        # re-save upserts in place (PK user_id+provider), not a second row
        await vault.save_brain_credentials(pool, 1, "brainuser2", "newpass")
        assert await vault.load_brain_credentials(pool, 1) == ("brainuser2", "newpass")
        assert (await vault.brain_status(pool, 1))["username_last4"] == "ser2"
    finally:
        await pool.close()
