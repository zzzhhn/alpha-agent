# Phase 2-pre: DB-Backed Engine Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a focused set of engine knobs runtime-configurable from the database (instead of hardcoded constants / env vars), so the Phase 2a proposer can propose changes and the Phase 2b approval can apply them, and so the operator can hand-tune knobs today with a journaled, rollback-able audit trail, all without a code deploy.

**Architecture:** A new `engine_config(key, value)` table holds the live value per knob. A small `config_store` module keeps a process-level cache (knobs are read in hot, pure, synchronous functions like `map_to_tier`, so a per-call DB read is not viable): `refresh_config(pool)` loads all rows into the cache (called at the top of cron handlers + request entry), and `get_config(key, default)` reads the cache synchronously, falling back to the hardcoded default when the cache is cold or the key is unset. Writes go through `set_config(pool, key, value, user_id, source)`, which upserts `engine_config` AND journals to the existing `config_change_log` (so 2b's rollback substrate is shared with 1b). Four knobs are rewired to read from config: rating tier thresholds, the no-trade band, the factor horizon mode, and the factor-acceptance IC threshold.

**Tech Stack:** Python 3.12, asyncpg, FastAPI, Postgres (Neon), pytest + pytest-postgresql (`applied_db` DSN → pool via `get_pool`), uv.

**Decisions locked (2026-05-22):** focused 4-knob subset (rating tier thresholds, no-trade band, factor horizon short/long, factor-acceptance IC threshold); signal inclusion + GEX band stay env/constant for now. The proposer (2a) and human-gated approval (2b) are separate plans built on this foundation.

---

## The 4 knobs (verified live) + config keys

| Config key | Default (current hardcoded/env value) | Read at | Consumer |
|---|---|---|---|
| `rating.tier_thresholds` | `{"buy":1.5,"ow":0.5,"hold":-0.5,"uw":-1.5}` | `alpha_agent/fusion/rating.py::map_to_tier` | rating of every composite (6 call sites) |
| `rating.no_trade_band` | `0.15` (env `ALPHA_TIER_BAND_Z`) | `rating.py::_resolve_band_width` | hysteresis band in `map_to_tier_with_band` |
| `factor.mode` | `"short"` (env `ALPHA_FACTOR_MODE`) | `alpha_agent/signals/factor.py` (expr selection) | which factor expression the fast cron computes |
| `signal.ic_accept_threshold` | `0.02` (`_IC_THRESHOLD` in `alpha_agent/agents/backtest.py`) | `agents/backtest.py` factor-acceptance check | whether a backtested factor is accepted |

NOTE (verify during Task 4/5): `_IC_THRESHOLD` in `ic_engine.py` is vestigial post-Phase-1b (the old weight rule that used it was removed); the LIVE consumer is `agents/backtest.py:54`. Rewire that one. Leave the dead `ic_engine.py` constant or delete it (your call, note it).

---

## File Structure

- `alpha_agent/storage/migrations/V014__engine_config.sql` (new): the `engine_config` table.
- `alpha_agent/config_store.py` (new): `DEFAULTS` dict, process cache, `refresh_config(pool)`, `get_config(key, default=None)`, `set_config(pool, key, value, user_id, source)`.
- `alpha_agent/fusion/rating.py` (modify): `map_to_tier` + `map_to_tier_with_band` + `_resolve_band_width` read from `get_config`.
- `alpha_agent/signals/factor.py` (modify): factor-expr selection reads `get_config("factor.mode", "short")`.
- `alpha_agent/agents/backtest.py` (modify): the IC-acceptance check reads `get_config("signal.ic_accept_threshold", 0.02)`.
- `alpha_agent/api/routes/cron_routes.py` + `api/cron/*` entry (modify): call `refresh_config(pool)` at the top of the cron handlers so the cache is warm in the lambda.
- Tests: `tests/storage/test_migration_v014.py`, `tests/test_config_store.py`, `tests/fusion/test_rating_configurable.py`.

---

### Task 1: V014 `engine_config` migration

**Files:**
- Create: `alpha_agent/storage/migrations/V014__engine_config.sql`
- Test: `tests/storage/test_migration_v014.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v014.py
import json

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_engine_config_upserts(pool):
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_by) VALUES ($1, $2::jsonb, 0) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        "rating.no_trade_band", json.dumps(0.15),
    )
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_by) VALUES ($1, $2::jsonb, 0) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        "rating.no_trade_band", json.dumps(0.20),
    )
    row = await pool.fetchrow("SELECT value FROM engine_config WHERE key = 'rating.no_trade_band'")
    assert json.loads(row["value"]) == pytest.approx(0.20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v014.py -v`
Expected: FAIL, `UndefinedTableError: relation "engine_config" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V014__engine_config.sql (2026-05-22)
--
-- Phase 2-pre: runtime-configurable engine knobs. One row per knob; value is
-- JSONB so a knob can hold a scalar (no_trade_band) or an object
-- (tier_thresholds). The live value lives here; the change history + rollback
-- journal stays in config_change_log (shared with the Phase 1b auto tier).
-- A missing key falls back to the hardcoded DEFAULTS in config_store.py.
CREATE TABLE IF NOT EXISTS engine_config (
    key text PRIMARY KEY,
    value jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by integer NOT NULL DEFAULT 0
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_migration_v014.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V014__engine_config.sql tests/storage/test_migration_v014.py
git commit -m "feat(db): V014 engine_config table"
```

---

### Task 2: `config_store` (cache + get/set + refresh)

**Files:**
- Create: `alpha_agent/config_store.py`
- Test: `tests/test_config_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_store.py
import pytest

from alpha_agent import config_store
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    config_store._CACHE.clear()  # isolate tests
    yield_done = True  # noqa: F841
    await close_pool()


def test_get_config_returns_default_when_cache_cold():
    config_store._CACHE.clear()
    assert config_store.get_config("rating.no_trade_band", 0.15) == 0.15
    # An unknown key with no default returns None.
    assert config_store.get_config("does.not.exist") is None


@pytest.mark.asyncio
async def test_set_then_refresh_then_get(pool):
    config_store._CACHE.clear()
    await config_store.set_config(pool, "rating.no_trade_band", 0.20, user_id=0, source="test")
    # Before refresh, cache may be stale; after refresh it reflects the DB.
    await config_store.refresh_config(pool)
    assert config_store.get_config("rating.no_trade_band", 0.15) == pytest.approx(0.20)
    # set_config also journaled the change to config_change_log.
    n = await pool.fetchval(
        "SELECT count(*) FROM config_change_log WHERE field = 'rating.no_trade_band'"
    )
    assert n >= 1


@pytest.mark.asyncio
async def test_object_valued_knob_roundtrips(pool):
    config_store._CACHE.clear()
    thresholds = {"buy": 1.4, "ow": 0.5, "hold": -0.5, "uw": -1.5}
    await config_store.set_config(pool, "rating.tier_thresholds", thresholds, user_id=0, source="test")
    await config_store.refresh_config(pool)
    assert config_store.get_config("rating.tier_thresholds", {})["buy"] == pytest.approx(1.4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_store.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'alpha_agent.config_store'`.

- [ ] **Step 3: Write `alpha_agent/config_store.py`**

```python
"""Runtime engine-config store (Phase 2-pre).

Knobs are read in hot, pure, synchronous functions (e.g. rating.map_to_tier),
so a per-call DB read is not viable. Instead a process-level cache is loaded
by refresh_config(pool) (called at the top of cron handlers / request entry),
and get_config(key, default) reads it synchronously. A cold cache or unset key
falls back to the caller-supplied default (the historic hardcoded value).

Writes go through set_config, which upserts engine_config AND journals the
change to config_change_log (the shared Phase 1b/2b rollback substrate).
"""
from __future__ import annotations

import json
from typing import Any

# Hardcoded defaults (the historic constant/env values). Used when the DB has
# no row for a key. Kept here so a fresh DB behaves exactly like pre-2-pre.
DEFAULTS: dict[str, Any] = {
    "rating.tier_thresholds": {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
    "rating.no_trade_band": 0.15,
    "factor.mode": "short",
    "signal.ic_accept_threshold": 0.02,
}

_CACHE: dict[str, Any] = {}


async def refresh_config(pool) -> None:
    """Load every engine_config row into the process cache. Call at the top of
    cron handlers and request-path entry so reads see the latest values."""
    rows = await pool.fetch("SELECT key, value FROM engine_config")
    fresh: dict[str, Any] = {}
    for r in rows:
        v = r["value"]
        fresh[r["key"]] = json.loads(v) if isinstance(v, str) else v
    _CACHE.clear()
    _CACHE.update(fresh)


def get_config(key: str, default: Any = None) -> Any:
    """Synchronous cache read. Falls back to the cached value, else the
    caller's default (the historic hardcoded value), else the DEFAULTS table."""
    if key in _CACHE:
        return _CACHE[key]
    if default is not None:
        return default
    return DEFAULTS.get(key)


async def set_config(pool, key: str, value: Any, user_id: int, source: str) -> None:
    """Upsert the live value + journal the change to config_change_log, then
    update the cache so the new value is visible in-process immediately."""
    old = await pool.fetchval("SELECT value FROM engine_config WHERE key = $1", key)
    await pool.execute(
        "INSERT INTO engine_config (key, value, updated_at, updated_by) "
        "VALUES ($1, $2::jsonb, now(), $3) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
        "updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by",
        key, json.dumps(value), user_id,
    )
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES ($1, $2, $3, $4, $5)",
        user_id, key,
        old if isinstance(old, str) else (json.dumps(old) if old is not None else None),
        json.dumps(value), source,
    )
    _CACHE[key] = value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_store.py -v`
Expected: PASS (3 tests). NOTE: the `pool` fixture above has a double-yield typo; write it as a normal single-yield fixture that clears `_CACHE` in teardown. Fix the fixture to: create pool, `yield p`, then in teardown `config_store._CACHE.clear()` + `await close_pool()`.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/config_store.py tests/test_config_store.py
git commit -m "feat(config): engine config store (cache + get/set + journal)"
```

---

### Task 3: Rewire rating thresholds + no-trade band

**Files:**
- Modify: `alpha_agent/fusion/rating.py`
- Test: `tests/fusion/test_rating_configurable.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/fusion/test_rating_configurable.py
import pytest

from alpha_agent import config_store
from alpha_agent.fusion.rating import map_to_tier


def test_map_to_tier_uses_default_thresholds():
    config_store._CACHE.clear()
    assert map_to_tier(2.0) == "BUY"     # > 1.5 default
    assert map_to_tier(0.0) == "HOLD"


def test_map_to_tier_honors_config_override():
    # Lower the BUY threshold to 1.0; composite 1.2 should now be BUY.
    config_store._CACHE.clear()
    config_store._CACHE["rating.tier_thresholds"] = {"buy": 1.0, "ow": 0.5, "hold": -0.5, "uw": -1.5}
    try:
        assert map_to_tier(1.2) == "BUY"   # 1.2 > 1.0 configured
    finally:
        config_store._CACHE.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fusion/test_rating_configurable.py -v`
Expected: FAIL on `test_map_to_tier_honors_config_override`, `map_to_tier` still uses the hardcoded 1.5 cutoff, so 1.2 maps to OW not BUY.

- [ ] **Step 3: Rewire `map_to_tier` + `_resolve_band_width`**

In `rating.py`, change `map_to_tier` to read thresholds from config (keep the exact same NaN/None → HOLD guard + comparison order):

```python
from alpha_agent.config_store import get_config

def map_to_tier(composite: float) -> Tier:
    if composite is None or (isinstance(composite, float) and math.isnan(composite)):
        return "HOLD"
    t = get_config("rating.tier_thresholds", {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5})
    if composite > t["buy"]:
        return "BUY"
    if composite > t["ow"]:
        return "OW"
    if composite >= t["hold"]:
        return "HOLD"
    if composite >= t["uw"]:
        return "UW"
    return "SELL"
```

And `_resolve_band_width` to read `get_config("rating.no_trade_band", <env-or-0.15>)`, keep the env var as the default arg so behavior is unchanged when no DB row exists, and keep the `0 <= band <= 0.5` clamp. Update `map_to_tier_with_band`'s band ranges to use the same configured thresholds `t` (currently it hardcodes 1.5/0.5/-0.5/-1.5 in its `bands` dict, read them from `get_config` too so band logic stays consistent with the tier cutoffs).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fusion/test_rating_configurable.py tests/ -k "rating or tier" -v`
Expected: PASS (new tests + no regression in existing rating tests, which run with a cold cache → defaults → unchanged behavior).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/fusion/rating.py tests/fusion/test_rating_configurable.py
git commit -m "feat(config): rating tier thresholds + no-trade band read from engine_config"
```

---

### Task 4: Rewire factor mode + IC-accept threshold

**Files:**
- Modify: `alpha_agent/signals/factor.py`, `alpha_agent/agents/backtest.py`
- Test: extend `tests/test_config_store.py` or add small per-module tests

- [ ] **Step 1: Write the failing tests**

Add a test that `factor.py`'s active-expression selection returns the LONG expression when `config_store._CACHE["factor.mode"] = "long"` and the SHORT one otherwise (READ factor.py first to find the exact selection function/variable, it currently reads `os.environ["ALPHA_FACTOR_MODE"]`; the test asserts the config override wins). Add a test that `agents/backtest.py`'s acceptance uses `get_config("signal.ic_accept_threshold", 0.02)` (construct a fake `bt_result` with `ic_mean` just above/below an overridden threshold and assert accept/reject flips).

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL, both still read the env var / hardcoded constant.

- [ ] **Step 3: Rewire**

- `factor.py`: replace the `os.environ.get("ALPHA_FACTOR_MODE", "short")` read at expression-selection time with `get_config("factor.mode", os.environ.get("ALPHA_FACTOR_MODE", "short"))` (env stays the default so nothing changes until a DB row is set). If the mode is read at module-import time (a module-level constant), refactor the selection into a function called per-computation so the config is read live, not frozen at import.
- `agents/backtest.py`: replace `_IC_THRESHOLD` in the acceptance comparison (line ~54) with `get_config("signal.ic_accept_threshold", 0.02)`. Confirm the vestigial `ic_engine.py::_IC_THRESHOLD` is unused post-1b (grep) and note it (delete or leave with a comment).

- [ ] **Step 4: Run tests + commit**

Run: `uv run pytest tests/ -k "factor or backtest or config" -v` (no regression).

```bash
git add alpha_agent/signals/factor.py alpha_agent/agents/backtest.py tests/test_config_store.py
git commit -m "feat(config): factor mode + IC-accept threshold read from engine_config"
```

---

### Task 5: Warm the cache on the live paths + admin set endpoint

**Files:**
- Modify: `alpha_agent/api/routes/cron_routes.py` (refresh at cron entry), `api/index.py` if needed
- Create: a thin `POST /api/admin/config` (set a knob) + `GET /api/admin/config` (list) in `alpha_agent/api/routes/admin.py` (it exists) for manual tuning + the 2b apply path
- Test: `tests/api/test_admin_config.py`

- [ ] **Step 1: Write the failing test**

Using the `client_with_db` fixture: POST `/api/admin/config` `{"key":"rating.no_trade_band","value":0.2}` → 200; GET `/api/admin/config` returns the row; assert `engine_config` has the row AND `config_change_log` journaled it. (READ `admin.py` + its existing auth/route style first; match it. If admin routes require auth, follow the existing admin-auth pattern in the test.)

- [ ] **Step 2: Run to verify it fails** (404, endpoints absent)

- [ ] **Step 3: Implement**

- In each cron handler that computes signals/ratings (`fast_intraday`, `slow_daily`, the IC backtest), call `await refresh_config(pool)` once near the top so the lambda's process cache is warm before any `map_to_tier` runs. (READ the handlers; add the single refresh call.)
- Add the admin endpoints to `admin.py`: `GET /api/admin/config` → `SELECT key,value FROM engine_config`; `POST /api/admin/config` body `{key, value}` → `await set_config(pool, key, value, user_id=<admin>, source="manual")`. Validate `key` against the known `DEFAULTS` keys (reject unknown keys). Match admin.py's existing auth.

- [ ] **Step 4: Verify + commit**

Run: `uv run pytest tests/api/test_admin_config.py -v` + `uv run python -c "from alpha_agent.api.app import create_app; app=create_app(); print('/api/admin/config' in [r.path for r in app.routes])"`.
CRITICAL: also enumerate any NEW router in BOTH `app.py::create_app` AND `api/index.py` (the dual-entry trap, a new router only in app.py 404s in prod). admin.py already exists + is enumerated, so adding routes to it needs no new enumeration; confirm.

```bash
git add alpha_agent/api/routes/cron_routes.py alpha_agent/api/routes/admin.py tests/api/test_admin_config.py
git commit -m "feat(config): warm config cache on cron entry + admin get/set endpoints"
```

- [ ] **Step 5: Apply V014 to prod + smoke (manual, after merge)**

```bash
uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv(); from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"
curl -s "https://alpha.bobbyzhong.com/api/admin/config" | head   # lists knobs (empty until set)
```

---

## Self-Review

**Spec coverage (the config-ification prerequisite for Phase 2):** the 4 focused knobs (rating tier thresholds, no-trade band, factor mode, IC-accept threshold) are made DB-configurable with hardcoded defaults preserved (Task 3/4), via a process-cache that pure sync functions read (Task 2), warmed on the live paths (Task 5), with every write journaled to `config_change_log` for 2b rollback. The migration is Task 1.

**Backward-compatibility invariant:** with an empty `engine_config` table (fresh DB / pre-set), `get_config(key, default)` returns the historic default, so every rewired function behaves byte-identically to today. Existing tests run with a cold cache → defaults → unchanged. This is the key safety property: 2-pre changes HOW values are read, not the values.

**Placeholder scan:** No TBD/TODO. Task 4's tests are described (read factor.py's selection fn, fake bt_result) rather than fully transcribed because the exact factor-selection symbol must be read first; the assertion intent is explicit. The Task 2 fixture double-yield typo is called out with the fix.

**Dual-entry reminder (CRITICAL):** Task 5 adds routes to the EXISTING `admin.py` router (already enumerated in both `app.py` and `api/index.py`), so no new enumeration is needed, but the task explicitly re-checks this, because a brand-new router would 404 in prod if only registered in `app.py` (the trap that bit watchlist and Phase 2c evolution).

**Out of scope:** signal inclusion (`_ACTIVE_SIGNALS`) + GEX regime band stay env/constant (deferred). The methodology proposer (2a) and approval queue (2b) are separate plans; this plan only makes the knobs settable + journaled (the proposer/approval reuse `set_config` + `config_change_log`).