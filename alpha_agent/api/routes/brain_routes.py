"""Phase E2: WorldQuant BRAIN credential + connection endpoints.

Save the user's encrypted BRAIN login, read its non-secret status, and a
connection test that actually authenticates to BRAIN. The plaintext password is
accepted once on save and never returned. Every route requires the user's own
auth — credentials are strictly per-user."""
import logging
import os

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.crypto_box import CryptoError
from alpha_agent.auth.dependencies import require_user
from alpha_agent.brain import vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/brain", tags=["brain"])

_GH_REPO = os.environ.get("GH_REPO", "zzzhhn/alpha-agent")
_GH_REF = os.environ.get("GH_REF", "main")
_MINING_WORKFLOW = "brain-mining-loop.yml"


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


@router.post("/mine")
async def trigger_mining(
    body: dict = Body(default_factory=dict),
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Manually kick a mining round without waiting for the daily cron. Dispatches
    the brain-mining-loop GitHub Actions workflow (BRAIN sims poll for minutes —
    can't run inside this request). Results land in brain_alphas in ~30-45min; the
    /brain page's refresh (or auto-poll) picks them up. Requires GH_PAT.

    Returns `started_at` anchored to the DB clock: the progress poller counts rows
    created after it, so anchoring to the same clock that stamps `created_at`
    avoids serverless-vs-Neon skew undercounting early candidates."""
    n = body.get("n_candidates")
    try:
        n = str(max(1, min(int(n), 30))) if n is not None else "12"
    except (TypeError, ValueError):
        n = "12"

    gh_token = os.environ.get("GH_PAT")
    if not gh_token:
        raise HTTPException(500, "GH_PAT not configured; cannot dispatch mining")

    # Anchor BEFORE dispatch so no candidate row can land before the anchor.
    started_at = await pool.fetchval("SELECT now()")

    url = (
        f"https://api.github.com/repos/{_GH_REPO}/actions/"
        f"workflows/{_MINING_WORKFLOW}/dispatches"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json={"ref": _GH_REF, "inputs": {"n_candidates": n}},
                headers={
                    "Authorization": f"Bearer {gh_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
    except Exception as e:  # noqa: BLE001 — surface network failure cleanly
        raise HTTPException(502, f"dispatch failed: {type(e).__name__}") from e
    if resp.status_code != 204:
        raise HTTPException(502, f"GitHub API {resp.status_code}: {resp.text[:150]}")
    return {
        "ok": True,
        "n_candidates": int(n),
        "eta_minutes": 40,
        "started_at": started_at.isoformat(),
    }


@router.get("/mine/status")
async def mining_status(
    since: str | None = None,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Poll target for the manual-mining progress bar. Returns:
      - `mined`: candidates this user has recorded since `since` (every candidate is
        persisted, so this is the real per-candidate progress count);
      - `running`: whether a mining run is queued/in-progress on GitHub Actions (the
        authoritative completion signal — the count alone can't tell "done" from
        "logic-screen pruned below n"). None if GH is unavailable.

    Never raises on a GH/DB hiccup: the UI polls this repeatedly and must degrade
    gracefully (the bar still fills from `mined` even if the GH read fails)."""
    from datetime import datetime

    from alpha_agent.brain import store

    mined = 0
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            mined = await store.count_brain_alphas_since(pool, user_id, since=since_dt)
        except Exception as e:  # noqa: BLE001 — a bad/absent ts must not break the poll
            logger.warning("count_brain_alphas_since failed: %s", e)

    running: bool | None = None
    latest_status: str | None = None
    latest_conclusion: str | None = None
    gh_token = os.environ.get("GH_PAT")
    if gh_token:
        runs_url = (
            f"https://api.github.com/repos/{_GH_REPO}/actions/"
            f"workflows/{_MINING_WORKFLOW}/runs?per_page=5"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    runs_url,
                    headers={
                        "Authorization": f"Bearer {gh_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            if resp.status_code == 200:
                runs = resp.json().get("workflow_runs", [])
                active = {"queued", "in_progress", "requested", "waiting", "pending"}
                running = any((r.get("status") or "") in active for r in runs)
                if runs:
                    latest_status = runs[0].get("status")
                    latest_conclusion = runs[0].get("conclusion")
        except Exception as e:  # noqa: BLE001 — GH hiccup must not break the poll
            logger.warning("GH runs poll failed: %s", e)

    return {
        "running": running,
        "latest_status": latest_status,
        "latest_conclusion": latest_conclusion,
        "mined": mined,
    }


@router.get("/alphas")
async def list_alphas(
    limit: int = 25,
    offset: int = 0,
    outcome: str | None = None,
    q: str | None = None,
    sharpe_min: float | None = None,
    fitness_min: float | None = None,
    turnover_max: float | None = None,
    submitted: bool | None = None,
    sort: str = "created_at",
    descending: bool = True,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """The user's BRAIN mining results, server-side paginated + filtered. Returns
    {alphas, total} (total = rows matching the filters, for page controls).
    Degrades to empty if V028 isn't applied yet."""
    from alpha_agent.brain import store

    try:
        return await store.query_brain_alphas(
            pool, user_id, limit=limit, offset=offset, outcome=outcome, q=q,
            sharpe_min=sharpe_min, fitness_min=fitness_min,
            turnover_max=turnover_max, submitted=submitted,
            sort=sort, descending=descending,
        )
    except Exception as e:  # noqa: BLE001 - table may not exist yet
        logger.warning("query_brain_alphas failed (table missing?): %s", e)
        return {"alphas": [], "total": 0}


@router.get("/alphas/{row_id}/pnl")
async def get_alpha_pnl(
    row_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Live cumulative-PnL curve for a mined alpha, fetched from BRAIN on demand
    (not stored — it's large and only needed when the user opens the detail).
    Returns {points: [{date, pnl}]}. 400 if the row has no BRAIN alpha id."""
    from alpha_agent.brain import store
    from alpha_agent.brain.client import BrainClient
    from alpha_agent.brain.pnl import pnl_to_points

    row = await store.get_brain_alpha(pool, user_id, row_id)
    if row is None:
        raise HTTPException(404, "alpha not found")
    if not row.get("alpha_id"):
        raise HTTPException(400, "this candidate has no BRAIN alpha id (sim failed)")

    creds = await vault.load_brain_credentials(pool, user_id)
    if creds is None:
        raise HTTPException(400, "no BRAIN credentials saved")

    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        raw = await client.get_pnl(row["alpha_id"])
    except Exception as e:  # noqa: BLE001 — surface BRAIN failure as a clean 502
        raise HTTPException(502, f"BRAIN PnL fetch failed: {type(e).__name__}") from e
    finally:
        await client.aclose()

    return {"points": pnl_to_points(raw)}


@router.get("/alphas/{row_id}/yearly")
async def get_alpha_yearly(
    row_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Per-year IS Summary breakdown for a mined alpha (WorldQuant's yearly table:
    sharpe/turnover/fitness/returns/drawdown/margin/long/short per year), fetched
    from BRAIN on demand. Returns {rows: [...]}."""
    from alpha_agent.brain import store
    from alpha_agent.brain.client import BrainClient
    from alpha_agent.brain.pnl import yearly_to_rows

    row = await store.get_brain_alpha(pool, user_id, row_id)
    if row is None:
        raise HTTPException(404, "alpha not found")
    if not row.get("alpha_id"):
        raise HTTPException(400, "this candidate has no BRAIN alpha id (sim failed)")

    creds = await vault.load_brain_credentials(pool, user_id)
    if creds is None:
        raise HTTPException(400, "no BRAIN credentials saved")

    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        raw = await client.get_yearly_stats(row["alpha_id"])
    except Exception as e:  # noqa: BLE001 — surface BRAIN failure cleanly
        raise HTTPException(502, f"BRAIN yearly fetch failed: {type(e).__name__}") from e
    finally:
        await client.aclose()

    return {"rows": yearly_to_rows(raw)}


@router.post("/alphas/{row_id}/submit")
async def submit_alpha(
    row_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Submit a mined alpha to the user's BRAIN account. This is the ONLY
    outward action in the whole BRAIN flow and is strictly user-initiated (one
    click per alpha) — nothing auto-submits. Guards: the row must be the user's,
    carry a BRAIN alpha_id, and be a gate survivor (passed/flagged). Records the
    submit outcome; a 201 from BRAIN means accepted, not yet ACTIVE."""
    from alpha_agent.brain import store
    from alpha_agent.brain.client import BrainClient

    row = await store.get_brain_alpha(pool, user_id, row_id)
    if row is None:
        raise HTTPException(404, "alpha not found")
    if not row.get("alpha_id"):
        raise HTTPException(400, "this candidate has no BRAIN alpha id (sim failed)")
    if row.get("outcome") not in ("passed", "flagged"):
        raise HTTPException(400, "only passed/flagged alphas can be submitted")
    if row.get("submitted_at"):
        raise HTTPException(409, "already submitted")

    creds = await vault.load_brain_credentials(pool, user_id)
    if creds is None:
        raise HTTPException(400, "no BRAIN credentials saved")

    client = BrainClient(creds[0], creds[1])
    try:
        await client.authenticate()
        accepted = await client.submit(row["alpha_id"])
    except Exception as e:  # noqa: BLE001 — surface BRAIN failure as a clean 502
        raise HTTPException(502, f"BRAIN submit failed: {type(e).__name__}: {e}") from e
    finally:
        await client.aclose()

    status = "submitted" if accepted else "submit_rejected"
    await store.mark_submitted(pool, row_id, brain_status=status)
    return {"ok": accepted, "brain_status": status, "alpha_id": row["alpha_id"]}
