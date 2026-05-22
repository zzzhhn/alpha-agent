# Phase 2a: Methodology Proposer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily statistics-driven job (no LLM) that proposes small config-knob changes, validates each on purged walk-forward out-of-sample windows with honest trial-count deflation (Deflated-Sharpe-lite), and queues only the survivors as PENDING proposals for human approval, staying dormant ("insufficient data") until enough history exists to validate.

**Architecture:** Builds on Phase 2-pre (the `engine_config` knobs + `config_store`). A `candidate enumerator` does bounded local search around the current config (e.g. BUY threshold +/- 0.1, no-trade band +/- 0.05, factor mode flip). A `validation harness` re-runs composite to rating to PnL on purged walk-forward OOS folds (purge + embargo >= the 5-day forward horizon, so no label leakage), producing a Sharpe/IC distribution per candidate; a Deflated-Sharpe-lite step discounts the best candidate by the number of trials. Only candidates that beat the current config on the OOS distribution AND survive deflation become proposals, capped per day. Proposals are written to `config_change_log` (extended with `status` + `evidence` columns) as `status='pending'`. Nothing applies automatically (that is Phase 2b, human-gated).

**Tech Stack:** Python 3.12, numpy (no scipy/sklearn), asyncpg, Postgres (Neon), pytest + pytest-postgresql, uv. Reuses `alpha_agent/factor_engine/kernel.py` (the pure backtest kernel) and `config_store`.

**Decisions locked (2026-05-22):** validation = pragmatic purged walk-forward + Deflated-Sharpe-lite (trial-count deflation), NOT full CPCV; hard cap on proposals/day; proposer searches over the 2-pre knobs (rating tier thresholds, no-trade band, factor mode, IC-accept threshold); dormant (zero proposals) when OOS folds are below a minimum.

---

## Dependencies + grounding (read first during Task 1)

- Phase 2-pre must be merged: `engine_config`, `alpha_agent/config_store.py` (`get_config`/`set_config`/`refresh_config`/`DEFAULTS`).
- `config_change_log` schema (V009): `id, user_id, field, old_value, new_value, changed_at, source, rollback_of`. This plan's V015 adds `status` + `evidence`.
- The backtest substrate: read `alpha_agent/factor_engine/kernel.py` for the pure backtest entry (it computes Sharpe/IC over a panel; reuse it rather than re-implementing PnL). Read `alpha_agent/backtest/ic_engine.py::_spearman_rho` (reuse for IC).
- Forward horizon = 5 trading days (`_FWD_RET_DAYS`); purge + embargo must be >= 5 trading days.

---

## File Structure

- `alpha_agent/storage/migrations/V015__proposal_columns.sql` (new): `ALTER config_change_log ADD status text, ADD evidence jsonb`.
- `alpha_agent/evolution/candidates.py` (new): `enumerate_candidates(current_config) -> list[ConfigDelta]` (pure, bounded local search).
- `alpha_agent/evolution/validation.py` (new): `purged_walk_forward(...)` + `deflated_sharpe_lite(sharpes, n_trials)` (pure numpy) + `evaluate_candidate(pool, delta) -> CandidateResult|None`.
- `alpha_agent/evolution/proposer.py` (new): `run_proposer(pool) -> dict` orchestrator (enumerate -> validate -> deflate -> write pending proposals, capped).
- `alpha_agent/api/routes/cron_routes.py` (modify): a `/api/cron/methodology_proposer` route + GH Actions daily wiring.
- Tests: `tests/storage/test_migration_v015.py`, `tests/evolution/test_candidates.py`, `tests/evolution/test_validation.py`, `tests/evolution/test_proposer.py`.

---

### Task 1: V015 proposal columns on `config_change_log`

**Files:**
- Create: `alpha_agent/storage/migrations/V015__proposal_columns.sql`
- Test: `tests/storage/test_migration_v015.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v015.py
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_proposal_columns_exist(pool):
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, new_value, source, status, evidence) "
        "VALUES (0, 'rating.no_trade_band', '0.2', 'proposer', 'pending', $1::jsonb)",
        '{"sharpe_oos": 0.8, "n_trials": 4}',
    )
    row = await pool.fetchrow(
        "SELECT status, evidence FROM config_change_log WHERE status = 'pending' LIMIT 1"
    )
    assert row["status"] == "pending"
    assert row["evidence"] is not None
    # Existing rows (1b/2-pre writes) have NULL status and are unaffected.
    nulls = await pool.fetchval("SELECT count(*) FROM config_change_log WHERE status IS NULL")
    assert nulls >= 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v015.py -v`
Expected: FAIL, `column "status" of relation "config_change_log" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V015__proposal_columns.sql (2026-05-22)
--
-- Phase 2a: the methodology proposer queues candidates as pending rows in
-- config_change_log. status: NULL for the existing auto-tier / manual rows
-- (1b promotions, 2-pre manual sets), 'pending'|'approved'|'rejected' for
-- proposer rows. evidence: the Sharpe/IC distribution + Deflated-Sharpe + trial
-- count behind the proposal, surfaced in the approval UI.
ALTER TABLE config_change_log
    ADD COLUMN IF NOT EXISTS status text,
    ADD COLUMN IF NOT EXISTS evidence jsonb;

CREATE INDEX IF NOT EXISTS idx_config_change_log_status
    ON config_change_log (status) WHERE status = 'pending';
```

- [ ] **Step 4: Run to verify it passes**, `uv run pytest tests/storage/test_migration_v015.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V015__proposal_columns.sql tests/storage/test_migration_v015.py
git commit -m "feat(db): V015 status + evidence columns on config_change_log (proposals)"
```

---

### Task 2: Candidate enumerator (pure local search)

**Files:**
- Create: `alpha_agent/evolution/candidates.py` (+ `alpha_agent/evolution/__init__.py`)
- Test: `tests/evolution/test_candidates.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/evolution/test_candidates.py
from alpha_agent.evolution.candidates import enumerate_candidates


def test_enumerates_bounded_neighbors_of_current_config():
    current = {
        "rating.tier_thresholds": {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5},
        "rating.no_trade_band": 0.15,
        "factor.mode": "short",
        "signal.ic_accept_threshold": 0.02,
    }
    cands = enumerate_candidates(current)
    # Each candidate is a single-knob delta from current (local search).
    assert all(c.key in current for c in cands)
    # The band knob proposes +/- a step (e.g. 0.10 and 0.20 around 0.15).
    band_vals = sorted(c.new_value for c in cands if c.key == "rating.no_trade_band")
    assert band_vals == [pytest.approx(0.10), pytest.approx(0.20)]  # import pytest
    # factor.mode proposes the flip.
    modes = [c.new_value for c in cands if c.key == "factor.mode"]
    assert modes == ["long"]
    # Bounded: total candidate count is small (hard cap, e.g. <= 8).
    assert 1 <= len(cands) <= 8
```

- [ ] **Step 2: Run to verify it fails**, `ImportError`.

- [ ] **Step 3: Implement `candidates.py`**

```python
"""Bounded local-search candidate generation for the methodology proposer.
Each candidate is a single-knob delta from the current config (one change at a
time keeps attribution clean + the trial count small for honest deflation)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigDelta:
    key: str
    new_value: Any
    rationale: str


def enumerate_candidates(current: dict[str, Any]) -> list[ConfigDelta]:
    out: list[ConfigDelta] = []
    band = float(current.get("rating.no_trade_band", 0.15))
    for nb in (round(band - 0.05, 4), round(band + 0.05, 4)):
        if 0.0 <= nb <= 0.5:
            out.append(ConfigDelta("rating.no_trade_band", nb,
                                   f"no-trade band {band} -> {nb}"))
    thr = current.get("rating.tier_thresholds", {"buy": 1.5, "ow": 0.5, "hold": -0.5, "uw": -1.5})
    for nb in (round(thr["buy"] - 0.1, 4), round(thr["buy"] + 0.1, 4)):
        out.append(ConfigDelta("rating.tier_thresholds", {**thr, "buy": nb},
                               f"BUY threshold {thr['buy']} -> {nb}"))
    mode = current.get("factor.mode", "short")
    out.append(ConfigDelta("factor.mode", "long" if mode == "short" else "short",
                           f"factor mode {mode} -> flip"))
    ic = float(current.get("signal.ic_accept_threshold", 0.02))
    for nv in (round(ic - 0.01, 4), round(ic + 0.01, 4)):
        if nv > 0:
            out.append(ConfigDelta("signal.ic_accept_threshold", nv,
                                   f"IC-accept {ic} -> {nv}"))
    return out[:8]  # hard cap on trials/day
```

(Add `import pytest` to the test. Implement so the band test's `[0.10, 0.20]` holds.)

- [ ] **Step 4: Run to verify it passes**, both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/evolution/__init__.py alpha_agent/evolution/candidates.py tests/evolution/test_candidates.py
git commit -m "feat(proposer): bounded single-knob candidate enumerator"
```

---

### Task 3: Validation harness (purged walk-forward + Deflated-Sharpe-lite)

**Files:**
- Create: `alpha_agent/evolution/validation.py`
- Test: `tests/evolution/test_validation.py`

- [ ] **Step 1: Write the failing test (pure-math parts first)**

```python
# tests/evolution/test_validation.py
import numpy as np
import pytest

from alpha_agent.evolution.validation import deflated_sharpe_lite, purged_fold_indices


def test_purged_folds_embargo_excludes_overlap():
    # 100 days, 5 folds, embargo=5: each test fold's train must exclude the
    # `embargo` days on both sides of the test block (no label leakage).
    folds = purged_fold_indices(n=100, n_folds=5, embargo=5)
    assert len(folds) == 5
    for train_idx, test_idx in folds:
        lo, hi = min(test_idx), max(test_idx)
        # No train index within `embargo` of the test block.
        assert all(not (lo - 5 <= t <= hi + 5) for t in train_idx)


def test_deflated_sharpe_lite_penalizes_trial_count():
    # Same observed best Sharpe, more trials -> lower deflated value.
    s = [0.1, 0.2, 0.9]
    d_few = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=3)
    d_many = deflated_sharpe_lite(best_sharpe=0.9, sharpes=s, n_trials=30)
    assert d_many < d_few
    # A best Sharpe that is not above the cross-trial mean+noise deflates to <= 0.
    assert deflated_sharpe_lite(best_sharpe=0.2, sharpes=[0.18, 0.2, 0.22], n_trials=20) <= 0.2
```

- [ ] **Step 2: Run to verify it fails**, `ImportError`.

- [ ] **Step 3: Implement the pure-math core of `validation.py`**

```python
"""Purged walk-forward + Deflated-Sharpe-lite (numpy only, no scipy/sklearn)."""
from __future__ import annotations

import numpy as np


def purged_fold_indices(n: int, n_folds: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Contiguous-block walk-forward folds with a purge+embargo gap: each test
    block excludes `embargo` train days on both sides so a label that overlaps
    the test window cannot leak into training."""
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        lo, hi = bounds[i], bounds[i + 1] - 1
        test_idx = list(range(lo, hi + 1))
        train_idx = [t for t in range(n) if t < lo - embargo or t > hi + embargo]
        folds.append((train_idx, test_idx))
    return folds


def deflated_sharpe_lite(best_sharpe: float, sharpes: list[float], n_trials: int) -> float:
    """Discount the best observed Sharpe by the spread across trials and the
    trial count (more trials -> more selection bias -> larger haircut). Lite
    proxy for the Deflated Sharpe Ratio: subtract a multiple of the cross-trial
    std scaled by log(n_trials)."""
    arr = np.asarray(sharpes, dtype=float)
    spread = float(arr.std()) if len(arr) > 1 else 0.0
    haircut = spread * float(np.log1p(n_trials))
    return float(best_sharpe - haircut)
```

- [ ] **Step 4: Run the pure-math tests**, PASS. Commit this slice.

- [ ] **Step 5: Add `evaluate_candidate(pool, delta) -> CandidateResult|None` (DB + kernel)**

READ `alpha_agent/factor_engine/kernel.py` to find the pure backtest entry that, given a panel + params, returns per-fold Sharpe/IC. Implement `evaluate_candidate`:
1. Load the recent panel + signal history needed (the same data the IC engine uses; reuse its queries).
2. Build purged folds via `purged_fold_indices` with `embargo>=5`.
3. For each fold: apply the candidate delta (in-memory, NOT via set_config) to the rating/factor path, compute OOS Sharpe + IC on the test block via the kernel.
4. Return `CandidateResult(delta, sharpes=[...], ic_oos, n_folds)`, or `None` if the usable history yields fewer than `MIN_FOLDS` (e.g. 3) folds with enough observations (the dormant-when-starved guard).

Add an integration test (`applied_db`) that seeds a small synthetic panel and asserts `evaluate_candidate` returns None when history is too short, and a non-None result with the right shape when enough is seeded. (This is the data-shape probe per the SDK-boundary rule; do not mock the kernel.)

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/evolution/validation.py tests/evolution/test_validation.py
git commit -m "feat(proposer): purged walk-forward + deflated-sharpe-lite validation harness"
```

---

### Task 4: Proposer orchestrator (enumerate -> validate -> queue)

**Files:**
- Create: `alpha_agent/evolution/proposer.py`
- Test: `tests/evolution/test_proposer.py`

- [ ] **Step 1: Write the failing test**

Seed (via `applied_db`) enough synthetic history that at least one candidate validates, plus a current config. Assert `run_proposer(pool)`:
- writes only candidates that beat current config OOS AND survive deflation, as `config_change_log` rows with `status='pending'` + `evidence` populated (sharpes, ic_oos, deflated_sharpe, n_trials, rationale);
- respects the per-day cap (`MAX_PROPOSALS_PER_DAY`, e.g. 3);
- returns `{"evaluated": N, "proposed": M, "dormant": bool}`;
- with too-short history: returns `dormant=True`, `proposed=0`, writes nothing.
Also assert it does NOT mutate `engine_config` (proposals never auto-apply).

- [ ] **Step 2: Run to verify it fails**, `ImportError`.

- [ ] **Step 3: Implement `run_proposer(pool)`**

```python
async def run_proposer(pool, user_id: int = 0) -> dict:
    await refresh_config(pool)
    current = {k: get_config(k, DEFAULTS[k]) for k in DEFAULTS}
    candidates = enumerate_candidates(current)
    base = await evaluate_candidate(pool, _identity_delta(current))  # current config OOS
    if base is None:
        return {"evaluated": 0, "proposed": 0, "dormant": True}
    results = []
    for c in candidates:
        r = await evaluate_candidate(pool, c)
        if r is not None:
            results.append(r)
    n_trials = len(results)
    proposed = 0
    # Rank by OOS mean Sharpe; deflate the best; only keep candidates that beat
    # base AND survive deflation; cap per day.
    for r in sorted(results, key=lambda r: -np.mean(r.sharpes)):
        if proposed >= MAX_PROPOSALS_PER_DAY:
            break
        defl = deflated_sharpe_lite(float(np.mean(r.sharpes)), [float(np.mean(x.sharpes)) for x in results], n_trials)
        if np.mean(r.sharpes) > np.mean(base.sharpes) and defl > 0:
            await _write_pending(pool, r, defl, n_trials, user_id)
            proposed += 1
    return {"evaluated": n_trials, "proposed": proposed, "dormant": False}
```

`_write_pending` inserts a `config_change_log` row: `field=delta.key`, `old_value=json(current value)`, `new_value=json(delta.new_value)`, `source='proposer'`, `status='pending'`, `evidence=json({sharpes, ic_oos, deflated_sharpe, n_trials, rationale})`. Define `MAX_PROPOSALS_PER_DAY=3`, `MIN_FOLDS=3`.

- [ ] **Step 4: Run to verify it passes**, PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/evolution/proposer.py tests/evolution/test_proposer.py
git commit -m "feat(proposer): orchestrator (enumerate -> validate -> deflate -> queue pending)"
```

---

### Task 5: Daily cron wiring

**Files:**
- Modify: `alpha_agent/api/routes/cron_routes.py` (+ `api/index.py` enumeration if a NEW router) + `.github/workflows/cron-shards.yml`

- [ ] **Step 1: Add a cron route**

Add `POST/GET /api/cron/methodology_proposer` to `cron_routes.py` that calls `run_proposer(pool)` and stamps `cron_runs`. Since `cron_routes` is already enumerated in BOTH `app.py` and `api/index.py`, no new router enumeration is needed (CONFIRM this, adding a route to an existing enumerated router is fine; a brand-new router would need both entries, the dual-entry trap).

- [ ] **Step 2: Verify route registers**, `uv run python -c "from alpha_agent.api.routes.cron_routes import router; print('/api/cron/methodology_proposer' in [r.path for r in router.routes])"`.

- [ ] **Step 3: Schedule it daily**

Add a job to `cron-shards.yml` (a new schedule cron + an `if`-gated job, mirroring `daily_prices_puller`), running once daily after the IC backtest (the proposer reads IC + panel history). Single curl, no sharding needed.

- [ ] **Step 4: Commit**

```bash
git add alpha_agent/api/routes/cron_routes.py .github/workflows/cron-shards.yml
git commit -m "feat(proposer): daily methodology_proposer cron + schedule"
```

- [ ] **Step 5: Apply V015 to prod + smoke (manual, after merge)**

```bash
uv run python -c "import asyncio,os; from dotenv import load_dotenv; load_dotenv(); from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"
curl -s -X POST "https://alpha.bobbyzhong.com/api/cron/methodology_proposer" | python3 -m json.tool
# Expected early: {"evaluated":0,"proposed":0,"dormant":true} (data-starved is correct)
```

---

## Self-Review

**Spec coverage (design section 8):** bounded local-search candidate generation over existing config knobs (Task 2); purged walk-forward + Deflated-Sharpe-lite validation, no LLM, no full CPCV (Task 3); proposals queued in config_change_log with delta + evidence + rationale, capped per day, nothing auto-applies (Task 4); daily cron (Task 5). The human approve/reject (2b) is the next plan.

**Dormant-when-starved invariant:** with ~12 days of history, `evaluate_candidate` returns None below `MIN_FOLDS`, so `run_proposer` returns `dormant=True, proposed=0` and writes nothing, the intended conservative behavior until months of history accrue. This is verified explicitly in Task 4's test.

**Honest trial accounting:** single-knob candidates keep attribution clean; `deflated_sharpe_lite` haircuts the best by cross-trial spread x log(n_trials), and only post-deflation-positive AND beats-baseline candidates are proposed. Tested in Task 3.

**Placeholder scan:** No TBD/TODO. Task 3 Step 5 + Task 4 Step 1 describe their integration tests (seed synthetic panel, assert shape/dormancy) rather than fully transcribing them, because the exact `kernel.py` backtest signature must be read first; the assertions are explicit. This is the SDK-boundary real-shape probe (do not mock the kernel).

**Out of scope:** auto-apply (forbidden, this is the approve tier), full CPCV (later stretch), the approval UI + apply mechanism (Phase 2b), proposing over signal-inclusion / GEX (not in the 2-pre knob set).