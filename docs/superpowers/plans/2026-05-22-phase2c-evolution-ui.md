# Phase 2c: Evolution Self-Analysis UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the self-loop a face: a read-only `/evolution` dashboard that surfaces what the engine already produces, so a user can see per-signal IC trends over time, how well-calibrated the confidence is (reliability curve + Brier), what the adaptive-weight layer changed (live vs shadow weights, promotion streak), and the change/rollback history, without any new analysis logic.

**Architecture:** A new backend router `alpha_agent/api/routes/evolution.py` exposes four read-only endpoints over data already written by Phases 1a/1b/1c (`signal_ic_history`, `signal_weight_current`, `confidence_calibration`, `config_change_log`). A new frontend route `/evolution` renders four panels (recharts line for IC trend, reliability curve, a live-vs-shadow weight table, a change/rollback history table). No writes, no proposer (the methodology proposer + approve/reject controls arrive with Phase 2a/2b; the panel leaves an explicit placeholder for them).

**Tech Stack:** FastAPI + asyncpg (backend, pytest + pytest-postgresql `applied_db`), Next.js 14 App Router + recharts + the `lib/api.ts` client (frontend, verified via `tsc --noEmit` + `next lint` + build + manual browser check; the repo has no frontend unit-test runner).

**Scope note:** This is Phase 2c only. The DB-backed engine config (2-pre), the methodology proposer (2a), and the approval queue (2b) are separate later plans. The Evolution panel is read-only and has NO dependency on them; it includes a clearly-labeled empty "Pending proposals" section that 2b will fill.

---

## Existing data this surfaces (all already populated in prod)

- `signal_ic_history(signal_name, window_days, ic, n_observations, computed_at)`, written daily by `run_monthly_ic_backtest` (Phase 1a). Time series of IC per signal per window.
- `signal_weight_current(signal_name, status, weight, reason, consecutive_bad_windows, shadow_streak, last_updated)`, live + shadow rows per signal (Phase 1b).
- `confidence_calibration(as_of, isotonic_map, buckets, n_pairs, applied)`, daily reliability/Brier diagnostics (Phase 1c). `buckets` = `[{lo, hi, hit_rate, brier, n}, ...]`.
- `config_change_log(id, user_id, field, old_value, new_value, changed_at, source, rollback_of)`, weight promotions/rollbacks journaled by Phase 1b (`source` in `auto_promote`/`cold_start_seed`/`auto_rollback`, `field='signal_weights'`).

Reference: `alpha_agent/api/routes/health.py` already aggregates `signal_ic_history` into icir/ir (`/api/_health/signals`), mirror its asyncpg + Pydantic style. Frontend recharts usage: `frontend/src/app/(dashboard)/report/page.tsx` and `factors/page.tsx`. API client: `frontend/src/lib/api.ts`.

---

## File Structure

- `alpha_agent/api/routes/evolution.py` (new): router `prefix="/api/evolution"`, four GET endpoints.
- `alpha_agent/api/app.py` (modify): register the evolution router.
- `tests/api/test_evolution.py` (new): endpoint shape + content tests against `applied_db`.
- `frontend/src/lib/api.ts` (modify): four fetch helpers + types (or `frontend/src/lib/types.ts` if types live there).
- `frontend/src/app/(dashboard)/evolution/page.tsx` (new): the page (server component shell).
- `frontend/src/components/evolution/IcTrendChart.tsx`, `ReliabilityChart.tsx`, `WeightDeltaTable.tsx`, `ChangeHistoryTable.tsx` (new): the four panels.
- `frontend/src/components/layout/Sidebar.tsx` (modify): add the `/evolution` nav entry.
- `frontend/src/lib/i18n.ts` (modify): `evolution.*` keys (zh/en).

---

### Task 1: Backend evolution router (4 read endpoints)

**Files:**
- Create: `alpha_agent/api/routes/evolution.py`
- Test: `tests/api/test_evolution.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_evolution.py
import json
from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool):
    now = datetime.now(UTC)
    # IC history: 2 days x 1 signal x 1 window
    for d, ic in ((2, 0.05), (1, 0.08)):
        await pool.execute(
            "INSERT INTO signal_ic_history (signal_name, window_days, ic, n_observations, computed_at) "
            "VALUES ('news', 30, $1, 40, $2) ON CONFLICT DO NOTHING",
            ic, now - timedelta(days=d),
        )
    # Live + shadow weight rows
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason, shadow_streak) "
        "VALUES ('news','live',0.10,now(),'ic_above_threshold',0) "
        "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason, shadow_streak) "
        "VALUES ('news','shadow',0.12,now(),'shadow_candidate',3) "
        "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight, shadow_streak=EXCLUDED.shadow_streak"
    )
    # Calibration row
    await pool.execute(
        "INSERT INTO confidence_calibration (as_of, isotonic_map, buckets, n_pairs, applied) "
        "VALUES (now(), $1::jsonb, $2::jsonb, 73, true)",
        json.dumps({"x": [0.4, 0.6], "y": [0.3, 0.5]}),
        json.dumps([{"lo": 0.4, "hi": 0.5, "hit_rate": 0.35, "brier": 0.12, "n": 40}]),
    )
    # Change log: a promotion + a rollback
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0, 'signal_weights', '{}', '{\"baseline_ic\": 0.1}', 'auto_promote')"
    )


@pytest.mark.asyncio
async def test_ic_trend_returns_series(applied_db, pool):
    from httpx import ASGITransport, AsyncClient

    from alpha_agent.api.app import create_app
    await _seed(pool)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        r = await ac.get("/api/evolution/ic_trend?window_days=30")
        assert r.status_code == 200
        body = r.json()
        news = [s for s in body["series"] if s["signal_name"] == "news"]
        assert news and len(news[0]["points"]) >= 2
        assert {"computed_at", "ic"} <= set(news[0]["points"][0])


@pytest.mark.asyncio
async def test_weights_calibration_changes_endpoints(applied_db, pool):
    from httpx import ASGITransport, AsyncClient

    from alpha_agent.api.app import create_app
    await _seed(pool)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        w = (await ac.get("/api/evolution/weights")).json()
        news = {row["status"]: row for row in w["weights"] if row["signal_name"] == "news"}
        assert news["live"]["weight"] == pytest.approx(0.10)
        assert news["shadow"]["weight"] == pytest.approx(0.12)
        assert news["shadow"]["shadow_streak"] == 3

        cal = (await ac.get("/api/evolution/calibration")).json()
        assert cal["applied"] is True and cal["n_pairs"] == 73
        assert cal["buckets"][0]["brier"] == pytest.approx(0.12)

        ch = (await ac.get("/api/evolution/changes?limit=10")).json()
        assert any(c["source"] == "auto_promote" for c in ch["changes"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_evolution.py -v`
Expected: FAIL (404s, the routes do not exist). If `create_app`/httpx fixtures differ from the repo's existing API tests, FIRST read an existing `tests/api/test_*.py` (e.g. `test_stock.py` uses `client_with_db`) and MATCH that app/client fixture pattern instead of constructing the client inline. Use whatever the repo's API tests already use.

- [ ] **Step 3: Write `alpha_agent/api/routes/evolution.py`**

```python
"""Read-only Evolution self-analysis endpoints.

Surfaces data already produced by the self-loop (Phases 1a/1b/1c) for the
/evolution dashboard. No writes, no analysis logic. Mirrors the asyncpg +
Pydantic style of health.py.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


@router.get("/ic_trend")
async def ic_trend(window_days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    """Per-signal IC time series for one backtest window over the trailing
    `window_days` of computed_at stamps (for the trend chart)."""
    pool = await get_db_pool()
    since = datetime.now(UTC) - timedelta(days=window_days)
    rows = await pool.fetch(
        "SELECT signal_name, computed_at, ic, n_observations "
        "FROM signal_ic_history WHERE window_days = $1 AND computed_at >= $2 "
        "ORDER BY signal_name, computed_at",
        window_days, since,
    )
    series: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        series.setdefault(r["signal_name"], []).append({
            "computed_at": r["computed_at"].isoformat(),
            "ic": float(r["ic"]),
            "n": int(r["n_observations"]),
        })
    return {"window_days": window_days,
            "series": [{"signal_name": k, "points": v} for k, v in series.items()]}


@router.get("/weights")
async def weights() -> dict[str, Any]:
    """Current live + shadow weights per signal with shadow streak + reason."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT signal_name, status, weight, reason, consecutive_bad_windows, "
        "shadow_streak, last_updated FROM signal_weight_current "
        "ORDER BY signal_name, status"
    )
    return {"weights": [{
        "signal_name": r["signal_name"], "status": r["status"],
        "weight": float(r["weight"]), "reason": r["reason"],
        "consecutive_bad_windows": r["consecutive_bad_windows"],
        "shadow_streak": r["shadow_streak"],
        "last_updated": r["last_updated"].isoformat() if r["last_updated"] else None,
    } for r in rows]}


@router.get("/calibration")
async def calibration() -> dict[str, Any]:
    """Latest confidence calibration row (reliability buckets + Brier)."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT as_of, isotonic_map, buckets, n_pairs, applied "
        "FROM confidence_calibration ORDER BY as_of DESC LIMIT 1"
    )
    if row is None:
        return {"as_of": None, "n_pairs": 0, "applied": False, "buckets": []}
    return {
        "as_of": row["as_of"].isoformat(),
        "n_pairs": row["n_pairs"], "applied": row["applied"],
        "isotonic_map": json.loads(row["isotonic_map"]),
        "buckets": json.loads(row["buckets"]),
    }


@router.get("/changes")
async def changes(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Recent signal-weight change/rollback journal (Phase 1b auto tier)."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, field, old_value, new_value, changed_at, source, rollback_of "
        "FROM config_change_log WHERE field = 'signal_weights' "
        "ORDER BY changed_at DESC LIMIT $1",
        limit,
    )
    return {"changes": [{
        "id": r["id"], "source": r["source"],
        "changed_at": r["changed_at"].isoformat(),
        "rollback_of": r["rollback_of"],
        "new_value": r["new_value"],
    } for r in rows]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_evolution.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/evolution.py tests/api/test_evolution.py
git commit -m "feat(evolution): read-only API for IC trend, weights, calibration, changes"
```

---

### Task 2: Register the router

**Files:**
- Modify: `alpha_agent/api/app.py`

- [ ] **Step 1: Read how routers are registered**

Read `alpha_agent/api/app.py` and find the router-registration block (the `_load(...)` / `include_router` pattern used for `cron_routes`, `health`, etc.). Match it exactly.

- [ ] **Step 2: Register evolution the same way**

Add an evolution import + load mirroring the existing pattern, e.g.:

```python
    def _import_evolution_routes():
        from alpha_agent.api.routes.evolution import router
        return router
    _load("evolution", _import_evolution_routes)
```

(Use whatever the file's actual registration helper signature is, match the neighbors.)

- [ ] **Step 3: Verify the routes register**

Run: `uv run python -c "from alpha_agent.api.app import create_app; app=create_app(); ps=[r.path for r in app.routes]; assert '/api/evolution/ic_trend' in ps and '/api/evolution/weights' in ps, ps; print('routes OK')"`
Expected: `routes OK`.

- [ ] **Step 4: Commit**

```bash
git add alpha_agent/api/app.py
git commit -m "feat(evolution): register evolution router"
```

---

### Task 3: Frontend API client + types

**Files:**
- Modify: `frontend/src/lib/api.ts` (+ `frontend/src/lib/types.ts` if the repo keeps types separate)

- [ ] **Step 1: Read the existing client conventions**

Read `frontend/src/lib/api.ts`: how it builds the backend base URL (the `NEXT_PUBLIC_*` var), the fetch wrapper (e.g. `apiGet`), and where TypeScript types live (inline vs `types.ts`). MATCH that pattern exactly. Do NOT invent a new fetch mechanism.

- [ ] **Step 2: Add four typed fetch helpers**

Mirroring the existing helpers, add (types reflect Task 1's JSON shapes):

```typescript
export interface IcTrendPoint { computed_at: string; ic: number; n: number; }
export interface IcTrendSeries { signal_name: string; points: IcTrendPoint[]; }
export interface EvolutionWeight {
  signal_name: string; status: "live" | "shadow"; weight: number;
  reason: string | null; consecutive_bad_windows: number;
  shadow_streak: number; last_updated: string | null;
}
export interface CalibrationBucket {
  lo: number; hi: number; hit_rate: number | null; brier: number | null; n: number;
}
export interface EvolutionCalibration {
  as_of: string | null; n_pairs: number; applied: boolean;
  isotonic_map?: { x: number[]; y: number[] }; buckets: CalibrationBucket[];
}
export interface EvolutionChange {
  id: number; source: string; changed_at: string;
  rollback_of: number | null; new_value: string;
}

export const fetchIcTrend = (windowDays = 30) =>
  apiGet<{ window_days: number; series: IcTrendSeries[] }>(`/api/evolution/ic_trend?window_days=${windowDays}`);
export const fetchEvolutionWeights = () =>
  apiGet<{ weights: EvolutionWeight[] }>(`/api/evolution/weights`);
export const fetchCalibration = () =>
  apiGet<EvolutionCalibration>(`/api/evolution/calibration`);
export const fetchChanges = (limit = 50) =>
  apiGet<{ changes: EvolutionChange[] }>(`/api/evolution/changes?limit=${limit}`);
```

Adapt `apiGet` to the file's actual wrapper name/signature. If types live in `types.ts`, put the interfaces there and import them.

- [ ] **Step 3: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/types.ts 2>/dev/null; git add frontend/src/lib/api.ts
git commit -m "feat(evolution): frontend API client + types"
```

---

### Task 4: `/evolution` page shell + nav + i18n

**Files:**
- Create: `frontend/src/app/(dashboard)/evolution/page.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`, `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Read conventions**

Read an existing dashboard page (e.g. `frontend/src/app/(dashboard)/report/page.tsx`) for the page shell pattern (client vs server component, how it fetches + lays out sections), `Sidebar.tsx` for the `NAV_GROUPS` shape, and `i18n.ts` for the key structure. The memory note says nav is grouped Research/Decisions/Reference, place `/evolution` in the most fitting group (Decisions, alongside the self-loop outputs).

- [ ] **Step 2: Create the page shell**

`frontend/src/app/(dashboard)/evolution/page.tsx`: a client component that fetches the four endpoints and renders four sections in order: IC Trend, Calibration, Adaptive Weights, Change History, plus a disabled "Pending methodology proposals" placeholder section labeled "Coming in Phase 2". Each section imports the component from Task 5/6. Use `key`-stable layout matching the repo's section styling (the `tm-*` classes / Card components seen in report/factors pages). Handle loading + empty states (e.g. calibration `applied:false` → "Calibration accumulating data (N/50 pairs)").

- [ ] **Step 3: Add nav + i18n**

Add a `{ id: "evolution", labelKey: "nav.evolution", href: "/evolution", icon: <lucide icon> }` entry to `Sidebar.tsx`'s `NAV_GROUPS` (use a lucide-react icon, NOT an emoji, per the project's icon rule). Add `nav.evolution` + `evolution.*` section titles to `i18n.ts` (zh + en).

- [ ] **Step 4: Typecheck + lint + build**

From `frontend/`: `npx tsc --noEmit && npx next lint && npm run build`
Expected: clean (the page may render empty sections until Task 5/6 add charts, that is fine; it must compile + build).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/\(dashboard\)/evolution/page.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/lib/i18n.ts
git commit -m "feat(evolution): /evolution page shell + nav + i18n"
```

---

### Task 5: IC trend + reliability charts

**Files:**
- Create: `frontend/src/components/evolution/IcTrendChart.tsx`, `frontend/src/components/evolution/ReliabilityChart.tsx`

- [ ] **Step 1: Read recharts usage**

Read how `report/page.tsx` or `factors/page.tsx` uses recharts (the `ResponsiveContainer` wrapper, memory note: it MUST be wrapped in a `<div style={{width:"100%",height:N}}>` or it renders 0-width in grid/flex parents). Match that.

- [ ] **Step 2: `IcTrendChart.tsx`**

A client component taking `series: IcTrendSeries[]`. Render a recharts `LineChart` (one `<Line>` per signal, `dataKey="ic"`, x-axis = `computed_at` formatted short). Memoize the merged-by-timestamp data. Wrap in `<div style={{width:"100%",height:320}}><ResponsiveContainer>...`. Show an empty state ("IC history accumulating") when all series are empty. A horizontal reference line at ic=0.

- [ ] **Step 3: `ReliabilityChart.tsx`**

A client component taking `calibration: EvolutionCalibration`. Render a recharts chart plotting bucket midpoint `(lo+hi)/2` (x) vs `hit_rate` (y), plus a y=x diagonal reference (perfect calibration), and Brier per bucket as a secondary display (tooltip or bar). Skip buckets with `n===0`. Empty/identity state when `applied===false`: show "Calibration not yet applied (N/50 pairs)".

- [ ] **Step 4: Wire into the page + typecheck/lint/build**

Import both into `evolution/page.tsx`. From `frontend/`: `npx tsc --noEmit && npx next lint && npm run build`. Then manually load `/evolution` against the dev server (or a preview) and confirm both charts render with prod data (IC line for ≥1 signal; reliability curve from the active calibration).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/evolution/IcTrendChart.tsx frontend/src/components/evolution/ReliabilityChart.tsx frontend/src/app/\(dashboard\)/evolution/page.tsx
git commit -m "feat(evolution): IC trend + calibration reliability charts"
```

---

### Task 6: Weight-delta + change-history tables

**Files:**
- Create: `frontend/src/components/evolution/WeightDeltaTable.tsx`, `frontend/src/components/evolution/ChangeHistoryTable.tsx`

- [ ] **Step 1: `WeightDeltaTable.tsx`**

Client component taking `weights: EvolutionWeight[]`. Pivot to one row per signal showing: live weight, shadow weight, delta (shadow − live), shadow_streak (as `N/5` toward promotion), reason, and a badge when `consecutive_bad_windows>0`. Sort by absolute delta desc so the signals about to change surface first. Empty state when no rows.

- [ ] **Step 2: `ChangeHistoryTable.tsx`**

Client component taking `changes: EvolutionChange[]`. One row per change: timestamp, source (badge: auto_promote / cold_start_seed / auto_rollback), and for rollbacks show `rollback_of` linking to the row it reverts. Parse `new_value` JSON to show `baseline_ic` when present. Newest first.

- [ ] **Step 3: Wire into the page + typecheck/lint/build**

Import both into `evolution/page.tsx`. From `frontend/`: `npx tsc --noEmit && npx next lint && npm run build`. Manually load `/evolution` and confirm the weight table shows live vs shadow for the 11 signals and the change history shows the cold_start_seed/auto_promote rows from prod.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/evolution/WeightDeltaTable.tsx frontend/src/components/evolution/ChangeHistoryTable.tsx frontend/src/app/\(dashboard\)/evolution/page.tsx
git commit -m "feat(evolution): weight-delta + change-history tables"
```

---

## Self-Review

**Spec coverage (design section 9, Evolution panel):** daily per-signal IC trend (Task 1 `/ic_trend` + Task 5 `IcTrendChart`); calibration reliability curve + Brier (Task 1 `/calibration` + Task 5 `ReliabilityChart`); what auto-changed (weight deltas + shadow status) (Task 1 `/weights` + Task 6 `WeightDeltaTable`); rollback history (Task 1 `/changes` + Task 6 `ChangeHistoryTable`). The "pending methodology proposals + approve/reject" item is intentionally a labeled placeholder (Task 4 Step 2) because the proposer (2a) and approval queue (2b) are separate later plans.

**Placeholder scan:** No TBD/TODO. The "read the existing file and match the pattern" steps (api.ts wrapper, app.py router registration, Sidebar NAV_GROUPS, recharts ResponsiveContainer) are deliberate convention-matching steps with the target file named and the expected pattern described, consistent with how Phases 1a/1b/1c handled call-site edits.

**Type consistency:** the four endpoint JSON shapes in Task 1 match the TypeScript interfaces in Task 3 (`IcTrendSeries.points[].computed_at/ic/n`; `EvolutionWeight.status/weight/shadow_streak`; `EvolutionCalibration.applied/n_pairs/buckets[]`; `EvolutionChange.source/rollback_of/new_value`). The components in Tasks 5/6 consume exactly those interfaces.

**Read-only invariant:** every endpoint is GET and only SELECTs; no endpoint writes. The panel cannot mutate engine state (approve/reject lands in 2b). This keeps Phase 2c low-risk and free of the config-ification prerequisite.

**Out of scope (later plans):** DB-backed engine config (2-pre), methodology proposer with purged walk-forward + Deflated-Sharpe-lite (2a), approval queue + apply/rollback of methodology changes (2b). Phase 2c only visualizes existing self-loop output.

**Frontend testing note:** the repo has no frontend unit-test runner, so frontend tasks verify via `tsc --noEmit` + `next lint` + `npm run build` + a manual browser check against prod data. Backend Task 1 has real pytest coverage against `applied_db`.
