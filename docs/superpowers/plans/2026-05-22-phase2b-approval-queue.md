# Phase 2b: Methodology Approval Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human review the proposer's pending config-change proposals with their evidence and, in one click, approve (apply the knob change via the 2-pre config store + journal it for rollback) or reject, with nothing applying automatically, plus a one-click rollback of an applied change.

**Architecture:** Builds on Phase 2-pre (`config_store.set_config`) + Phase 2a (pending proposals in `config_change_log` with `status='pending'` + `evidence`). Backend: three mutation endpoints on the existing `evolution` router (already enumerated in both app entries) plus the existing `GET` reads. `approve` calls `set_config(pool, key, new_value, source='approved')` (which applies the live value AND journals an apply row, so the change is immediately effective and rollback-able) then marks the proposal `status='approved'`. `reject` marks `status='rejected'`. `rollback` re-applies the proposal's `old_value` via `set_config(..., source='rollback')` and journals a `rollback_of` row. Frontend: the Phase 2c Evolution panel's "Pending Methodology Proposals" placeholder becomes a real table with evidence + Approve/Reject buttons, and the Change History gains rollback affordance.

**Tech Stack:** FastAPI + asyncpg (backend, pytest + `client_with_db`), Next.js 14 + `lib/api/evolution.ts` (`apiPost`), recharts not needed. Auth: approve/reject/rollback are admin mutations, use the repo's existing admin/auth guard.

**Decisions locked (2026-05-22):** pure human-gated, nothing auto-applies; approve applies via `set_config` (shared 1b/2-pre journal) so rollback uses the same substrate; reject is a no-op apply (status only).

---

## Dependencies + grounding (read first during Task 1)

- Phase 2-pre merged: `config_store.set_config(pool, key, value, user_id, source)` (upserts engine_config + journals config_change_log).
- Phase 2a merged: V015 added `status` + `evidence` to `config_change_log`; the proposer writes `status='pending'` rows with `field`=knob key, `old_value`/`new_value` JSON, `evidence` JSON.
- Existing `evolution` router (`alpha_agent/api/routes/evolution.py`, Phase 2c) is GET-only + already enumerated in `app.py` AND `api/index.py` (so adding routes to it needs NO new enumeration; CONFIRM).
- Auth: read how `admin.py` guards mutations (the admin dependency) and apply the same to approve/reject/rollback.
- Frontend: the 2c page `frontend/src/app/(dashboard)/evolution/page.tsx` has a labeled "Pending Methodology Proposals" placeholder; `lib/api/evolution.ts` has the read client + `apiGet`. `lib/api/client.ts` has `apiPost` (confirm its signature).

---

## File Structure

- `alpha_agent/api/routes/evolution.py` (modify): add `GET /api/evolution/proposals`, `POST /api/evolution/proposals/{id}/approve`, `.../reject`, `.../rollback`.
- `tests/api/test_evolution_approval.py` (new).
- `frontend/src/lib/api/evolution.ts` (modify): `fetchProposals`, `approveProposal`, `rejectProposal`, `rollbackChange` helpers + types.
- `frontend/src/components/evolution/ProposalsTable.tsx` (new): pending proposals + evidence + Approve/Reject buttons.
- `frontend/src/app/(dashboard)/evolution/page.tsx` (modify): replace the placeholder with `<ProposalsTable>`.

---

### Task 1: Approval endpoints (list / approve / reject / rollback)

**Files:**
- Modify: `alpha_agent/api/routes/evolution.py`
- Test: `tests/api/test_evolution_approval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_evolution_approval.py
import json

import asyncpg
import pytest


async def _seed_pending(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row_id = await conn.fetchval(
            "INSERT INTO config_change_log (user_id, field, old_value, new_value, source, status, evidence) "
            "VALUES (0, 'rating.no_trade_band', '0.15', '0.2', 'proposer', 'pending', $1::jsonb) RETURNING id",
            json.dumps({"sharpe_oos": 0.8, "n_trials": 4, "rationale": "band 0.15->0.2"}),
        )
        return row_id
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_pending_proposals(client_with_db, applied_db):
    await _seed_pending(applied_db)
    body = client_with_db.get("/api/evolution/proposals").json()
    assert any(p["field"] == "rating.no_trade_band" and p["status"] == "pending"
               for p in body["proposals"])
    assert body["proposals"][0]["evidence"]["n_trials"] == 4


@pytest.mark.asyncio
async def test_approve_applies_and_marks_approved(client_with_db, applied_db):
    pid = await _seed_pending(applied_db)
    r = client_with_db.post(f"/api/evolution/proposals/{pid}/approve")
    assert r.status_code == 200
    conn = await asyncpg.connect(applied_db)
    try:
        # engine_config now holds the approved value (applied via set_config).
        v = await conn.fetchval("SELECT value FROM engine_config WHERE key='rating.no_trade_band'")
        assert json.loads(v) == pytest.approx(0.2)
        # proposal row marked approved.
        st = await conn.fetchval("SELECT status FROM config_change_log WHERE id=$1", pid)
        assert st == "approved"
        # an apply row was journaled (source='approved').
        n = await conn.fetchval("SELECT count(*) FROM config_change_log WHERE source='approved'")
        assert n >= 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reject_marks_rejected_without_applying(client_with_db, applied_db):
    pid = await _seed_pending(applied_db)
    client_with_db.post(f"/api/evolution/proposals/{pid}/reject")
    conn = await asyncpg.connect(applied_db)
    try:
        st = await conn.fetchval("SELECT status FROM config_change_log WHERE id=$1", pid)
        assert st == "rejected"
        # engine_config NOT written (reject does not apply).
        exists = await conn.fetchval("SELECT count(*) FROM engine_config WHERE key='rating.no_trade_band'")
        assert exists == 0
    finally:
        await conn.close()
```

(If approve/reject require admin auth, seed an admin session per the repo's admin-test pattern; READ an existing admin mutation test first and match it.)

- [ ] **Step 2: Run to verify it fails**, 404s (endpoints absent).

- [ ] **Step 3: Implement the endpoints in `evolution.py`**

Add (importing `set_config` + the admin auth dependency; mirror admin.py):

```python
from alpha_agent.config_store import set_config

@router.get("/proposals")
async def proposals() -> dict[str, Any]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT id, field, old_value, new_value, evidence, changed_at, status "
        "FROM config_change_log WHERE status = 'pending' ORDER BY changed_at DESC"
    )
    return {"proposals": [{
        "id": r["id"], "field": r["field"],
        "old_value": _decode_jsonb(r["old_value"]) if r["old_value"] else None,
        "new_value": _decode_jsonb(r["new_value"]),
        "evidence": _decode_jsonb(r["evidence"]) if r["evidence"] else {},
        "changed_at": r["changed_at"].isoformat(), "status": r["status"],
    } for r in rows]}


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: int) -> dict[str, Any]:  # + admin auth dep
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT field, new_value FROM config_change_log WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(404, "proposal not found or not pending")
    new_value = _decode_jsonb(row["new_value"])
    await set_config(pool, row["field"], new_value, user_id=0, source="approved")
    await pool.execute("UPDATE config_change_log SET status='approved' WHERE id=$1", proposal_id)
    return {"ok": True, "applied": {row["field"]: new_value}}


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: int) -> dict[str, Any]:  # + admin auth dep
    pool = await get_db_pool()
    n = await pool.execute(
        "UPDATE config_change_log SET status='rejected' WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    return {"ok": True}


@router.post("/proposals/{proposal_id}/rollback")
async def rollback(proposal_id: int) -> dict[str, Any]:  # + admin auth dep
    """Revert an approved change: re-apply its old_value and journal a
    rollback_of row."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT field, old_value FROM config_change_log WHERE id=$1 AND status='approved'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(404, "approved change not found")
    old_value = _decode_jsonb(row["old_value"]) if row["old_value"] else None
    await set_config(pool, row["field"], old_value, user_id=0, source="rollback")
    await pool.execute(
        "UPDATE config_change_log SET rollback_of=$1 WHERE id=("
        "  SELECT max(id) FROM config_change_log WHERE field=$2 AND source='rollback')",
        proposal_id, row["field"],
    )
    return {"ok": True, "reverted": {row["field"]: old_value}}
```

Update the router/module docstring: it is no longer strictly read-only (it now has the human-gated approval mutations). Add `from fastapi import HTTPException` if absent. Apply the admin auth dependency to the three POSTs (match admin.py).

- [ ] **Step 4: Run to verify it passes**, `uv run pytest tests/api/test_evolution_approval.py -v` → PASS. Confirm no new router enumeration needed (evolution already in both entries).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/evolution.py tests/api/test_evolution_approval.py
git commit -m "feat(evolution): human-gated approve/reject/rollback for methodology proposals"
```

---

### Task 2: Frontend proposals client + types

**Files:**
- Modify: `frontend/src/lib/api/evolution.ts`

- [ ] **Step 1: Read `lib/api/client.ts`** for `apiPost` (signature + how it sends the bearer/auth header, since these are admin mutations).

- [ ] **Step 2: Add types + helpers**

```typescript
export interface Proposal {
  id: number; field: string;
  old_value: unknown; new_value: unknown;
  evidence: Record<string, unknown>;
  changed_at: string; status: string;
}
export const fetchProposals = (opts?: ApiGetOptions) =>
  apiGet<{ proposals: Proposal[] }>("/api/evolution/proposals", opts);
export const approveProposal = (id: number) =>
  apiPost(`/api/evolution/proposals/${id}/approve`, {});
export const rejectProposal = (id: number) =>
  apiPost(`/api/evolution/proposals/${id}/reject`, {});
export const rollbackChange = (id: number) =>
  apiPost(`/api/evolution/proposals/${id}/rollback`, {});
```

Adapt to `apiPost`'s real signature. `tsc --noEmit` clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/evolution.ts
git commit -m "feat(evolution): frontend proposals client (list/approve/reject/rollback)"
```

---

### Task 3: ProposalsTable component + wire into the panel

**Files:**
- Create: `frontend/src/components/evolution/ProposalsTable.tsx`
- Modify: `frontend/src/app/(dashboard)/evolution/page.tsx`

- [ ] **Step 1: Build `ProposalsTable.tsx`**

A `"use client"` component taking `proposals: Proposal[]`. One row per pending proposal: field, old -> new value, key evidence (Sharpe OOS, deflated Sharpe, n_trials, rationale from `evidence`), and Approve / Reject buttons that call `approveProposal(id)` / `rejectProposal(id)` then refresh (router.refresh() or local state). Disable buttons while the request is in flight; show a toast/inline result. Empty state: "No pending proposals (the proposer is dormant until enough history accrues)", which is the expected early state.

- [ ] **Step 2: Wire into the page**

The `/evolution` page is currently a server component. Since proposals need interactive mutations, fetch `proposals` server-side (add `fetchProposals()` to the page's `Promise.allSettled`) and pass the data into the client `<ProposalsTable>`; the buttons do client-side `apiPost` + `router.refresh()`. Replace the "Pending Methodology Proposals, Coming in Phase 2" placeholder with `<ProposalsTable proposals={proposals.proposals} />`.

- [ ] **Step 3: tsc + lint + build**

From `frontend/`: `npx tsc --noEmit && npx next lint && npm run build`. `/evolution` must compile (pre-existing `/picks` ECONNREFUSED unrelated). Manually (if backend reachable) confirm the section shows the empty state (no pending proposals yet) or seeded proposals with working buttons.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/evolution/ProposalsTable.tsx "frontend/src/app/(dashboard)/evolution/page.tsx"
git commit -m "feat(evolution): pending-proposals table with approve/reject in the panel"
```

---

## Self-Review

**Spec coverage (design section 8 approval + section 9 UI controls):** list pending proposals with evidence (Task 1 GET + Task 3 table); one-click approve that applies via `set_config` and journals for rollback (Task 1 approve); reject without applying (Task 1 reject); rollback of an applied change (Task 1 rollback); the Evolution panel's pending-proposals controls (Task 3). Nothing auto-applies, all three mutations are human-triggered + admin-guarded.

**Shared rollback substrate:** approve/rollback both go through `config_store.set_config`, which journals to `config_change_log` exactly like the Phase 1b auto tier and Phase 2-pre manual sets, so the Change-History panel (2c) shows methodology applies + rollbacks alongside weight promotions uniformly.

**Human-gated invariant:** the only write to `engine_config` from this plan is inside `approve`/`rollback`, both behind admin auth + an explicit user click. `reject` touches only `status`. The proposer (2a) never writes `engine_config`. Tested in Task 1 (`test_reject_marks_rejected_without_applying` asserts no engine_config write).

**Placeholder scan:** No TBD/TODO. The admin-auth dependency + `apiPost` signature are "read the existing pattern and match" steps (named files), consistent with prior phases. The rollback's "find the just-written rollback row to set rollback_of" uses `max(id) WHERE source='rollback'` within the same call; if the repo has a cleaner RETURNING pattern, use it (note in report).

**Dual-entry reminder:** all endpoints are added to the EXISTING `evolution` router (already in both `app.py` and `api/index.py`), so no new enumeration, Task 1 Step 4 re-confirms.

**Out of scope:** auto-apply (forbidden), proposing logic (2a), the config knobs themselves (2-pre). This plan only adds the human review + apply/reject/rollback layer + its UI.