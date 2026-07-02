"""Async client for the WorldQuant BRAIN API.

Wraps the real platform endpoints the self-evolving loop needs: authenticate,
submit a simulation, poll it to completion, read the resulting alpha's in-sample
metrics + PnL, and submit. HTTPBasicAuth is set on the session so every request
carries it (BRAIN auth is per-request; POST /authentication just primes the
session cookie). Pure I/O wrapper — no generation or gating logic — so it mocks
cleanly in tests via an injected httpx client.

API surface distilled from the WorldQuant BRAIN API (see the QuantML-Research
wq-alpha-research SKILL). Base: https://api.worldquantbrain.com.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import httpx

BRAIN_API_BASE = "https://api.worldquantbrain.com"

# In-sample gate thresholds (BRAIN's published bars). A candidate must clear all
# of these before it's worth the SELF_CORRELATION check + surfacing to the user.
MIN_SHARPE = 1.25
MIN_FITNESS = 1.1
MAX_TURNOVER = 0.35
MAX_DRAWDOWN = 0.15

# Default simulation settings (USA TOP3000, delay-1, subindustry-neutral) — the
# highest-pass-rate config. Callers override per-signal (e.g. decay for turnover).
DEFAULT_SETTINGS: dict[str, Any] = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
}


class BrainError(Exception):
    """Base for BRAIN API failures."""


class BrainAuthError(BrainError):
    """Authentication rejected (bad credentials / not authorized)."""


class BrainSimulationError(BrainError):
    """A simulation failed or timed out."""


@dataclass(frozen=True)
class AlphaMetrics:
    """In-sample metrics from GET /alphas/{id} (the `is` block)."""

    alpha_id: str
    sharpe: Optional[float]
    fitness: Optional[float]
    turnover: Optional[float]
    returns: Optional[float]
    drawdown: Optional[float]

    def passes_gates(
        self,
        *,
        min_sharpe: float = MIN_SHARPE,
        min_fitness: float = MIN_FITNESS,
        max_turnover: float = MAX_TURNOVER,
        max_drawdown: float = MAX_DRAWDOWN,
    ) -> bool:
        """True only if every in-sample gate is present and cleared. A missing
        metric fails closed (never surface an alpha we couldn't fully vet)."""
        if None in (self.sharpe, self.fitness, self.turnover):
            return False
        if self.sharpe < min_sharpe or self.fitness < min_fitness:
            return False
        if self.turnover > max_turnover:
            return False
        if self.drawdown is not None and self.drawdown > max_drawdown:
            return False
        return True


def _metrics_from_alpha(alpha_id: str, alpha: dict) -> AlphaMetrics:
    is_block = alpha.get("is") or {}
    return AlphaMetrics(
        alpha_id=alpha_id,
        sharpe=is_block.get("sharpe"),
        fitness=is_block.get("fitness"),
        turnover=is_block.get("turnover"),
        returns=is_block.get("returns"),
        drawdown=is_block.get("drawdown"),
    )


class BrainClient:
    """Async WorldQuant BRAIN client. One instance per mining run (the session
    cookie is reused across all calls). Always `await aclose()` when done."""

    def __init__(
        self,
        username: str,
        password: str,
        *,
        base_url: str = BRAIN_API_BASE,
        timeout_s: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        # Injected client (tests) keeps its own auth; otherwise set BasicAuth on
        # the session so every request carries it.
        self._client = client or httpx.AsyncClient(
            base_url=self._base,
            auth=httpx.BasicAuth(username, password),
            timeout=timeout_s,
        )

    async def authenticate(self) -> None:
        """Prime the session. 201 = authorized; anything else is an auth error."""
        resp = await self._client.post("/authentication")
        if resp.status_code != 201:
            raise BrainAuthError(
                f"BRAIN authentication failed: HTTP {resp.status_code}"
            )

    async def simulate(
        self, expression: str, settings: Optional[dict] = None
    ) -> str:
        """POST /simulations. Returns the sim_id parsed from the Location header."""
        payload = {
            "type": "REGULAR",
            "settings": settings or DEFAULT_SETTINGS,
            "regular": expression,
        }
        resp = await self._client.post("/simulations", json=payload)
        if resp.status_code not in (200, 201):
            raise BrainSimulationError(
                f"simulate rejected: HTTP {resp.status_code}: {resp.text[:200]}"
            )
        location = resp.headers.get("Location", "")
        sim_id = location.rstrip("/").split("/")[-1]
        if not sim_id:
            raise BrainSimulationError("simulate returned no Location/sim_id")
        return sim_id

    async def poll_simulation(
        self, sim_id: str, *, interval_s: float = 8.0, max_wait_s: float = 600.0
    ) -> dict:
        """Poll GET /simulations/{id} until COMPLETE (returns the sim dict, which
        carries the resulting `alpha` id). Raises on a failed or timed-out sim."""
        waited = 0.0
        while True:
            resp = await self._client.get(f"/simulations/{sim_id}")
            resp.raise_for_status()
            data = resp.json()
            status = (data.get("status") or "").upper()
            if status in ("COMPLETE", "COMPLETED"):
                return data
            if status in ("FAILED", "ERROR", "SIMULATION_ERROR"):
                raise BrainSimulationError(
                    f"simulation {sim_id} failed: {data.get('message', status)}"
                )
            if waited >= max_wait_s:
                raise BrainSimulationError(
                    f"simulation {sim_id} timed out after {max_wait_s}s "
                    f"(last status {status or 'UNKNOWN'})"
                )
            await asyncio.sleep(interval_s)
            waited += interval_s

    async def get_alpha_metrics(self, alpha_id: str) -> AlphaMetrics:
        """GET /alphas/{id} → in-sample metrics."""
        resp = await self._client.get(f"/alphas/{alpha_id}")
        resp.raise_for_status()
        return _metrics_from_alpha(alpha_id, resp.json())

    async def get_pnl(self, alpha_id: str) -> dict:
        """GET /alphas/{id}/recordsets/pnl → cumulative-PnL recordset. The caller
        differences it into DAILY returns for the SELF_CORRELATION check (raw
        cumulative PnL inflates every correlation > 0.9)."""
        resp = await self._client.get(f"/alphas/{alpha_id}/recordsets/pnl")
        resp.raise_for_status()
        return resp.json()

    async def list_active_alphas(self) -> list[dict]:
        """GET /users/self/alphas → the user's alphas; filter to ACTIVE (the set
        a new candidate must not correlate with)."""
        resp = await self._client.get("/users/self/alphas")
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [a for a in results if (a.get("status") or "").upper() == "ACTIVE"]

    async def submit(self, alpha_id: str) -> bool:
        """POST /alphas/{id}/submit. Returns True on 201 (accepted). NOTE: 201 is
        NOT the same as going ACTIVE — the caller re-reads status to confirm.
        Only called from a user-approved action, never automatically."""
        resp = await self._client.post(f"/alphas/{alpha_id}/submit")
        return resp.status_code in (200, 201)

    async def aclose(self) -> None:
        await self._client.aclose()
