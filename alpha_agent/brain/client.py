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
    margin: Optional[float] = None
    # BRAIN's own performance tier for the alpha (top-level `grade` on the alpha
    # object): SPECTACULAR / EXCELLENT / GOOD / AVERAGE / INFERIOR / POOR. Stored
    # + surfaced as-is; the exact enum is BRAIN's, so we never invent one.
    grade: Optional[str] = None
    # BRAIN's own in-sample check verdicts, keyed by check name (e.g.
    # LOW_SHARPE, LOW_FITNESS, HIGH_TURNOVER, SELF_CORRELATION). Each value is
    # {"result": "PASS"|"FAIL"|"PENDING", "value": float|None, "limit": ...}.
    # This is BRAIN's authoritative gate result (what actually blocks submit),
    # not our local threshold comparison.
    checks: dict[str, dict] = None  # type: ignore[assignment]

    def brain_self_correlation(self) -> Optional[float]:
        """BRAIN's computed max self-correlation from the SELF_CORRELATION check,
        or None if BRAIN hasn't computed it yet (PENDING / absent)."""
        chk = (self.checks or {}).get("SELF_CORRELATION") or {}
        v = chk.get("value")
        return float(v) if isinstance(v, (int, float)) else None

    def brain_checks_verdict(
        self, *, exclude: tuple[str, ...] = ("SELF_CORRELATION",)
    ) -> Optional[bool]:
        """True/False if BRAIN reports a definitive PASS/FAIL across its in-sample
        checks; None if any is still PENDING (or there are no checks yet).
        SELF_CORRELATION is excluded by default — the miner treats correlation as
        a separate axis (flagged bucket), so this reflects the alpha's own merit
        (Sharpe/Fitness/Turnover/etc.)."""
        checks = {k: v for k, v in (self.checks or {}).items() if k not in exclude}
        if not checks:
            return None
        results = [c.get("result") for c in checks.values()]
        if any(r in (None, "PENDING") for r in results):
            return None
        return all(r == "PASS" for r in results)

    def passes_gates(
        self,
        *,
        min_sharpe: float = MIN_SHARPE,
        min_fitness: float = MIN_FITNESS,
        max_turnover: float = MAX_TURNOVER,
        max_drawdown: float = MAX_DRAWDOWN,
    ) -> bool:
        """True only if every in-sample gate is present and cleared. Prefers
        BRAIN's own check verdict when available (authoritative); otherwise
        falls back to comparing the raw metrics against our thresholds. A
        missing metric fails closed (never surface an alpha we couldn't vet)."""
        verdict = self.brain_checks_verdict()
        if verdict is not None:
            return verdict
        if None in (self.sharpe, self.fitness, self.turnover):
            return False
        if self.sharpe < min_sharpe or self.fitness < min_fitness:
            return False
        if self.turnover > max_turnover:
            return False
        if self.drawdown is not None and self.drawdown > max_drawdown:
            return False
        return True


def _max_self_corr(body: dict) -> Optional[float]:
    """Extract the max self-correlation from a /correlations/self response.

    Uses the unambiguous top-level numeric `max` (what BRAIN reports as the
    largest correlation against the user's other alphas). We deliberately do NOT
    scan `records`: those are histogram buckets [low, high, count], and a count
    of 1 is indistinguishable from a correlation of 1.0 — guessing there could
    fabricate a false 'redundant' flag. None → caller falls back to the local
    approximation rather than trust a mis-parse."""
    if not isinstance(body, dict):
        return None
    top = body.get("max")
    return float(top) if isinstance(top, (int, float)) else None


def _parse_checks(is_block: dict) -> dict[str, dict]:
    """Index the `is.checks` array by check name. Each check is
    {"name": ..., "result": "PASS"/"FAIL"/"PENDING", "value": ..., "limit": ...}."""
    out: dict[str, dict] = {}
    for chk in is_block.get("checks") or []:
        name = chk.get("name")
        if name:
            out[name] = chk
    return out


def _metrics_from_alpha(alpha_id: str, alpha: dict) -> AlphaMetrics:
    is_block = alpha.get("is") or {}
    return AlphaMetrics(
        alpha_id=alpha_id,
        sharpe=is_block.get("sharpe"),
        fitness=is_block.get("fitness"),
        turnover=is_block.get("turnover"),
        returns=is_block.get("returns"),
        drawdown=is_block.get("drawdown"),
        margin=is_block.get("margin"),
        grade=alpha.get("grade"),  # top-level performance tier, not in `is`
        checks=_parse_checks(is_block),
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
            # A produced `alpha` id is the definitive terminal signal — present
            # whenever the sim finished, regardless of the status label. BRAIN's
            # WARNING is a TERMINAL state (completed with warnings, e.g. low
            # universe coverage) that still yields an alpha; treating it as
            # "still running" was making every WARNING sim poll to the 600s
            # timeout even though it had already finished.
            if data.get("alpha") or status in ("COMPLETE", "COMPLETED", "WARNING"):
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

    async def get_self_correlation(
        self, alpha_id: str, *, interval_s: float = 5.0, max_wait_s: float = 120.0
    ) -> Optional[float]:
        """GET /alphas/{id}/correlations/self → BRAIN's OWN max self-correlation
        of this alpha against the user's other alphas (the value that actually
        gates submission). Computed lazily server-side: BRAIN answers 202 (often
        with Retry-After) while computing, then 200 with the data. Returns the
        max correlation, or None if it can't be obtained (best-effort — never
        raises into the mining loop).

        Response shape varies; we read a top-level numeric `max`, else scan
        `records` for the largest numeric cell. This is the authoritative signal:
        when seeding from the user's own alphas, offspring that are near-
        duplicates score high here exactly as BRAIN would reject them."""
        waited = 0.0
        while True:
            try:
                resp = await self._client.get(f"/alphas/{alpha_id}/correlations/self")
            except Exception:  # noqa: BLE001 — best-effort
                return None
            if resp.status_code == 202:
                if waited >= max_wait_s:
                    return None
                retry = resp.headers.get("Retry-After")
                delay = float(retry) if retry and retry.isdigit() else interval_s
                await asyncio.sleep(delay)
                waited += delay
                continue
            if resp.status_code != 200:
                return None
            try:
                return _max_self_corr(resp.json())
            except Exception:  # noqa: BLE001 — unparseable body → no signal
                return None

    async def get_pnl(
        self, alpha_id: str, *, interval_s: float = 2.0, max_wait_s: float = 30.0
    ) -> dict:
        """GET /alphas/{id}/recordsets/pnl → cumulative-PnL recordset.

        Like the correlation endpoint, BRAIN computes this recordset LAZILY: the
        first request often returns 202 (still computing), sometimes with an
        EMPTY body — calling .json() on that throws JSONDecodeError (surfaced as
        a spurious 502 that 'worked on retry'). So poll: honour 202/Retry-After
        and empty bodies until a 200 with a JSON body arrives (or the budget is
        spent). The caller differences the result into DAILY returns for the
        SELF_CORRELATION check (raw cumulative PnL inflates every corr > 0.9)."""
        waited = 0.0
        while True:
            resp = await self._client.get(f"/alphas/{alpha_id}/recordsets/pnl")
            body = (resp.text or "").strip()
            if resp.status_code == 200 and body:
                return resp.json()
            # 202 (computing) or a 200 with an empty/not-yet-ready body → wait.
            if resp.status_code in (200, 202) and waited < max_wait_s:
                retry = resp.headers.get("Retry-After")
                delay = float(retry) if retry and retry.isdigit() else interval_s
                await asyncio.sleep(delay)
                waited += delay
                continue
            resp.raise_for_status()  # a real error status → raise
            # 200 but still empty after the budget — return an empty recordset so
            # the caller shows "no PnL" rather than crashing.
            return {"records": []}

    async def get_yearly_stats(
        self, alpha_id: str, *, interval_s: float = 2.0, max_wait_s: float = 30.0
    ) -> dict:
        """GET /alphas/{id}/recordsets/yearly-stats → the per-year IS breakdown
        (the WorldQuant 'IS Summary' table: sharpe/turnover/fitness/returns/
        drawdown/margin/long-count/short-count per year). Same lazy-compute
        polling as get_pnl. Returns the raw recordset ({schema, records})."""
        waited = 0.0
        while True:
            resp = await self._client.get(
                f"/alphas/{alpha_id}/recordsets/yearly-stats"
            )
            body = (resp.text or "").strip()
            if resp.status_code == 200 and body:
                return resp.json()
            if resp.status_code in (200, 202) and waited < max_wait_s:
                retry = resp.headers.get("Retry-After")
                delay = float(retry) if retry and retry.isdigit() else interval_s
                await asyncio.sleep(delay)
                waited += delay
                continue
            resp.raise_for_status()
            return {"schema": {}, "records": []}

    async def list_active_alphas(self) -> list[dict]:
        """GET /users/self/alphas → the user's alphas; filter to ACTIVE (the set
        a new candidate must not correlate with)."""
        resp = await self._client.get("/users/self/alphas")
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [a for a in results if (a.get("status") or "").upper() == "ACTIVE"]

    # High-value BRAIN datasets to draw fields from. Spans fundamentals, analyst
    # expectations, AND alternative data (news, options) — the last two are where
    # 'spectacular' alphas usually come from (few users mine them). Without a
    # dataset filter /data-fields returns only a small default set, so we query
    # each dataset explicitly and combine.
    _DEFAULT_DATASETS = (
        "fundamental6", "fundamental2", "analyst4", "news12", "news18",
        "option8", "option9", "pv1", "pv13", "socialmedia12", "model16",
    )

    async def fetch_data_fields(
        self,
        *,
        region: str = "USA",
        universe: str = "TOP3000",
        delay: int = 1,
        field_type: str = "MATRIX",
        per_dataset: int = 100,
        page_size: int = 50,
        datasets: Optional[tuple[str, ...]] = None,
        min_coverage: float = 0.35,
        limit: Optional[int] = None,
    ) -> list[str]:
        """GET /data-fields per dataset → the field IDs usable in FASTEXPR for
        this region/universe/delay, across fundamentals + analyst + alternative
        data. Returns field `id` strings (deduped, capped at `limit` if given).
        Best-effort per page/dataset.

        MATRIX = a per-(date,instrument) numeric value usable as an operand.
        min_coverage skips ultra-sparse fields that mostly NaN out. The endpoint
        rate-limits hard (429) — retried with backoff, since a swallowed 429 is
        exactly what left this returning nothing before."""
        import asyncio

        datasets = datasets or self._DEFAULT_DATASETS
        seen: set[str] = set()
        out: list[str] = []
        for ds in datasets:
            offset = 0
            got = 0
            while got < per_dataset:
                resp = None
                for attempt in range(4):
                    try:
                        resp = await self._client.get(
                            "/data-fields",
                            params={
                                "instrumentType": "EQUITY", "region": region,
                                "universe": universe, "delay": delay,
                                "type": field_type, "dataset.id": ds,
                                "limit": page_size, "offset": offset,
                            },
                        )
                    except Exception:  # noqa: BLE001 — best-effort per dataset
                        resp = None
                        break
                    if resp.status_code != 429:
                        break
                    await asyncio.sleep(1.5 * (attempt + 1))
                if resp is None or resp.status_code != 200:
                    break
                results = resp.json().get("results", [])
                if not results:
                    break
                for f in results:
                    fid = f.get("id")
                    try:
                        cov = float(f.get("coverage", 0) or 0)
                    except (TypeError, ValueError):
                        cov = 0.0
                    if isinstance(fid, str) and fid.strip() and fid not in seen and cov >= min_coverage:
                        seen.add(fid.strip())
                        out.append(fid.strip())
                        got += 1
                offset += page_size
        return out[:limit] if limit else out

    async def fetch_alpha_expressions(
        self, *, limit: int = 200, page_size: int = 50
    ) -> list[str]:
        """The FASTEXPR code of the user's REGULAR alphas (across all statuses),
        for use as GA seeds — the 'golden templates' the miner breeds from. The
        expression lives at alpha['regular']['code']. Paginated via limit/offset
        (the user may have dozens); stops at `limit` total or the last page.
        Best-effort: a page failure just ends collection with what we have."""
        out: list[str] = []
        offset = 0
        while len(out) < limit:
            try:
                resp = await self._client.get(
                    "/users/self/alphas",
                    params={"limit": page_size, "offset": offset},
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except Exception:  # noqa: BLE001 — best-effort seed collection
                break
            if not results:
                break
            for a in results:
                code = (a.get("regular") or {}).get("code")
                if isinstance(code, str) and code.strip():
                    out.append(code.strip())
            offset += page_size
        return out[:limit]

    async def submit(self, alpha_id: str) -> bool:
        """POST /alphas/{id}/submit. Returns True on 201 (accepted). NOTE: 201 is
        NOT the same as going ACTIVE — the caller re-reads status to confirm.
        Only called from a user-approved action, never automatically."""
        resp = await self._client.post(f"/alphas/{alpha_id}/submit")
        return resp.status_code in (200, 201)

    async def aclose(self) -> None:
        await self._client.aclose()
