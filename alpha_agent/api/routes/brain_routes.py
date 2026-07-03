"""Phase E2: WorldQuant BRAIN credential + connection endpoints.

Save the user's encrypted BRAIN login, read its non-secret status, and a
connection test that actually authenticates to BRAIN. The plaintext password is
accepted once on save and never returned. Every route requires the user's own
auth — credentials are strictly per-user."""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.crypto_box import CryptoError
from alpha_agent.auth.dependencies import require_user
from alpha_agent.brain import vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/brain", tags=["brain"])


@router.get("/credentials")
async def get_credentials_status(
    user_id: int = Depends(require_user), pool=Depends(get_db_pool)
) -> dict:
    """Non-secret connection status: connected? username last-4? saved when?"""
    return await vault.brain_status(pool, user_id)


@router.post("/credentials")
async def save_credentials(
    body: dict = Body(default_factory=dict),
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Encrypt + store the user's BRAIN username/password. The password is used
    only here and never returned to any client."""
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "username and password are required")
    try:
        last4 = await vault.save_brain_credentials(pool, user_id, username, password)
    except CryptoError as e:
        # Same class of failure as BYOK save: a misconfigured master key must
        # surface its reason as a 400, not an opaque 500.
        raise HTTPException(
            status_code=400, detail=f"server master key is misconfigured: {e}"
        ) from e
    return {"connected": True, "username_last4": last4}


@router.post("/credentials/test")
async def test_connection(
    user_id: int = Depends(require_user), pool=Depends(get_db_pool)
) -> dict:
    """Authenticate to BRAIN with the saved credentials to confirm they work.
    Returns {ok, error?} — never raises on a BRAIN-side failure so the settings
    UI can show a clean message."""
    from alpha_agent.brain.client import BrainAuthError, BrainClient

    creds = await vault.load_brain_credentials(pool, user_id)
    if creds is None:
        raise HTTPException(400, "no BRAIN credentials saved")
    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        return {"ok": True}
    except BrainAuthError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 — surface any BRAIN/network failure cleanly
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        await client.aclose()


@router.get("/alphas")
async def list_alphas(
    limit: int = 100,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """The user's BRAIN mining results (passed / flagged / rejected / sim_error),
    newest first. Degrades to an empty list if V028 isn't applied yet."""
    from alpha_agent.brain import store

    try:
        alphas = await store.list_brain_alphas(pool, user_id, limit=limit)
    except Exception as e:  # noqa: BLE001 - table may not exist yet
        logger.warning("list_brain_alphas failed (table missing?): %s", e)
        return {"alphas": []}
    return {"alphas": alphas}
