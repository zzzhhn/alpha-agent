# Phase 3d Factor-Lab UI + Approval Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the human-gated approval surface on top of Phase 3c. Backend gains three admin-guarded mutation endpoints (approve / reject / rollback) plus one read endpoint (list proposals). Frontend gains a new `/factor-lab` admin page with four sections (current live expression, diagnostic snapshot, propose button + result, pending proposals table) and a history tab. Approving a proposal registers its new operators into `extended_operators`, refreshes the AST whitelist, and writes the expression to `factor.custom_expression`; rollback reverts the expression but keeps operators registered.

**Architecture:** New endpoints land on the existing `factor_lab` router from Phase 3c-T5, so no new `_load(...)` registration is needed (the router is already dual-entry). Approve flow: validate proposal is pending, INSERT each new operator into `extended_operators` (idempotent via `ON CONFLICT (name) DO NOTHING`), call `set_config(pool, "factor.custom_expression", proposal.expression, user_id, source="approved")`, mark proposal `approved` + `decided_at` + `decided_by`, then `refresh_allowed_ops(pool)` so the AST validator accepts the new operator names from the next request. Rollback: read the approved proposal's prior `factor.custom_expression` value from `config_change_log` history; `set_config(..., source="rollback")` to revert; operators stay in `extended_operators` for audit + future reuse. Frontend page is a Next.js server component that pre-fetches diagnostic + pending proposals + history via `Promise.allSettled`; client components handle the propose / approve / reject / rollback button mutations + `router.refresh()`.

**Tech Stack:** FastAPI + asyncpg backend; Next.js 14 App Router + TypeScript frontend. Reuses Phase 2-pre `set_config`, Phase 3a `refresh_allowed_ops`, Phase 3c `factor_lab` router. No new tables, no migrations.

**UX principles applied to 3d (where the 5 rules finally land on actual pixels):**

1. **Intent alignment**: The page flow mirrors the human's mental sequence. Top: current live expression (read it, decide if you want a change). Middle: diagnostic snapshot (what would the LLM be told?). Then: Propose button (single primary action, prominent). Then: Pending proposals table (Approve/Reject buttons inline per row). Bottom: History tab (Rollback inline per approved row). Each section answers the question raised by the previous one.
2. **Cognitive load minimization**: Pending proposals table has 5 columns max (Expression, Deflated Sharpe, IC OOS, n_folds, Actions). `new_operators` Python code stays collapsed by default behind a `<details>` toggle; only the operator name + signature show by default. Status badges are 3 colors only (pending=amber, approved=green, rejected=gray); no other state coloring competes.
3. **Visibility of system status**: A spinner appears immediately on Propose click; the button label changes to "Proposing... (this may take 30-60s)" so the human knows the LLM call is in flight, not stuck. A "Dormant" pill renders when `dormant=true` is returned, with a tooltip explaining the cost-guard threshold. Approve/Reject buttons disable per-row during request; success/error toast appears on completion. Last-refreshed timestamp on diagnostic ("Snapshot taken X minutes ago"). When `app.state.allowed_ops_refresh_error` is non-null (from /api/healthz/ast), a warning banner surfaces above the page.
4. **Forgiveness**: Approve action shows a confirmation modal *only* when the proposal contains new operators (highest-stakes case: registering new sandboxed code). Reject is one-click, no confirmation (low-stakes, reversible via reproposing). Rollback is per-row inline in history (single click, no modal — the rollback itself is the safety net for an over-eager approve). All three mutations are reversible: approve can be rolled back; reject can be re-proposed; rollback restores a known prior state from `config_change_log`.
5. **Affordance**: Button labels match the verb (Approve, Reject, Rollback). Expression code renders in monospace with a `Copy` icon-button (lucide `Clipboard`). Status badges use the exact words from the DB enum (pending/approved/rejected) so the UI and the data shape stay isomorphic. The `/factor-lab` URL path appears in the page heading so an admin sharing a screenshot can reference it without ambiguity.

---

## Dependencies + grounding (read first during Task 1)

- Phase 3a: `factor_proposals` table (`status text CHECK pending|approved|rejected, expression, new_operators jsonb, evidence jsonb, diagnostic jsonb, created_at, decided_at, decided_by`); `extended_operators` table (`name PK, signature, python_impl, doc, registered_at, registered_by, source_proposal_id FK`); `refresh_allowed_ops(pool_or_dsn)`.
- Phase 2-pre: `set_config(pool, key, value, user_id, source)` upserts `engine_config` AND journals to `config_change_log` (source values seen so far: `manual`, `approved`, `rollback`, `auto`).
- Phase 3c: `factor_lab` router exists at `alpha_agent/api/routes/factor_lab.py` and is already enumerated in both `app.py` and `api/index.py` (verified via 3c-T5 smoke). New routes go onto the same router; no new `_load(...)` calls needed.
- Phase 2b approval-queue precedent: read `alpha_agent/api/routes/evolution.py` (lines ~135-220) for the approve/reject/rollback shape on `config_change_log` proposals. The 3d endpoints follow the same structure but operate on `factor_proposals` + write `factor.custom_expression`.
- Frontend grounding:
  - `frontend/src/lib/api/client.ts` exports `apiGet<T>(path, opts?)` and `apiPost<T, B>(path, body)`; auth header is auto-attached by middleware.
  - `frontend/src/lib/api/evolution.ts` is the precedent for an api-helper module (Proposal type + helpers). Mirror for `lib/api/factor-lab.ts`.
  - `frontend/src/app/(dashboard)/evolution/page.tsx` is the precedent for an admin proposals page (server component + Promise.allSettled + client child components). Mirror layout, do NOT duplicate.
  - `frontend/src/components/evolution/ProposalsTable.tsx` is the existing pattern for a per-row action component (pendingId state, router.refresh on success). Mirror for the new `FactorProposalsTable`.

**Anti-pattern guardrails (relearned this session):**
- **Dual-entry**: Not relevant for 3d backend (router already registered); IS relevant if Task 1 ends up adding ANY new router. The default expectation is none added.
- **Silent exception**: Each new mutation has explicit 404 on non-pending / non-approved row mismatch (mirror 2b reject-404 fix from Phase 2b). `refresh_allowed_ops` failure inside approve handler must surface to the response, not log-and-pretend-success.
- **Grep call chain for duplicate names** (sedimented from Phase 3c memory): Before extending any frontend hook or backend helper, grep callers. Here the risk is low (factor_lab router has only the two 3c endpoints), but the `/evolution` precedent file structure must be confirmed by reading the files, not by name-guessing.

---

## File Structure

- `alpha_agent/api/routes/factor_lab.py` (modify): add `GET /proposals`, `POST /proposals/{id}/approve`, `.../reject`, `.../rollback`.
- `tests/api/test_factor_lab_approval.py` (new).
- `frontend/src/lib/api/factor-lab.ts` (new): `FactorProposal` type + `fetchFactorProposals`, `proposeFactors`, `approveFactorProposal`, `rejectFactorProposal`, `rollbackFactor`.
- `frontend/src/app/(dashboard)/factor-lab/page.tsx` (new): server component with the 4 sections.
- `frontend/src/components/factor-lab/PendingFactorProposalsTable.tsx` (new): client component with Approve/Reject buttons.
- `frontend/src/components/factor-lab/ProposeButton.tsx` (new): client component that POSTs propose and triggers router.refresh.
- `frontend/src/components/factor-lab/FactorHistoryTable.tsx` (new): approved + rejected history with Rollback per approved row.

---

### Task 1: Backend approval endpoints (list + 3 mutations)

**Files:**
- Modify: `alpha_agent/api/routes/factor_lab.py`
- Test: `tests/api/test_factor_lab_approval.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_factor_lab_approval.py
import json
import time

import asyncpg
import pytest
from jose import jwt

_SECRET = "test-secret-not-real-0123456789"


def _auth(sub: str = "1") -> dict:
    now = int(time.time())
    tok = jwt.encode({"sub": sub, "iat": now, "exp": now + 3600}, _SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def authed_client(client_with_db, monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)
    return client_with_db


async def _seed_pending(applied_db, expression="rank(returns)", new_operators=None):
    conn = await asyncpg.connect(applied_db)
    try:
        return await conn.fetchval(
            "INSERT INTO factor_proposals "
            "(expression, new_operators, evidence, diagnostic) "
            "VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb) RETURNING id",
            expression,
            json.dumps(new_operators or []),
            json.dumps({"sharpes": [0.8, 0.7, 0.9], "ic_oos": 0.04,
                        "deflated_sharpe": 0.5, "baseline_sharpe": 0.3,
                        "n_folds": 3, "n_trials": 5,
                        "llm_rationale": "shorter window", "operator_test_results": []}),
            json.dumps({"current_expression": "rank(returns)",
                        "weak_signal": "news_24h", "weak_signal_ic": 0.003,
                        "worst_fold_sharpe": None, "worst_fold_window": None,
                        "symptom_summary": "test"}),
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_list_pending_proposals(client_with_db, applied_db):
    await _seed_pending(applied_db)
    body = client_with_db.get("/api/factor-lab/proposals").json()
    assert any(p["status"] == "pending" for p in body["proposals"])
    p = body["proposals"][0]
    assert p["evidence"]["n_folds"] == 3
    assert p["diagnostic"]["weak_signal"] == "news_24h"


@pytest.mark.asyncio
async def test_list_proposals_filters_by_status(client_with_db, applied_db):
    """Affordance: ?status=approved filter returns only approved rows."""
    pid = await _seed_pending(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute("UPDATE factor_proposals SET status='approved' WHERE id=$1", pid)
    finally:
        await conn.close()
    body = client_with_db.get("/api/factor-lab/proposals?status=approved").json()
    assert all(p["status"] == "approved" for p in body["proposals"])


@pytest.mark.asyncio
async def test_approve_writes_custom_expression_and_marks_approved(authed_client, applied_db):
    pid = await _seed_pending(applied_db, expression="rank(ts_mean(returns, 8))")
    r = authed_client.post(f"/api/factor-lab/proposals/{pid}/approve", headers=_auth())
    assert r.status_code == 200, r.text
    conn = await asyncpg.connect(applied_db)
    try:
        # engine_config now holds the approved expression
        v = await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='factor.custom_expression'"
        )
        assert json.loads(v) == "rank(ts_mean(returns, 8))"
        # proposal row marked approved with audit fields
        row = await conn.fetchrow(
            "SELECT status, decided_by FROM factor_proposals WHERE id=$1", pid,
        )
        assert row["status"] == "approved"
        assert row["decided_by"] == 1  # JWT sub=1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_approve_registers_new_operators(authed_client, applied_db):
    new_op = {
        "name": "lf_test_op",
        "signature": "(x: ndarray) -> ndarray",
        "python_impl": "def lf_test_op(x): return x",
        "doc": "test",
    }
    pid = await _seed_pending(applied_db, expression="lf_test_op(returns)",
                              new_operators=[new_op])
    authed_client.post(f"/api/factor-lab/proposals/{pid}/approve", headers=_auth())
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow(
            "SELECT name, source_proposal_id FROM extended_operators "
            "WHERE name='lf_test_op'"
        )
        assert row is not None
        assert row["source_proposal_id"] == pid
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_approve_is_idempotent_on_existing_operator(authed_client, applied_db):
    """Forgiveness: approving a proposal whose operator is already registered
    (e.g. same name from a prior approved proposal) does NOT crash; the second
    approval skips the duplicate via ON CONFLICT DO NOTHING."""
    new_op = {
        "name": "lf_shared_op", "signature": "(x: ndarray) -> ndarray",
        "python_impl": "def lf_shared_op(x): return x", "doc": "shared",
    }
    pid1 = await _seed_pending(applied_db, new_operators=[new_op])
    authed_client.post(f"/api/factor-lab/proposals/{pid1}/approve", headers=_auth())
    pid2 = await _seed_pending(applied_db, new_operators=[new_op])
    r = authed_client.post(f"/api/factor-lab/proposals/{pid2}/approve", headers=_auth())
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reject_marks_rejected_without_writing_engine_config(authed_client, applied_db):
    pid = await _seed_pending(applied_db)
    authed_client.post(f"/api/factor-lab/proposals/{pid}/reject", headers=_auth())
    conn = await asyncpg.connect(applied_db)
    try:
        st = await conn.fetchval("SELECT status FROM factor_proposals WHERE id=$1", pid)
        assert st == "rejected"
        # No engine_config row should have been touched.
        n = await conn.fetchval(
            "SELECT count(*) FROM engine_config WHERE key='factor.custom_expression'"
        )
        assert n == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_reject_404_on_non_pending(authed_client):
    """Mirror Phase 2b reject 404 symmetry: silent no-op on missing/decided
    proposals would be a misleading success."""
    r = authed_client.post("/api/factor-lab/proposals/999999/reject", headers=_auth())
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rollback_reverts_custom_expression(authed_client, applied_db):
    """Approve sets custom_expression to expr_X; rollback reverts to whatever
    the prior value was (NULL on first approval). Operators stay registered."""
    pid = await _seed_pending(applied_db, expression="rank(returns)",
                              new_operators=[{
                                  "name": "lf_rollback_op",
                                  "signature": "(x) -> ndarray",
                                  "python_impl": "def lf_rollback_op(x): return x",
                                  "doc": "",
                              }])
    authed_client.post(f"/api/factor-lab/proposals/{pid}/approve", headers=_auth())
    conn = await asyncpg.connect(applied_db)
    try:
        v_after_approve = await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='factor.custom_expression'"
        )
        assert json.loads(v_after_approve) == "rank(returns)"
    finally:
        await conn.close()
    authed_client.post(f"/api/factor-lab/proposals/{pid}/rollback", headers=_auth())
    conn = await asyncpg.connect(applied_db)
    try:
        v_after_rollback = await conn.fetchval(
            "SELECT value FROM engine_config WHERE key='factor.custom_expression'"
        )
        # Reverted to None (the prior state before the first approval).
        assert v_after_rollback is None or json.loads(v_after_rollback) is None
        # Operator stays registered (spec decision; for audit + reproducibility).
        op_n = await conn.fetchval(
            "SELECT count(*) FROM extended_operators WHERE name='lf_rollback_op'"
        )
        assert op_n == 1
    finally:
        await conn.close()
```

- [ ] **Step 2: Run, verify FAIL** (404 / 405 on missing routes)

`uv run pytest tests/api/test_factor_lab_approval.py -v -p no:randomly`

- [ ] **Step 3: Implement the endpoints**

Append to `alpha_agent/api/routes/factor_lab.py` (after the existing `/diagnostic` + `/propose`):

```python
from alpha_agent.config_store import set_config
from alpha_agent.core.factor_ast import refresh_allowed_ops


def _decode_jsonb(value):
    """asyncpg can return jsonb already-decoded (dict/list) OR as a str
    depending on driver version; normalize to native Python."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


@router.get("/proposals")
async def list_proposals(
    status: str | None = None,
    pool=Depends(get_db_pool),
) -> dict:
    """List factor proposals. Optional ?status=pending|approved|rejected filter.
    Unauthed read (matches /diagnostic and the evolution router precedent)."""
    if status is None:
        rows = await pool.fetch(
            "SELECT id, status, expression, new_operators, evidence, diagnostic, "
            "created_at, decided_at, decided_by FROM factor_proposals "
            "ORDER BY created_at DESC LIMIT 200"
        )
    else:
        if status not in {"pending", "approved", "rejected"}:
            raise HTTPException(400, f"invalid status: {status}")
        rows = await pool.fetch(
            "SELECT id, status, expression, new_operators, evidence, diagnostic, "
            "created_at, decided_at, decided_by FROM factor_proposals "
            "WHERE status = $1 ORDER BY created_at DESC LIMIT 200",
            status,
        )
    return {"proposals": [{
        "id": r["id"],
        "status": r["status"],
        "expression": r["expression"],
        "new_operators": _decode_jsonb(r["new_operators"]) or [],
        "evidence": _decode_jsonb(r["evidence"]) or {},
        "diagnostic": _decode_jsonb(r["diagnostic"]) or {},
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
        "decided_by": r["decided_by"],
    } for r in rows]}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Register the proposal's new operators in extended_operators (idempotent),
    set factor.custom_expression to the proposal's expression (via set_config
    so config_change_log gets a journal row), refresh the AST whitelist union
    so the new operators become validate-able immediately, and mark the
    proposal approved with audit fields."""
    row = await pool.fetchrow(
        "SELECT expression, new_operators FROM factor_proposals "
        "WHERE id=$1 AND status='pending'",
        proposal_id,
    )
    if row is None:
        raise HTTPException(404, "proposal not found or not pending")
    new_ops = _decode_jsonb(row["new_operators"]) or []
    for op in new_ops:
        await pool.execute(
            "INSERT INTO extended_operators "
            "(name, signature, python_impl, doc, registered_by, source_proposal_id) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "ON CONFLICT (name) DO NOTHING",
            op["name"], op.get("signature", ""), op["python_impl"],
            op.get("doc", ""), user_id, proposal_id,
        )
    await set_config(pool, "factor.custom_expression",
                     row["expression"], user_id=user_id, source="approved")
    await pool.execute(
        "UPDATE factor_proposals SET status='approved', decided_at=now(), decided_by=$1 "
        "WHERE id=$2", user_id, proposal_id,
    )
    # AST whitelist must accept the new operator names from the next request.
    # Anti-silent: failure here would mean the validator silently rejects any
    # use of the new operator; raise so the approve response carries the error.
    try:
        await refresh_allowed_ops(pool)
        refresh_error = None
    except Exception as exc:  # noqa: BLE001 - surfaced in response
        refresh_error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": True,
        "applied": {"factor.custom_expression": row["expression"]},
        "registered_operators": [op["name"] for op in new_ops],
        "refresh_error": refresh_error,
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Mark the proposal rejected; no engine_config write."""
    status = await pool.execute(
        "UPDATE factor_proposals SET status='rejected', decided_at=now(), decided_by=$1 "
        "WHERE id=$2 AND status='pending'", user_id, proposal_id,
    )
    if status.rsplit(" ", 1)[-1] == "0":
        raise HTTPException(404, "proposal not found or not pending")
    return {"ok": True}


@router.post("/proposals/{proposal_id}/rollback")
async def rollback_proposal(
    proposal_id: int,
    user_id: int = Depends(require_user),
    pool=Depends(get_db_pool),
) -> dict:
    """Revert factor.custom_expression to the value preceding this proposal's
    approval. Looks up the most recent config_change_log row for
    factor.custom_expression with source='approved' that PREDATES the row
    written by this proposal's approval; uses its old_value (the prior live
    expression, possibly None). Operators stay registered in extended_operators
    (audit + reproducibility, per the Phase 3 spec decision)."""
    row = await pool.fetchrow(
        "SELECT decided_at FROM factor_proposals "
        "WHERE id=$1 AND status='approved'", proposal_id,
    )
    if row is None:
        raise HTTPException(404, "approved proposal not found")
    # The approve handler called set_config which journaled a row. Find IT and
    # read its old_value (the live custom_expression before this approval).
    prior = await pool.fetchrow(
        "SELECT old_value FROM config_change_log "
        "WHERE field='factor.custom_expression' AND source='approved' "
        "AND changed_at <= $1 ORDER BY changed_at DESC LIMIT 1",
        row["decided_at"],
    )
    old_value = _decode_jsonb(prior["old_value"]) if prior and prior["old_value"] else None
    await set_config(pool, "factor.custom_expression",
                     old_value, user_id=user_id, source="rollback")
    return {"ok": True, "reverted_to": old_value}
```

NOTE: `set_config` accepts `value=None` and stores `null` jsonb; the rating path's `_resolve_default_expr` treats both `None` and empty string as fallthrough to the preset (verified in Phase 3a-T3).

- [ ] **Step 4: Run, verify PASS**

`uv run pytest tests/api/test_factor_lab_approval.py -v -p no:randomly`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/factor_lab.py tests/api/test_factor_lab_approval.py
git commit -m "feat(factor-lab): GET /proposals + approve/reject/rollback admin endpoints (Phase 3d)"
```

---

### Task 2: Frontend client (lib/api/factor-lab.ts)

**Files:**
- Create: `frontend/src/lib/api/factor-lab.ts`

- [ ] **Step 1: READ the precedent first**

```bash
cat frontend/src/lib/api/evolution.ts | head -60
```
Mirror its style exactly: `interface` definitions at the top, `fetch*` helpers using `apiGet`, mutation helpers using `apiPost`. Take the same `ApiGetOptions` import shape.

- [ ] **Step 2: Implement**

`frontend/src/lib/api/factor-lab.ts`:
```typescript
import { apiGet, apiPost, type ApiGetOptions } from "./client";

export interface FactorProposalOperator {
  name: string;
  signature: string;
  python_impl: string;
  doc: string;
}

export interface FactorProposalEvidence {
  sharpes: number[];
  ic_oos: number;
  deflated_sharpe: number;
  baseline_sharpe: number;
  n_folds: number;
  n_trials: number;
  llm_rationale: string;
  operator_test_results: Array<{ name: string; passed: boolean; tests: unknown[] }>;
}

export interface FactorDiagnosticSnapshot {
  current_expression: string;
  weak_signal: string | null;
  weak_signal_ic: number | null;
  worst_fold_sharpe: number | null;
  worst_fold_window: [string, string] | null;
  symptom_summary: string;
}

export interface FactorProposal {
  id: number;
  status: "pending" | "approved" | "rejected";
  expression: string;
  new_operators: FactorProposalOperator[];
  evidence: FactorProposalEvidence;
  diagnostic: FactorDiagnosticSnapshot;
  created_at: string | null;
  decided_at: string | null;
  decided_by: number | null;
}

export interface ProposeResult {
  evaluated: number;
  proposed: number;
  dormant: boolean;
}

export const fetchFactorDiagnostic = (opts?: ApiGetOptions) =>
  apiGet<FactorDiagnosticSnapshot>("/api/factor-lab/diagnostic", opts);

export const fetchFactorProposals = (
  status?: "pending" | "approved" | "rejected",
  opts?: ApiGetOptions,
) =>
  apiGet<{ proposals: FactorProposal[] }>(
    status ? `/api/factor-lab/proposals?status=${status}` : "/api/factor-lab/proposals",
    opts,
  );

export const proposeFactors = (n = 5) =>
  apiPost<ProposeResult, { n: number }>("/api/factor-lab/propose", { n });

export const approveFactorProposal = (id: number) =>
  apiPost<{ ok: boolean; applied: Record<string, string>; registered_operators: string[]; refresh_error: string | null }, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/approve`, {},
  );

export const rejectFactorProposal = (id: number) =>
  apiPost<{ ok: boolean }, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/reject`, {},
  );

export const rollbackFactorProposal = (id: number) =>
  apiPost<{ ok: boolean; reverted_to: string | null }, Record<string, never>>(
    `/api/factor-lab/proposals/${id}/rollback`, {},
  );
```

- [ ] **Step 3: tsc clean**

From `frontend/`: `npx tsc --noEmit` must pass with zero NEW errors. Pre-existing errors stay as-is.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/factor-lab.ts
git commit -m "feat(factor-lab): frontend api client + types for /diagnostic /proposals /propose"
```

---

### Task 3: Frontend page + components

**Files:**
- Create: `frontend/src/app/(dashboard)/factor-lab/page.tsx`
- Create: `frontend/src/components/factor-lab/ProposeButton.tsx`
- Create: `frontend/src/components/factor-lab/PendingFactorProposalsTable.tsx`
- Create: `frontend/src/components/factor-lab/FactorHistoryTable.tsx`

- [ ] **Step 1: READ the precedent**

```bash
cat "frontend/src/app/(dashboard)/evolution/page.tsx" | head -80
ls frontend/src/components/evolution/
```
The page uses `Promise.allSettled([...fetchEvolution*])`, destructures with rejection defaults, passes data into client child components. Mirror this; do NOT copy-paste verbatim because the data shape differs.

- [ ] **Step 2: Build `ProposeButton.tsx`**

```tsx
"use client";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { proposeFactors, type ProposeResult } from "@/lib/api/factor-lab";

export function ProposeButton({ n = 5 }: { n?: number }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ProposeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await proposeFactors(n);
      setResult(r);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleClick}
        disabled={loading}
        className="px-4 py-2 rounded bg-tm-primary text-tm-primary-fg disabled:opacity-50 inline-flex items-center gap-2"
      >
        {loading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Proposing... (this may take 30-60s)</span>
          </>
        ) : (
          <span>Propose factors (n={n})</span>
        )}
      </button>
      {result && (
        <div className="text-sm">
          Evaluated {result.evaluated}, proposed {result.proposed}
          {result.dormant && (
            <span className="ml-2 px-2 py-0.5 rounded bg-amber-100 text-amber-900 text-xs">
              Dormant (insufficient history)
            </span>
          )}
        </div>
      )}
      {error && <div className="text-sm text-tm-neg">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Build `PendingFactorProposalsTable.tsx`**

A `"use client"` component taking `proposals: FactorProposal[]`. Per pending row:
- Expression (monospace font, copy icon)
- Deflated Sharpe (from `evidence.deflated_sharpe`, formatted to 3 decimals)
- IC OOS (from `evidence.ic_oos`)
- n_folds
- New operators count + collapsible `<details>` showing each operator's name + signature + python_impl in a `<pre>` block
- Approve / Reject buttons

State: `pendingId: number | null` tracks the row in flight. Approve handler: if `proposal.new_operators.length > 0`, show a `window.confirm` (cheap modal-equivalent) before calling `approveFactorProposal(id)`. After success, `router.refresh()`. Failure shows inline `text-tm-neg` text on the row.

Empty state: a muted message ("No pending proposals. Click Propose above to generate candidates.").

- [ ] **Step 4: Build `FactorHistoryTable.tsx`**

Same shape as PendingFactorProposalsTable but for `status in {approved, rejected}` rows. Approved rows have a `Rollback` button (single-click, no confirmation, mirrors 2b rollback semantics). Rejected rows show status badge only, no action.

- [ ] **Step 5: Build the page `factor-lab/page.tsx`**

```tsx
import { fetchFactorDiagnostic, fetchFactorProposals } from "@/lib/api/factor-lab";
import { ProposeButton } from "@/components/factor-lab/ProposeButton";
import { PendingFactorProposalsTable } from "@/components/factor-lab/PendingFactorProposalsTable";
import { FactorHistoryTable } from "@/components/factor-lab/FactorHistoryTable";

export const dynamic = "force-dynamic";

export default async function FactorLabPage() {
  const [diagSettled, pendingSettled, historySettled] = await Promise.allSettled([
    fetchFactorDiagnostic({ revalidate: 0, tags: ["factor-lab-diagnostic"] }),
    fetchFactorProposals("pending", { revalidate: 0, tags: ["factor-lab-pending"] }),
    fetchFactorProposals(undefined, { revalidate: 0, tags: ["factor-lab-history"] }),
  ]);

  const diagnostic = diagSettled.status === "fulfilled" ? diagSettled.value : null;
  const pending = pendingSettled.status === "fulfilled" ? pendingSettled.value.proposals : [];
  const allProposals = historySettled.status === "fulfilled" ? historySettled.value.proposals : [];
  const history = allProposals.filter(p => p.status !== "pending");

  return (
    <main className="flex flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-bold">Factor Lab</h1>
        <p className="text-sm text-tm-muted">
          Propose new factor expressions via LLM; human-gated approval registers
          them as the live factor.custom_expression.
        </p>
      </header>

      <section>
        <h2 className="text-lg font-semibold mb-2">Current live expression</h2>
        <pre className="bg-tm-card p-3 rounded text-sm overflow-x-auto">
          {diagnostic?.current_expression ?? "(loading)"}
        </pre>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-2">Diagnostic snapshot</h2>
        {diagnostic ? (
          <div className="text-sm space-y-1">
            <div>Weak signal: <strong>{diagnostic.weak_signal ?? "(none)"}</strong> (IC={diagnostic.weak_signal_ic?.toFixed(4) ?? "n/a"})</div>
            <div className="text-tm-muted">{diagnostic.symptom_summary}</div>
          </div>
        ) : (
          <div className="text-tm-neg text-sm">Failed to load diagnostic.</div>
        )}
      </section>

      <section>
        <ProposeButton n={5} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-2">Pending proposals ({pending.length})</h2>
        <PendingFactorProposalsTable proposals={pending} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-2">History ({history.length})</h2>
        <FactorHistoryTable proposals={history} />
      </section>
    </main>
  );
}
```

- [ ] **Step 6: Add nav link**

In `frontend/src/components/layout/Sidebar.tsx` (or whatever the existing admin nav file is — grep `evolution` to find it):
```bash
grep -rnE "evolution|/evolution\"|nav.*evolution" frontend/src/components/ | head -10
```
Add a `factor-lab` entry next to the existing `evolution` link with the same admin-only treatment.

- [ ] **Step 7: typecheck + lint + build**

From `frontend/`:
```bash
npx tsc --noEmit && npx next lint && npm run build
```
The known pre-existing `/picks` ECONNREFUSED during static prerender is acceptable; any error on the new `/factor-lab` route is NOT.

- [ ] **Step 8: Commit**

```bash
git add "frontend/src/app/(dashboard)/factor-lab/" frontend/src/components/factor-lab/ frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(factor-lab): /factor-lab admin page with propose + approve/reject/rollback UI (Phase 3d)"
```

- [ ] **Step 9: Deploy + smoke**

```bash
git push
BASE="https://alpha.bobbyzhong.com"
# Backend list endpoint should already be live (router was registered in 3c-T5).
for i in $(seq 1 12); do
  HTTP=$(curl -s --max-time 30 -o /tmp/ls.json -w "%{http_code}" "$BASE/api/factor-lab/proposals?status=pending")
  echo "list try $i HTTP=$HTTP"
  [ "$HTTP" = "200" ] && break
  sleep 15
done
cat /tmp/ls.json | python3 -m json.tool
# Unauthed approve should 401.
curl -s -o /tmp/u.json -w "approve unauthed HTTP=%{http_code}\n" -X POST "$BASE/api/factor-lab/proposals/1/approve"
cat /tmp/u.json
```
Expected: `200 {"proposals": []}` for the list call (no pending proposals yet in prod); `401 missing or malformed Authorization header` for the unauthed approve.

The frontend page itself is best smoke-tested manually in a browser (open `https://<frontend>/factor-lab`, verify the four sections render, click Propose if you have BYOK headers set in the session).

---

## Self-Review

**Spec coverage (Phase 3 spec § 5.8 + § 5.9):**
- T1: GET /proposals + POST approve/reject/rollback; approve writes extended_operators + factor.custom_expression + refreshes AST whitelist; rollback reverts via prior config_change_log row; operators stay registered.
- T2: TypeScript client mirrors Phase 2b evolution.ts shape.
- T3: Page with four sections + nav link; PendingFactorProposalsTable with new-operator collapsible + Approve/Reject; FactorHistoryTable with per-approved-row Rollback; ProposeButton with loading spinner + dormant pill.

**5 UX principles re-checked against tasks:**
- Intent alignment: page section order matches mental sequence (live expression -> diagnostic -> propose -> pending -> history).
- Cognitive load: 5-column pending table; operators collapsed by default; 3-color status badges.
- Visibility: spinner + dormant pill on Propose; per-row disable on Approve/Reject; refresh_error surfaced in approve response.
- Forgiveness: confirmation modal only for new-operator approvals; rollback per row; all 3 mutations reversible.
- Affordance: button labels match verbs; status badges = DB enum values; monospace expression with Copy.

**Anti-pattern guardrails (sedimented from 3a/3b/3c memory):**
- Silent exception: approve's `refresh_allowed_ops` failure goes into the response body as `refresh_error` (callers see it, not swallowed). Reject 404s on missing/decided rows (mirror 2b fix). The structured-response pattern matches the `/api/healthz/ast` precedent.
- Dual-entry: factor_lab router was registered in 3c-T5 in BOTH `app.py` and `api/index.py`; new routes on the same router inherit registration automatically. No new `_load(...)` needed. Verify via the existing `/api/_debug/load-errors` after deploy.
- Grep call chain (from [[grep-call-chain-for-duplicate-names]] memory): T3 mentions Sidebar.tsx grep before editing; the implementer must locate the real admin-nav file via grep, not infer from naming.

**Out of scope (closes Phase 3):**
- Per-user factor proposals (admin-tier only stays the spec contract).
- Multi-approval workflow (one admin click = applied; no review-by-second-admin gate).
- Operator unregistration / demote (admin lives with the operators they approved; removing them would break reproducibility of prior approved proposals).
- Iterative LLM refinement within a single propose call (each click = one round; the Karpathy-style overnight loop is not part of v1, per spec § 10).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-phase3d-ui-approval.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review, consistent with 3a / 3b / 3c.

**2. Inline Execution** — same-session batched execution.

Pick approach to proceed.
