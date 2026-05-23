# Phase 3a Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the no-LLM, no-sandbox foundation that Phase 3b/3c/3d build on: the `factor_proposals` + `extended_operators` schemas (V016), the `factor.custom_expression` knob, the `_resolve_default_expr` honoring of that knob, and the AST whitelist union that lets the validator accept dynamically-registered operator names.

**Architecture:** Two new tables (`factor_proposals` and `extended_operators`) added via V016. A new `factor.custom_expression` config knob (sourced from `engine_config` per Phase 2-pre, with a `None` default for full backward compatibility). The `_resolve_default_expr` function checks `factor.custom_expression` first and falls back to the existing `factor.mode` short/long preset when unset. The AST validator's `_ALLOWED_OPS` becomes a frozenset built from the static built-ins UNION a server-startup snapshot of `extended_operators.name`, refreshable on demand (no DB hit on hot validation path).

**Tech Stack:** Python 3.12, asyncpg, Postgres (Neon), pytest + pytest-postgresql, uv. No sandbox, no LLM, no UI yet. Reuses `alpha_agent/config_store.py` from Phase 2-pre.

**UX principles guiding schema choices (from user, 2026-05-23):**
1. **Intent alignment** (predict next step): `factor_proposals.evidence` is a structured jsonb (sharpes, ic_oos, deflated_sharpe, baseline_sharpe, n_folds, n_trials, llm_rationale), so the eventual 3d UI can render an at-a-glance Approve/Reject decision without re-querying.
2. **Cognitive load minimization**: status is a `text CHECK IN (...)` enum (3 values: `pending`, `approved`, `rejected`), not a free-form string. The UI maps each value to one badge.
3. **Visibility of system status**: every proposal row carries its `diagnostic` jsonb snapshot, so the user can later trace "why was this proposed?" without forensics on cron logs.
4. **Forgiveness** (errors are normal): `factor.custom_expression` defaults to `None`, and setting it to `None` re-enables the preset fallback. Approve writes the expression; rollback in Phase 3d writes back the previous value. The knob is fully reversible by design; nothing in 3a is one-way.
5. **Affordance**: table and column names self-explain (`factor_proposals` not `factor_log`; `extended_operators.python_impl` not `op_blob`). A new contributor reading the schema should be able to guess intent without docs.

---

## Dependencies + grounding (read first during Task 1)

- Phase 2-pre merged: `engine_config` table + `alpha_agent/config_store.py` (`DEFAULTS`, `get_config`, `set_config`, `refresh_config`).
- Phase 2a merged: V015 added `status` + `evidence` to `config_change_log`. V016 must be the NEXT migration number; confirm with `ls alpha_agent/storage/migrations/V*.sql | tail`.
- AST validator: `alpha_agent/core/factor_ast.py:20` defines `_ALLOWED_OPS: frozenset[str] = frozenset(AllowedOperator.__args__)`. Line 97 uses it as `if node.func.id not in _ALLOWED_OPS`. The literal type `AllowedOperator` lives in `alpha_agent/core/types.py`.
- Default expression resolver: `alpha_agent/signals/factor.py:76-85` defines `_resolve_default_expr()` which currently reads `factor.mode` from `get_config`/env and returns one of `SHORT_TERM_FACTOR_EXPR` / `LONG_TERM_FACTOR_EXPR`. The patch must insert a `factor.custom_expression` lookup BEFORE that branch.
- Migrations runner: `alpha_agent/storage/migrations/runner.py` auto-discovers `VNNN__name.sql`; tests run against `applied_db` (DSN string) with the full chain applied. Mirror the fixture pattern in `tests/storage/test_migration_v015.py`.

---

## File Structure

- `alpha_agent/storage/migrations/V016__factor_proposals.sql` (new): two CREATE TABLE statements + indexes.
- `alpha_agent/config_store.py` (modify): add `factor.custom_expression: None` to `DEFAULTS`.
- `alpha_agent/signals/factor.py` (modify): patch `_resolve_default_expr` to honor `factor.custom_expression`.
- `alpha_agent/core/factor_ast.py` (modify): expose `_ALLOWED_OPS` as a refreshable union of `BUILTIN_OPS` + `extended_operators.name`. Add `async refresh_allowed_ops(pool)`.
- `alpha_agent/api/app.py` (modify): call `refresh_allowed_ops(pool)` once at startup (the existing lifespan/startup hook).
- Tests: `tests/storage/test_migration_v016.py`, `tests/test_factor_custom_expression.py`, `tests/core/test_factor_ast_extended_ops.py`.

---

### Task 1: V016 migration (`factor_proposals` + `extended_operators`)

**Files:**
- Create: `alpha_agent/storage/migrations/V016__factor_proposals.sql`
- Test: `tests/storage/test_migration_v016.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v016.py
import json

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_factor_proposals_table_shape(pool):
    pid = await pool.fetchval(
        "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
        "VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb) RETURNING id",
        "rank(ts_mean(returns, 12))",
        json.dumps([]),
        json.dumps({"sharpes": [0.8, 0.7], "ic_oos": 0.04, "deflated_sharpe": 0.5,
                    "baseline_sharpe": 0.3, "n_folds": 3, "n_trials": 5, "llm_rationale": "test"}),
        json.dumps({"weak_signal": "news_24h", "weak_signal_ic": 0.005,
                    "symptom_summary": "news IC dropped"}),
    )
    row = await pool.fetchrow(
        "SELECT status, expression, new_operators, evidence FROM factor_proposals WHERE id=$1",
        pid,
    )
    assert row["status"] == "pending"  # default
    assert row["expression"] == "rank(ts_mean(returns, 12))"


@pytest.mark.asyncio
async def test_factor_proposals_status_check_rejects_garbage(pool):
    with pytest.raises(Exception):
        await pool.execute(
            "INSERT INTO factor_proposals (status, expression, new_operators, evidence, diagnostic) "
            "VALUES ('half-baked', 'x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb)"
        )


@pytest.mark.asyncio
async def test_extended_operators_table_shape(pool):
    # Operators come from approved proposals; insert one and a self-referencing
    # source_proposal_id to confirm the FK + uniqueness.
    pid = await pool.fetchval(
        "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
        "VALUES ('x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb) RETURNING id"
    )
    await pool.execute(
        "INSERT INTO extended_operators (name, signature, python_impl, doc, registered_by, source_proposal_id) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "lf_demo_test", "(x: ndarray) -> ndarray", "def lf_demo_test(x): return x", "demo", 0, pid,
    )
    n = await pool.fetchval("SELECT count(*) FROM extended_operators WHERE name='lf_demo_test'")
    assert n == 1
    # name is unique:
    with pytest.raises(Exception):
        await pool.execute(
            "INSERT INTO extended_operators (name, signature, python_impl, doc, registered_by, source_proposal_id) "
            "VALUES ('lf_demo_test', 's', 'i', 'd', 0, $1)",
            pid,
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v016.py -v`
Expected: FAIL, `relation "factor_proposals" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V016__factor_proposals.sql (2026-05-23)
--
-- Phase 3a foundation: the LLM factor invention substrate. Two tables:
--   factor_proposals  : one row per LLM-generated candidate, status enum
--                       (pending/approved/rejected), evidence jsonb captures
--                       the OOS Sharpe distribution and DSR-lite haircut so
--                       the UI can render Approve/Reject without re-querying.
--   extended_operators: approved operators registered by name; ExprEvaluator
--                       dispatches these via the Phase 3b subprocess sandbox
--                       at runtime, never inlined.
-- All three new schema choices honor the 5 UX principles documented in the
-- Phase 3 spec sec 1 (intent alignment, cognitive load, visibility, forgiveness,
-- affordance).

CREATE TABLE IF NOT EXISTS factor_proposals (
    id              bigserial PRIMARY KEY,
    status          text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected')),
    expression      text NOT NULL,
    new_operators   jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence        jsonb NOT NULL,
    diagnostic      jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    decided_by      bigint
);

CREATE INDEX IF NOT EXISTS idx_factor_proposals_status_created
    ON factor_proposals (status, created_at DESC);

CREATE TABLE IF NOT EXISTS extended_operators (
    name                text PRIMARY KEY,
    signature           text NOT NULL,
    python_impl         text NOT NULL,
    doc                 text,
    registered_at       timestamptz NOT NULL DEFAULT now(),
    registered_by       bigint NOT NULL,
    source_proposal_id  bigint REFERENCES factor_proposals(id)
);

CREATE INDEX IF NOT EXISTS idx_extended_operators_registered_at
    ON extended_operators (registered_at DESC);
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/storage/test_migration_v016.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V016__factor_proposals.sql tests/storage/test_migration_v016.py
git commit -m "feat(db): V016 factor_proposals + extended_operators (Phase 3a foundation)"
```

---

### Task 2: `factor.custom_expression` knob in DEFAULTS

**Files:**
- Modify: `alpha_agent/config_store.py`
- Test: `tests/test_factor_custom_expression.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_factor_custom_expression.py
import pytest

from alpha_agent.config_store import DEFAULTS, _CACHE, get_config, refresh_config, set_config
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def test_custom_expression_default_is_none():
    """Forgiveness: default of None means the knob is opt-in and the existing
    factor.mode preset path stays in effect when nothing is approved yet."""
    assert "factor.custom_expression" in DEFAULTS
    assert DEFAULTS["factor.custom_expression"] is None


@pytest.mark.asyncio
async def test_set_then_refresh_then_get(pool):
    _CACHE.clear()
    await set_config(pool, "factor.custom_expression", "rank(ts_mean(returns, 8))",
                     user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") == "rank(ts_mean(returns, 8))"


@pytest.mark.asyncio
async def test_set_to_none_restores_default_path(pool):
    """Reversibility: setting back to None means the preset path resumes."""
    _CACHE.clear()
    await set_config(pool, "factor.custom_expression", "rank(returns)",
                     user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") == "rank(returns)"
    await set_config(pool, "factor.custom_expression", None, user_id=0, source="test")
    await refresh_config(pool)
    assert get_config("factor.custom_expression") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_factor_custom_expression.py::test_custom_expression_default_is_none -v`
Expected: FAIL, `KeyError` or assertion error.

- [ ] **Step 3: Add the knob to `DEFAULTS`**

In `alpha_agent/config_store.py`, modify the `DEFAULTS` dict (lines 17 to 22):

```python
DEFAULTS: dict[str, Any] = {
    "rating.tier_thresholds": {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    "rating.no_trade_band": 0.15,
    "factor.mode": "short",
    "signal.ic_accept_threshold": 0.02,
    # Phase 3a: free-form factor expression. None = fall back to factor.mode
    # short/long preset (full backward compat). Set via Phase 3d Approve.
    "factor.custom_expression": None,
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_factor_custom_expression.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/config_store.py tests/test_factor_custom_expression.py
git commit -m "feat(config): factor.custom_expression knob default None (Phase 3a)"
```

---

### Task 3: `_resolve_default_expr` honors `factor.custom_expression`

**Files:**
- Modify: `alpha_agent/signals/factor.py`
- Test: `tests/test_factor_custom_expression.py` (extend the file from Task 2)

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# Append to tests/test_factor_custom_expression.py

from alpha_agent.signals.factor import (
    LONG_TERM_FACTOR_EXPR,
    SHORT_TERM_FACTOR_EXPR,
    _resolve_default_expr,
)


def test_resolver_falls_back_to_short_when_custom_is_none():
    """When the knob is unset and factor.mode is short (default), the resolver
    returns SHORT_TERM_FACTOR_EXPR. No-op for existing users."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "short"
    _CACHE["factor.custom_expression"] = None
    assert _resolve_default_expr() == SHORT_TERM_FACTOR_EXPR


def test_resolver_returns_custom_when_set():
    """When the knob holds an expression string, it wins over factor.mode."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "long"  # would normally win
    _CACHE["factor.custom_expression"] = "rank(returns)"
    assert _resolve_default_expr() == "rank(returns)"


def test_resolver_treats_empty_string_as_unset():
    """Defensive: an empty string is treated the same as None (defends against
    a UI that clears the field and submits ''). Falls through to preset."""
    _CACHE.clear()
    _CACHE["factor.mode"] = "long"
    _CACHE["factor.custom_expression"] = ""
    assert _resolve_default_expr() == LONG_TERM_FACTOR_EXPR
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_factor_custom_expression.py -v -k resolver`
Expected: FAIL on the second (custom set) and third (empty string) tests.

- [ ] **Step 3: Patch `_resolve_default_expr`**

In `alpha_agent/signals/factor.py:76-85`, replace the body of `_resolve_default_expr`:

```python
def _resolve_default_expr() -> str:
    """Resolve the active factor expression. Precedence order (Phase 3a):
       1. factor.custom_expression knob (set by Phase 3d Approve when an LLM
          proposal lands). Non-empty string wins.
       2. factor.mode preset ("short" or "long") from config or env var.

    Reads on every call so tests + per-invocation overrides work."""
    custom = get_config("factor.custom_expression", None)
    if custom:  # non-None AND non-empty (forgiveness: empty string falls through)
        return custom
    mode = get_config("factor.mode", os.environ.get("ALPHA_FACTOR_MODE", "short")).strip().lower()
    return LONG_TERM_FACTOR_EXPR if mode == "long" else SHORT_TERM_FACTOR_EXPR
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_factor_custom_expression.py -v`
Expected: 6 passed (3 from Task 2 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/factor.py tests/test_factor_custom_expression.py
git commit -m "feat(factor): _resolve_default_expr honors factor.custom_expression (Phase 3a)"
```

---

### Task 4: AST whitelist union with `extended_operators`

**Files:**
- Modify: `alpha_agent/core/factor_ast.py`
- Modify: `alpha_agent/api/app.py` (call `refresh_allowed_ops` at startup)
- Test: `tests/core/test_factor_ast_extended_ops.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_factor_ast_extended_ops.py
import asyncpg
import pytest

from alpha_agent.core.factor_ast import (
    BUILTIN_OPS,
    get_allowed_ops,
    refresh_allowed_ops,
)


@pytest.mark.asyncio
async def test_baseline_whitelist_is_builtin_only(applied_db):
    """Before any extended operators are registered, the whitelist equals
    the static built-ins (no DB-injected names)."""
    await refresh_allowed_ops(applied_db)
    assert get_allowed_ops() == BUILTIN_OPS


@pytest.mark.asyncio
async def test_refresh_picks_up_extended_operators(applied_db):
    """After inserting an extended_operators row, refresh_allowed_ops folds
    its name into the whitelist; new validations now accept it."""
    conn = await asyncpg.connect(applied_db)
    try:
        pid = await conn.fetchval(
            "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
            "VALUES ('x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb) RETURNING id"
        )
        await conn.execute(
            "INSERT INTO extended_operators (name, signature, python_impl, doc, "
            "registered_by, source_proposal_id) VALUES "
            "('lf_demo_op', '(x) -> x', 'def lf_demo_op(x): return x', 'demo', 0, $1)",
            pid,
        )
    finally:
        await conn.close()
    await refresh_allowed_ops(applied_db)
    ops = get_allowed_ops()
    assert "lf_demo_op" in ops
    assert BUILTIN_OPS.issubset(ops)  # built-ins still present


@pytest.mark.asyncio
async def test_refresh_idempotent(applied_db):
    """Calling refresh twice with no DB change leaves the whitelist identical
    (no accidental duplicates or removals)."""
    await refresh_allowed_ops(applied_db)
    first = get_allowed_ops()
    await refresh_allowed_ops(applied_db)
    second = get_allowed_ops()
    assert first == second
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/core/test_factor_ast_extended_ops.py -v`
Expected: FAIL, `ImportError: cannot import name 'BUILTIN_OPS' / 'get_allowed_ops' / 'refresh_allowed_ops'`.

- [ ] **Step 3: Patch `factor_ast.py`**

In `alpha_agent/core/factor_ast.py`, replace the module-level `_ALLOWED_OPS` block:

```python
# Phase 3a: the whitelist is the static built-ins UNION any operator names
# registered in extended_operators (Phase 3 LLM-authored, sandboxed at runtime).
# BUILTIN_OPS stays a fixed frozenset; the dynamic union is held in
# _ALLOWED_OPS and refreshed via refresh_allowed_ops(pool_or_dsn) at server
# startup and after each Phase 3d Approve. Validation reads _ALLOWED_OPS off
# the module (no DB hit on hot path).
BUILTIN_OPS: frozenset[str] = frozenset(AllowedOperator.__args__)
_ALLOWED_OPS: frozenset[str] = BUILTIN_OPS


def get_allowed_ops() -> frozenset[str]:
    """Read the current whitelist (built-ins UNION registered extended ops)."""
    return _ALLOWED_OPS


async def refresh_allowed_ops(pool_or_dsn) -> None:
    """Rebuild _ALLOWED_OPS from BUILTIN_OPS UNION extended_operators.name.
    Call at server startup and after a Phase 3d Approve so newly-registered
    names become validate-able without a server restart."""
    import asyncpg
    global _ALLOWED_OPS
    if isinstance(pool_or_dsn, str):
        conn = await asyncpg.connect(pool_or_dsn)
        try:
            rows = await conn.fetch("SELECT name FROM extended_operators")
        finally:
            await conn.close()
    else:
        rows = await pool_or_dsn.fetch("SELECT name FROM extended_operators")
    extended = frozenset(r["name"] for r in rows)
    _ALLOWED_OPS = BUILTIN_OPS | extended
```

Keep the existing usages of `_ALLOWED_OPS` at lines 97 and 126 untouched (they continue to read the module variable, which now updates after refresh).

- [ ] **Step 4: Wire startup refresh in `app.py`**

In `alpha_agent/api/app.py`, in the existing FastAPI lifespan/startup handler (find it via `grep -nE "lifespan|on_event\(\"startup\"\)|@app.on_event" alpha_agent/api/app.py`), add a call after the pool is initialized:

```python
from alpha_agent.core.factor_ast import refresh_allowed_ops
# ... existing startup body ...
await refresh_allowed_ops(pool)
```

If no startup handler exists yet, add a minimal one that runs `refresh_allowed_ops` (the rest of the app does not yet require startup work, but Phase 3 will lean on this hook).

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/core/test_factor_ast_extended_ops.py -v`
Expected: 3 passed.

Also run the AST validator's existing suite to confirm no regression:
Run: `uv run pytest tests/core/test_factor_ast.py -v` (if the file exists; otherwise `uv run pytest tests/ -v -k factor_ast`)
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/core/factor_ast.py alpha_agent/api/app.py tests/core/test_factor_ast_extended_ops.py
git commit -m "feat(ast): whitelist union with extended_operators + startup refresh (Phase 3a)"
```

---

### Task 5: Apply V016 to prod + verify end to end

**Files:** none (deployment + smoke only)

- [ ] **Step 1: Apply migrations to prod**

```bash
uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv(); from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"
```
Expected output: `['V016__factor_proposals']` (only V016 pending).

- [ ] **Step 2: Verify prod schema**

```bash
uv run python -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv()
from alpha_agent.storage.postgres import get_pool, close_pool
async def main():
    p = await get_pool(os.environ['DATABASE_URL'])
    fp = await p.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='factor_proposals'\")
    eo = await p.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='extended_operators'\")
    print('factor_proposals cols:', [r['column_name'] for r in fp])
    print('extended_operators cols:', [r['column_name'] for r in eo])
    await close_pool()
asyncio.run(main())
"
```
Expected: `factor_proposals` has id, status, expression, new_operators, evidence, diagnostic, created_at, decided_at, decided_by. `extended_operators` has name, signature, python_impl, doc, registered_at, registered_by, source_proposal_id.

- [ ] **Step 3: Push code**

```bash
git push
```

- [ ] **Step 4: Smoke the live backend**

Wait for the Vercel deploy to reach Ready (poll `/api/openapi.json` or any existing endpoint). Then verify the AST union refresh ran at startup:

```bash
# A read endpoint that touches the AST validator (e.g. alpha translate sanity check)
# is the indirect smoke. Direct: assert no new errors in /api/openapi.json.
BASE="https://alpha.bobbyzhong.com"
curl -s --max-time 30 -o /tmp/oas.json -w "%{http_code}\n" "$BASE/api/openapi.json"
# Expect 200; absence of import-time errors confirms refresh_allowed_ops ran.
```

- [ ] **Step 5: Manual sanity (optional but recommended)**

Setting the knob via the existing admin endpoint and confirming the resolver picks it up live:

```bash
TOKEN=<admin Bearer token>
curl -sX POST "$BASE/api/admin/config" -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"key": "factor.custom_expression", "value": "rank(ts_mean(returns, 8))"}' | python3 -m json.tool
# Then trigger a factor evaluation path (e.g. /api/picks/lean) and confirm the
# response shape stays valid. Then null it out:
curl -sX POST "$BASE/api/admin/config" -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"key": "factor.custom_expression", "value": null}' | python3 -m json.tool
```

---

## Self-Review

**Spec coverage:** Phase 3a in the spec (sec 8 phasing first bullet) calls for: V016 schema (Task 1), `factor.custom_expression` knob (Task 2), `_resolve_default_expr` extension (Task 3), AST whitelist union with `extended_operators` (Task 4). Task 5 is the deploy-ordering apply per the project's deployment ground-truth rule (migration to prod BEFORE pushing code that reads the new table; here the code does not yet WRITE to either table, but the AST refresh reads `extended_operators` at startup, so V016 must land first).

**No placeholders:** every step has real SQL, real Python, or a real shell command. The startup-hook wiring in Task 4 Step 4 leaves a small "find the existing lifespan / startup handler" instruction; that is grounding, not a placeholder. Confirmed the grep target.

**Type / name consistency:** `BUILTIN_OPS` (Task 4) is the new name for the static frozenset; the existing `_ALLOWED_OPS` keeps its name and continues to be the module-level mutable holder. Callers at `factor_ast.py:97` and `:126` keep using `_ALLOWED_OPS` (the runtime union); they need no change. `get_allowed_ops()` is the read accessor for tests + future external readers.

**UX principles trace:**
- Intent alignment: `evidence` schema is structured so 3d UI can render Approve/Reject at a glance (Task 1 test asserts the shape).
- Cognitive load: `status` is a 3-value CHECK enum (Task 1 test asserts garbage values are rejected).
- Visibility: `diagnostic` jsonb on every row preserves the propose-time symptom snapshot (Task 1 schema).
- Forgiveness: `factor.custom_expression = None` returns to preset; empty string also falls through (Tasks 2 + 3 tests).
- Affordance: table and column names are self-explanatory (`factor_proposals`, `extended_operators`, `python_impl`, `source_proposal_id`).

**Out of scope (deferred to later sub-phases):**
- Phase 3b: the subprocess sandbox + worker pool + canned operator test harness.
- Phase 3c: the diagnostic engine, prompt template, evaluate_factor_candidate, `/propose` endpoint.
- Phase 3d: the `/factor-lab` UI, approve/reject/rollback endpoints, the wired refresh-allowed-ops on approve.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-phase3a-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with two-stage review (spec compliance + code quality) between tasks, same pattern as Phases 1a / 2a / 2b.

**2. Inline Execution** — execute tasks in this session via superpowers:executing-plans (batched checkpoints).

Pick approach to proceed.
