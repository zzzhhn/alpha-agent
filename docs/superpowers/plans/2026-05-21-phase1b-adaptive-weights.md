# Phase 1b: Hardened Adaptive Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw `mean(IC) * normalize` weight rule with a hardened EWMA-ICIR adaptive weighting that moves slowly, caps each change, floors instead of hard-zeroing on a single bad window, and promotes candidate weights to live only after a shadow window proves they do not degrade the composite IC against a frozen baseline (with auto-rollback if live later degrades).

**Architecture:** A new pure module `alpha_agent/backtest/adaptive_weights.py` holds the math (EWMA-ICIR, change-cap clamp, floor/hard-drop). A DB-aware orchestrator `apply_adaptive_weights(pool)` computes candidate weights from `signal_ic_history`, writes them as `status='shadow'` rows in `signal_weight_current`, backtests the candidate vs live composite IC over a trailing window, increments a shadow streak, and promotes (copy shadow → live, journal to `config_change_log`) once the streak clears 5 trading days. A frozen-baseline check auto-rolls-back live weights if their composite IC degrades. `run_monthly_ic_backtest` is rewired to call `apply_adaptive_weights` instead of the inline rule. `combine.load_weights` is filtered to `status='live'` so shadow rows never leak into live fusion.

**Tech Stack:** Python 3.12, asyncpg, numpy, Postgres (Neon), pytest + pytest-postgresql (`applied_db` DSN fixture → build a pool via `get_pool`), uv for running.

**Decisions locked (2026-05-21):** EWMA half-life 30 trading days, daily update; change cap 15% per update; auto-rollback metric = composite IC vs frozen baseline; shadow promotion window = 5 trading days.

---

## Existing code this builds on (already live as of Phase 1a)

- `alpha_agent/backtest/ic_engine.py`:
  - `compute_walk_forward_ic(pool, signal_name, window_days) -> tuple[float,int]|None` (reads `daily_prices` via `LEAD(close,5)`).
  - `run_monthly_ic_backtest(pool) -> int`, writes `signal_ic_history` rows then applies the OLD weight rule (`min(IC)<0.02 → 0`; else `mean(IC)*_DEFAULT_NORMALIZE`) to `signal_weight_current`. Phase 1b replaces only the weight-application half.
  - Constants: `_ACTIVE_SIGNALS` (11 signals), `_WINDOWS=(30,60,90)`, `_IC_THRESHOLD=0.02`, `_MIN_OBS=10`.
- `alpha_agent/fusion/combine.py::load_weights(pool)`, `SELECT signal_name, weight FROM signal_weight_current` over ALL rows; empty → `DEFAULT_WEIGHTS`. MUST be filtered to live.
- Schemas:
  - `signal_weight_current(signal_name text PK, weight numeric(6,4), last_updated timestamptz, reason text)`.
  - `signal_ic_history(signal_name, window_days, ic numeric(8,5), n_observations, computed_at, PK(signal_name,window_days,computed_at))`.
  - `config_change_log(id BIGSERIAL PK, user_id int, field text, old_value text, new_value text, changed_at timestamptz, source text, rollback_of bigint→config_change_log.id)`.
- Test fixture: `applied_db` (from `tests/storage/conftest.py`) is a DSN STRING; build a pool via `get_pool(applied_db)`.

---

## File Structure

- `alpha_agent/storage/migrations/V012__adaptive_weight_shadow.sql` (new): add `status`, `consecutive_bad_windows`, `shadow_streak` to `signal_weight_current`; widen PK to `(signal_name, status)`.
- `alpha_agent/backtest/adaptive_weights.py` (new): pure math (`compute_ewma_icir`, `apply_change_cap`, `apply_floor_or_drop`) + the DB orchestrator `apply_adaptive_weights(pool)` + the composite-IC backtest helper `composite_ic(pool, weights, window_days)`.
- `alpha_agent/backtest/ic_engine.py` (modify): replace the inline weight rule in `run_monthly_ic_backtest` with a call to `apply_adaptive_weights(pool)`.
- `alpha_agent/fusion/combine.py` (modify): `load_weights` filters `WHERE status='live'`.
- Tests: `tests/storage/test_migration_v012.py`, `tests/backtest/test_adaptive_weights_math.py`, `tests/backtest/test_composite_ic.py`, `tests/backtest/test_adaptive_weights_orchestration.py`, `tests/fusion/test_load_weights_live_only.py`.

---

### Task 1: V012 migration, shadow columns + widened PK

**Files:**
- Create: `alpha_agent/storage/migrations/V012__adaptive_weight_shadow.sql`
- Test: `tests/storage/test_migration_v012.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v012.py
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_signal_weight_current_supports_live_and_shadow(pool):
    # A live + a shadow row for the SAME signal must coexist (PK widened to
    # (signal_name, status)). New columns default sanely.
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.10, now(), 'ic_above_threshold', 'live')"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.12, now(), 'shadow_candidate', 'shadow')"
    )
    rows = await pool.fetch(
        "SELECT status, weight, consecutive_bad_windows, shadow_streak "
        "FROM signal_weight_current WHERE signal_name='news' ORDER BY status"
    )
    assert {r["status"] for r in rows} == {"live", "shadow"}
    # Defaults present and zero.
    for r in rows:
        assert r["consecutive_bad_windows"] == 0
        assert r["shadow_streak"] == 0


@pytest.mark.asyncio
async def test_existing_rows_become_live(pool):
    # Insert WITHOUT status → must default to 'live' (back-compat with the
    # Phase 1a writer that knew no status column).
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason) "
        "VALUES ('macro', 0.07, now(), 'ic_above_threshold')"
    )
    status = await pool.fetchval(
        "SELECT status FROM signal_weight_current WHERE signal_name='macro'"
    )
    assert status == "live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v012.py -v`
Expected: FAIL, inserting a second row for the same `signal_name` violates the existing single-column PK (`duplicate key value violates unique constraint`), and/or `column "status" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V012__adaptive_weight_shadow.sql (2026-05-21)
--
-- Phase 1b shadow weighting. signal_weight_current must hold a 'live' row
-- (consumed by fusion.load_weights) AND a 'shadow' candidate row per signal,
-- so the PK widens from (signal_name) to (signal_name, status). Existing
-- rows default to status='live' so the Phase 1a writer and load_weights keep
-- working unchanged. consecutive_bad_windows drives the diversification
-- floor's hard-drop-after-N rule; shadow_streak drives the 5-day promotion.
ALTER TABLE signal_weight_current
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS consecutive_bad_windows integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS shadow_streak integer NOT NULL DEFAULT 0;

-- Widen the primary key to (signal_name, status). The old PK name is the
-- table-derived default; drop by that name then re-add the composite.
ALTER TABLE signal_weight_current
    DROP CONSTRAINT IF EXISTS signal_weight_current_pkey;
ALTER TABLE signal_weight_current
    ADD PRIMARY KEY (signal_name, status);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_migration_v012.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V012__adaptive_weight_shadow.sql tests/storage/test_migration_v012.py
git commit -m "feat(db): V012 shadow status + streak columns on signal_weight_current"
```

---

### Task 2: EWMA-ICIR pure math

**Files:**
- Create: `alpha_agent/backtest/adaptive_weights.py`
- Test: `tests/backtest/test_adaptive_weights_math.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_adaptive_weights_math.py
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import compute_ewma_icir


def _series(ics, start=None):
    """Build [(date, ic), ...] one trading day apart, oldest first."""
    start = start or (date.today() - timedelta(days=len(ics)))
    return [(start + timedelta(days=i), ic) for i, ic in enumerate(ics)]


def test_constant_series_has_zero_std_returns_none():
    # std == 0 -> ICIR undefined -> None (no risk-adjusted signal).
    assert compute_ewma_icir(_series([0.1, 0.1, 0.1]), half_life_days=30) is None


def test_single_point_returns_none():
    assert compute_ewma_icir(_series([0.1]), half_life_days=30) is None


def test_equal_weight_limit_matches_plain_mean_over_std():
    # half_life huge -> lambda ~ 1 -> equal weights -> plain (population) mean/std.
    # ic = [0.0, 0.1, 0.2]: mean=0.1, pop var=0.006667, std=0.081650, icir=1.2247.
    icir = compute_ewma_icir(_series([0.0, 0.1, 0.2]), half_life_days=1e9)
    assert icir == pytest.approx(1.2247, rel=1e-3)


def test_recent_points_dominate_with_short_half_life():
    # Recent ICs negative, old positive. A short half-life weights the recent
    # (negative) end, so ICIR must be negative.
    icir = compute_ewma_icir(_series([0.3, 0.2, -0.2, -0.3]), half_life_days=2)
    assert icir is not None and icir < 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_adaptive_weights_math.py -v`
Expected: FAIL, `ModuleNotFoundError`/`ImportError: cannot import name 'compute_ewma_icir'`.

- [ ] **Step 3: Write the implementation**

```python
# alpha_agent/backtest/adaptive_weights.py
"""Phase 1b hardened adaptive weighting.

Pure math (EWMA-ICIR, change-cap, floor/hard-drop) plus a DB orchestrator
that writes shadow candidates, backtests them against the live baseline, and
promotes/rolls-back via config_change_log. Replaces the raw mean(IC) rule.
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np

# Tuning constants (Phase 1b decisions 2026-05-21).
HALF_LIFE_DAYS: float = 30.0    # slow EWMA: weights track stable predictive power
CHANGE_CAP_FRAC: float = 0.15   # a weight moves <= 15% of its reference per update
CAP_MIN_REF: float = 0.05       # reference floor so a 0-weight signal can re-grow
WEIGHT_FLOOR: float = 0.02      # diversification floor: a bad window shrinks here
MAX_BAD_WINDOWS: int = 3        # hard-drop to 0 only after this many consecutive bads
ICIR_NORMALIZE: float = 0.10    # scales positive ICIR into the familiar weight range
SHADOW_PROMOTE_STREAK: int = 5  # trading days a candidate must hold before promotion


def compute_ewma_icir(
    points: list[tuple[date | datetime, float]],
    half_life_days: float = HALF_LIFE_DAYS,
) -> float | None:
    """Exponentially-weighted IC information ratio = EWMA-mean(IC) / EWMA-std(IC).

    `points` is (timestamp, ic) for one signal+window in any order. Returns
    None if fewer than 2 points or the weighted std is ~0 (no risk-adjusted
    signal). Newer points get exponentially more weight (half-life in days).
    """
    if len(points) < 2:
        return None
    pts = sorted(points, key=lambda p: p[0])
    latest = pts[-1][0]
    lam = 0.5 ** (1.0 / half_life_days)
    ws, ics = [], []
    for ts, ic in pts:
        age = (latest - ts).days
        ws.append(lam ** age)
        ics.append(float(ic))
    w = np.array(ws)
    x = np.array(ics)
    wsum = w.sum()
    mean = float((w * x).sum() / wsum)
    var = float((w * (x - mean) ** 2).sum() / wsum)
    std = var ** 0.5
    if std < 1e-9:
        return None
    return mean / std
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_adaptive_weights_math.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/adaptive_weights.py tests/backtest/test_adaptive_weights_math.py
git commit -m "feat(weights): EWMA-ICIR pure computation"
```

---

### Task 3: change-cap + diversification floor (pure)

**Files:**
- Modify: `alpha_agent/backtest/adaptive_weights.py` (append two functions)
- Test: `tests/backtest/test_adaptive_weights_math.py` (extend)

- [ ] **Step 1: Write the failing test (append to the existing test file)**

```python
# append to tests/backtest/test_adaptive_weights_math.py
from alpha_agent.backtest.adaptive_weights import (  # noqa: E402
    apply_change_cap,
    apply_floor_or_drop,
)


def test_change_cap_clamps_upward_move():
    # current=0.10, cap=0.15 -> max_step = 0.15 * max(0.10, 0.05) = 0.015.
    assert apply_change_cap(0.10, 0.50, cap_frac=0.15) == pytest.approx(0.115)


def test_change_cap_clamps_downward_move():
    assert apply_change_cap(0.10, 0.0, cap_frac=0.15) == pytest.approx(0.085)


def test_change_cap_lets_dropped_signal_re_grow_slowly():
    # current=0 -> reference is CAP_MIN_REF=0.05 -> max_step = 0.15*0.05 = 0.0075.
    assert apply_change_cap(0.0, 0.30, cap_frac=0.15) == pytest.approx(0.0075)


def test_floor_shrinks_on_single_bad_window_not_zero():
    # icir <= 0 is a bad window; with cb below the max, weight shrinks to the
    # floor (not a hard zero) and the bad counter increments.
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.0, icir=-0.3, consecutive_bad=0, floor=0.02, max_bad=3
    )
    assert w == pytest.approx(0.02) and cb == 1 and dropped is False


def test_hard_drop_after_max_consecutive_bad():
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.0, icir=-0.1, consecutive_bad=2, floor=0.02, max_bad=3
    )
    assert w == 0.0 and cb == 3 and dropped is True


def test_good_window_resets_counter_and_keeps_target():
    w, cb, dropped = apply_floor_or_drop(
        raw_target=0.18, icir=1.2, consecutive_bad=2, floor=0.02, max_bad=3
    )
    assert w == pytest.approx(0.18) and cb == 0 and dropped is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_adaptive_weights_math.py -v`
Expected: FAIL, `ImportError: cannot import name 'apply_change_cap'`.

- [ ] **Step 3: Append the implementation to `adaptive_weights.py`**

```python
def apply_change_cap(
    current: float, target: float, cap_frac: float = CHANGE_CAP_FRAC
) -> float:
    """Clamp `target` so it moves at most `cap_frac` of the reference weight
    away from `current`. The reference is max(|current|, CAP_MIN_REF) so a
    dropped (0-weight) signal can still re-grow slowly instead of being stuck."""
    max_step = cap_frac * max(abs(current), CAP_MIN_REF)
    lo, hi = current - max_step, current + max_step
    return float(min(max(target, lo), hi))


def apply_floor_or_drop(
    raw_target: float,
    icir: float | None,
    consecutive_bad: int,
    floor: float = WEIGHT_FLOOR,
    max_bad: int = MAX_BAD_WINDOWS,
) -> tuple[float, int, bool]:
    """Diversification floor with hard-drop hysteresis.

    A bad window (icir is None or <= 0) shrinks the signal toward `floor`
    rather than to a hard zero, incrementing the consecutive-bad counter; only
    after `max_bad` consecutive bad windows does the weight hard-drop to 0. A
    good window (icir > 0) keeps the positive raw target and resets the counter.
    Returns (weight, new_consecutive_bad, dropped).
    """
    bad = icir is None or icir <= 0
    if not bad:
        return float(raw_target), 0, False
    cb = consecutive_bad + 1
    if cb >= max_bad:
        return 0.0, cb, True
    return float(floor), cb, False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_adaptive_weights_math.py -v`
Expected: PASS (all 10 tests in the file).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/adaptive_weights.py tests/backtest/test_adaptive_weights_math.py
git commit -m "feat(weights): change-cap clamp + diversification floor with hard-drop hysteresis"
```

---

### Task 4: `load_weights` reads live rows only

**Files:**
- Modify: `alpha_agent/fusion/combine.py` (the `load_weights` SQL)
- Test: `tests/fusion/test_load_weights_live_only.py` (new)

**Context:** `load_weights` currently does `SELECT signal_name, weight FROM signal_weight_current` over ALL rows. After V012 there can be a `shadow` row per signal; if it leaks into live fusion the composite is wrong. `tests/fusion/conftest.py` re-exports `applied_db` from `tests.storage.conftest`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fusion/test_load_weights_live_only.py
import pytest

from alpha_agent.fusion.combine import load_weights
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_load_weights_ignores_shadow_rows(pool):
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.10, now(), 'live', 'live')"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current (signal_name, weight, last_updated, reason, status) "
        "VALUES ('news', 0.99, now(), 'shadow_candidate', 'shadow')"
    )
    weights = await load_weights(pool)
    assert weights["news"] == pytest.approx(0.10)  # NOT the 0.99 shadow
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fusion/test_load_weights_live_only.py -v`
Expected: FAIL, without the filter, the two rows collapse and the shadow 0.99 can win (dict overwrite), so the assert sees 0.99.

- [ ] **Step 3: Add the filter**

In `alpha_agent/fusion/combine.py::load_weights`, change the query to:

```python
    rows = await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status = 'live'"
    )
```

Update the docstring line to note shadow rows are excluded.

- [ ] **Step 4: Run test + the existing fusion suite**

Run: `uv run pytest tests/fusion/test_load_weights_live_only.py tests/fusion/ -v`
Expected: PASS (new test + no regression in existing fusion tests, which seed only live-equivalent rows).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/fusion/combine.py tests/fusion/test_load_weights_live_only.py
git commit -m "fix(fusion): load_weights reads status='live' only (shadow must not leak)"
```

---

### Task 5: composite-IC backtest helper

**Files:**
- Modify: `alpha_agent/backtest/adaptive_weights.py` (append `composite_ic`)
- Test: `tests/backtest/test_composite_ic.py` (new)

**Context:** Promotion/rollback compares the composite IC produced by one weight vector vs another. `composite_ic` computes, over recent (ticker, as_of) points, the weighted-sum composite z (using the given weights over the breakdown), then the Spearman IC of that composite against the 5-trading-day forward return from `daily_prices`. Reuses `_spearman_rho` and `_MIN_OBS` from `ic_engine`.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_composite_ic.py
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import composite_ic
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed(pool, ticker, as_of, z_a, z_b, fwd_pct):
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker, date, composite, breakdown, fetched_at) "
        "VALUES ($1,$2::date,0.0,$3::jsonb,now()) "
        "ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
        ticker, as_of,
        json.dumps({"breakdown": [
            {"signal": "siga", "z": z_a},
            {"signal": "sigb", "z": z_b},
        ]}),
    )
    closes = [100, 100, 100, 100, 100, 100 * (1 + fwd_pct)]
    for i, c in enumerate(closes):
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, as_of + timedelta(days=i), c,
        )


@pytest.mark.asyncio
async def test_composite_ic_rewards_the_return_driving_signal(pool):
    # siga z drives the forward return monotonically; sigb is noise (zero z).
    base = date.today() - timedelta(days=40)
    for k in range(12):
        za = (k - 5.5) / 6.0
        await _seed(pool, f"T{k:02d}", base, z_a=za, z_b=0.0, fwd_pct=za * 0.1)
    ic_a = await composite_ic(pool, {"siga": 1.0, "sigb": 0.0}, window_days=90)
    ic_b = await composite_ic(pool, {"siga": 0.0, "sigb": 1.0}, window_days=90)
    assert ic_a is not None and ic_a > 0.9      # tracks the driver -> high IC
    assert ic_b is None or abs(ic_b) < 0.3      # pure noise -> ~0 / undefined


@pytest.mark.asyncio
async def test_composite_ic_none_below_min_obs(pool):
    base = date.today() - timedelta(days=40)
    await _seed(pool, "ONLY", base, z_a=0.5, z_b=0.0, fwd_pct=0.05)
    assert await composite_ic(pool, {"siga": 1.0}, window_days=90) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_composite_ic.py -v`
Expected: FAIL, `ImportError: cannot import name 'composite_ic'`.

- [ ] **Step 3: Append `composite_ic` to `adaptive_weights.py`**

```python
from collections import defaultdict
from datetime import UTC, timedelta

from alpha_agent.backtest.ic_engine import _MIN_OBS, _spearman_rho


async def composite_ic(
    pool, weights: dict[str, float], window_days: int, fwd_days: int = 5
) -> float | None:
    """Spearman IC of the weighted-sum composite signal vs the forward
    `fwd_days`-trading-day return, over recent (ticker, as_of) points.

    The composite per (ticker, as_of) is sum(weights[signal] * z) across that
    row's breakdown; the forward return comes from daily_prices via the same
    LEAD(close, 5) the per-signal IC uses. Returns None below _MIN_OBS points
    or if Spearman is degenerate.
    """
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    fwd_cutoff = (now - timedelta(days=fwd_days)).date()
    rows = await pool.fetch(
        """
        WITH sig AS (
            SELECT f.ticker, f.date AS as_of,
                   elem->>'signal' AS signal_name,
                   (elem->>'z')::double precision AS z
            FROM daily_signals_fast f
            CROSS JOIN LATERAL jsonb_array_elements(f.breakdown->'breakdown') AS elem
            WHERE f.date >= $1 AND f.date <= $2 AND (elem->>'z') IS NOT NULL
        ),
        fwd AS (
            SELECT ticker, date, close AS ce,
                   LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS cx
            FROM daily_prices
        )
        SELECT s.ticker, s.as_of, s.signal_name, s.z,
               (fwd.cx / fwd.ce - 1)::double precision AS fwd_5d
        FROM sig s
        JOIN fwd ON fwd.ticker = s.ticker AND fwd.date = s.as_of
        WHERE fwd.ce > 0 AND fwd.cx IS NOT NULL
        """,
        window_start, fwd_cutoff,
    )
    comp: dict[tuple, float] = defaultdict(float)
    fwd_ret: dict[tuple, float] = {}
    for r in rows:
        key = (r["ticker"], r["as_of"])
        comp[key] += weights.get(r["signal_name"], 0.0) * float(r["z"])
        fwd_ret[key] = float(r["fwd_5d"])
    if len(comp) < _MIN_OBS:
        return None
    keys = list(comp)
    rho = _spearman_rho([comp[k] for k in keys], [fwd_ret[k] for k in keys])
    if rho is None or np.isnan(rho):
        return None
    return float(rho)
```

(Place the imports at the top of the module with the existing imports; shown inline here for locality.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_composite_ic.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/adaptive_weights.py tests/backtest/test_composite_ic.py
git commit -m "feat(weights): composite-IC backtest helper for shadow vs live comparison"
```

---

### Task 6: orchestrator, candidate → shadow → promote on streak

**Files:**
- Modify: `alpha_agent/backtest/adaptive_weights.py` (append helpers + `apply_adaptive_weights`)
- Test: `tests/backtest/test_adaptive_weights_orchestration.py` (new)

**Context:** `apply_adaptive_weights` is the daily replacement for the old weight rule. It computes a candidate weight per signal from `signal_ic_history` (EWMA-ICIR → floor/drop → change-cap), writes it as the `shadow` row, then compares the shadow vs live composite IC. On non-degradation it increments every shadow row's streak and, once the minimum streak reaches `SHADOW_PROMOTE_STREAK` (5), promotes shadow → live (journaling to `config_change_log`). On a cold start (no live rows yet) it seeds live directly. Auto-rollback (Task 7) runs first each invocation.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_adaptive_weights_orchestration.py
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest.adaptive_weights import apply_adaptive_weights
from alpha_agent.storage.postgres import close_pool, get_pool

SIGNALS = ("siga", "sigb")


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_ic(pool, signal, window, ics, start):
    for i, ic in enumerate(ics):
        await pool.execute(
            "INSERT INTO signal_ic_history (signal_name, window_days, ic, n_observations, computed_at) "
            "VALUES ($1,$2,$3,50,$4) ON CONFLICT DO NOTHING",
            signal, window, ic, datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i),
        )


async def _seed_market(pool):
    # composite-IC backtest needs daily_signals_fast + daily_prices to exist;
    # seed a small monotone panel so composite_ic is computable (>= _MIN_OBS).
    base = date.today() - timedelta(days=40)
    for k in range(12):
        za = (k - 5.5) / 6.0
        await pool.execute(
            "INSERT INTO daily_signals_fast (ticker,date,composite,breakdown,fetched_at) "
            "VALUES ($1,$2::date,0.0,$3::jsonb,now()) ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
            f"T{k:02d}", base,
            json.dumps({"breakdown": [{"signal": "siga", "z": za}, {"signal": "sigb", "z": 0.0}]}),
        )
        closes = [100, 100, 100, 100, 100, 100 * (1 + za * 0.1)]
        for i, c in enumerate(closes):
            await pool.execute(
                "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
                "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
                f"T{k:02d}", base + timedelta(days=i), c,
            )


@pytest.mark.asyncio
async def test_cold_start_seeds_live_from_candidate(pool):
    start = date.today() - timedelta(days=10)
    # siga has stable positive IC (good ICIR); sigb noisy around zero.
    await _seed_ic(pool, "siga", 30, [0.10, 0.12, 0.11, 0.13, 0.12], start)
    await _seed_ic(pool, "sigb", 30, [0.01, -0.01, 0.0, 0.02, -0.02], start)
    await _seed_market(pool)
    res = await apply_adaptive_weights(pool, SIGNALS)
    assert res["promoted"] is True  # cold start seeds live immediately
    live = await pool.fetch("SELECT signal_name, weight FROM signal_weight_current WHERE status='live'")
    by = {r["signal_name"]: float(r["weight"]) for r in live}
    assert by["siga"] > by["sigb"]  # stable-IC signal gets more weight


@pytest.mark.asyncio
async def test_shadow_does_not_become_live_until_streak(pool):
    start = date.today() - timedelta(days=10)
    await _seed_ic(pool, "siga", 30, [0.10, 0.12, 0.11, 0.13, 0.12], start)
    await _seed_ic(pool, "sigb", 30, [0.05, 0.06, 0.05, 0.06, 0.05], start)
    await _seed_market(pool)
    # First call cold-starts live. Second call onward writes shadow; live must
    # not change until the streak reaches SHADOW_PROMOTE_STREAK.
    await apply_adaptive_weights(pool, SIGNALS)
    live_before = await pool.fetchval(
        "SELECT weight FROM signal_weight_current WHERE signal_name='siga' AND status='live'"
    )
    res = await apply_adaptive_weights(pool, SIGNALS)  # streak now 1, < 5
    assert res["promoted"] is False
    live_after = await pool.fetchval(
        "SELECT weight FROM signal_weight_current WHERE signal_name='siga' AND status='live'"
    )
    assert live_after == pytest.approx(float(live_before))  # live untouched
    shadow_exists = await pool.fetchval(
        "SELECT count(*) FROM signal_weight_current WHERE signal_name='siga' AND status='shadow'"
    )
    assert shadow_exists == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_adaptive_weights_orchestration.py -v`
Expected: FAIL, `ImportError: cannot import name 'apply_adaptive_weights'`.

- [ ] **Step 3: Append helpers + `apply_adaptive_weights` to `adaptive_weights.py`**

```python
import json

DEGRADE_TOL: float = 0.05  # live composite IC may dip this far below baseline before rollback


async def _gather_icir(pool, signal_name: str, windows=(30, 60, 90)) -> float | None:
    """Mean of per-window EWMA-ICIR over signal_ic_history; None if no window
    has >= 2 points (insufficient history for a risk ratio)."""
    icirs = []
    for w in windows:
        rows = await pool.fetch(
            "SELECT computed_at, ic FROM signal_ic_history "
            "WHERE signal_name=$1 AND window_days=$2 ORDER BY computed_at",
            signal_name, w,
        )
        v = compute_ewma_icir([(r["computed_at"], float(r["ic"])) for r in rows])
        if v is not None:
            icirs.append(v)
    return float(np.mean(icirs)) if icirs else None


async def _weights_by_status(pool, status: str) -> dict[str, float]:
    rows = await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status=$1", status
    )
    return {r["signal_name"]: float(r["weight"]) for r in rows}


async def _promote(pool, weights: dict[str, float], baseline_ic, now, reason: str) -> None:
    """Copy candidate weights into the live rows and journal the change so a
    later degradation can roll back to the prior live weights."""
    prev = await _weights_by_status(pool, "live")
    for sig, w in weights.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason) "
            "VALUES ($1,'live',$2,$3,$4) "
            "ON CONFLICT (signal_name, status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, reason=EXCLUDED.reason",
            sig, w, now, reason,
        )
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0, 'signal_weights', $1, $2, $3)",
        json.dumps(prev),
        json.dumps({"weights": weights, "baseline_ic": baseline_ic}),
        reason,
    )


async def apply_adaptive_weights(pool, active_signals) -> dict:
    """Daily adaptive-weight step: rollback check, candidate -> shadow, then
    promote shadow -> live once it holds non-degrading for SHADOW_PROMOTE_STREAK
    days. On a cold start (no live rows) the candidate seeds live directly."""
    now = datetime.now(UTC)
    rolled_back = await _maybe_rollback(pool)  # Task 7

    for sig in active_signals:
        icir = await _gather_icir(pool, sig)
        raw_target = max(icir, 0.0) * ICIR_NORMALIZE if icir is not None else 0.0
        live = await pool.fetchrow(
            "SELECT weight, consecutive_bad_windows FROM signal_weight_current "
            "WHERE signal_name=$1 AND status='live'",
            sig,
        )
        cur_w = float(live["weight"]) if live else 0.0
        cur_cb = int(live["consecutive_bad_windows"]) if live else 0
        floored, new_cb, _dropped = apply_floor_or_drop(raw_target, icir, cur_cb)
        capped = apply_change_cap(cur_w, floored)
        await pool.execute(
            "INSERT INTO signal_weight_current "
            "(signal_name, status, weight, last_updated, reason, consecutive_bad_windows, shadow_streak) "
            "VALUES ($1,'shadow',$2,$3,'shadow_candidate',$4, "
            "COALESCE((SELECT shadow_streak FROM signal_weight_current WHERE signal_name=$1 AND status='shadow'),0)) "
            "ON CONFLICT (signal_name, status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, "
            "consecutive_bad_windows=EXCLUDED.consecutive_bad_windows",
            sig, capped, now, new_cb,
        )

    live_w = await _weights_by_status(pool, "live")
    shadow_w = await _weights_by_status(pool, "shadow")
    if not live_w:
        await _promote(pool, shadow_w, baseline_ic=None, now=now, reason="cold_start_seed")
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
        return {"promoted": True, "reason": "cold_start", "rolled_back": rolled_back}

    ic_live = await composite_ic(pool, live_w, 90)
    ic_shadow = await composite_ic(pool, shadow_w, 90)
    promoted = False
    if ic_shadow is not None and (ic_live is None or ic_shadow >= ic_live):
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=shadow_streak+1 WHERE status='shadow'")
        streak = await pool.fetchval("SELECT min(shadow_streak) FROM signal_weight_current WHERE status='shadow'")
        if streak is not None and streak >= SHADOW_PROMOTE_STREAK:
            await _promote(pool, shadow_w, baseline_ic=ic_shadow, now=now, reason="auto_promote")
            await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
            promoted = True
    else:
        await pool.execute("UPDATE signal_weight_current SET shadow_streak=0 WHERE status='shadow'")
    return {"promoted": promoted, "ic_live": ic_live, "ic_shadow": ic_shadow, "rolled_back": rolled_back}
```

NOTE: `apply_adaptive_weights` calls `_maybe_rollback`, which Task 7 implements. To keep this task green in isolation, add a temporary stub `async def _maybe_rollback(pool): return False` at the bottom now; Task 7 replaces the stub body. (The stub is the one allowed forward-reference; Task 7's first step is to replace it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_adaptive_weights_orchestration.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/adaptive_weights.py tests/backtest/test_adaptive_weights_orchestration.py
git commit -m "feat(weights): shadow-candidate orchestrator with 5-day promotion streak"
```

---

### Task 7: auto-rollback against the frozen baseline

**Files:**
- Modify: `alpha_agent/backtest/adaptive_weights.py` (replace the `_maybe_rollback` stub)
- Test: `tests/backtest/test_adaptive_weights_orchestration.py` (extend)

**Context:** Each invocation, before computing new candidates, `_maybe_rollback` checks whether the current live weights' composite IC has degraded more than `DEGRADE_TOL` (0.05) below the `baseline_ic` recorded at the last promotion. If so it restores the prior live weights (the promotion's `old_value`) and journals a `rollback_of` row in `config_change_log`.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/backtest/test_adaptive_weights_orchestration.py
from alpha_agent.backtest.adaptive_weights import _maybe_rollback  # noqa: E402


async def _set_live(pool, weights):
    for sig, w in weights.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name,status,weight,last_updated,reason) "
            "VALUES ($1,'live',$2,now(),'seed') "
            "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight",
            sig, w,
        )


@pytest.mark.asyncio
async def test_rollback_fires_when_live_ic_degrades_below_baseline(pool):
    await _seed_market(pool)  # siga drives the return; sigb is noise
    # Live currently weights ONLY the noise signal -> low composite IC.
    await _set_live(pool, {"siga": 0.0, "sigb": 0.20})
    # A prior promotion claimed baseline_ic=0.95, old_value = the good weights.
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0,'signal_weights',$1,$2,'auto_promote')",
        json.dumps({"siga": 0.20, "sigb": 0.0}),
        json.dumps({"weights": {"siga": 0.0, "sigb": 0.20}, "baseline_ic": 0.95}),
    )
    rolled = await _maybe_rollback(pool)
    assert rolled is True
    live = {r["signal_name"]: float(r["weight"]) for r in await pool.fetch(
        "SELECT signal_name, weight FROM signal_weight_current WHERE status='live'")}
    assert live["siga"] == pytest.approx(0.20)  # restored to the good weights
    journ = await pool.fetchrow(
        "SELECT rollback_of, source FROM config_change_log WHERE source='auto_rollback'")
    assert journ is not None and journ["rollback_of"] is not None


@pytest.mark.asyncio
async def test_no_rollback_within_tolerance(pool):
    await _seed_market(pool)
    await _set_live(pool, {"siga": 0.20, "sigb": 0.0})  # good weights -> high IC
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
        "VALUES (0,'signal_weights',$1,$2,'auto_promote')",
        json.dumps({"siga": 0.10, "sigb": 0.0}),
        json.dumps({"weights": {"siga": 0.20, "sigb": 0.0}, "baseline_ic": 0.95}),
    )
    assert await _maybe_rollback(pool) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_adaptive_weights_orchestration.py -v`
Expected: FAIL, the stub `_maybe_rollback` always returns False, so `test_rollback_fires...` fails its `assert rolled is True`.

- [ ] **Step 3: Replace the `_maybe_rollback` stub with the real body**

```python
async def _maybe_rollback(pool) -> bool:
    """If the current live composite IC has fallen more than DEGRADE_TOL below
    the baseline_ic recorded at the last promotion, restore that promotion's
    prior weights and journal a rollback_of row. Cold-start seeds (baseline_ic
    is None) are never rolled back."""
    row = await pool.fetchrow(
        """
        SELECT id, old_value, new_value FROM config_change_log
        WHERE field = 'signal_weights' AND source IN ('auto_promote', 'cold_start_seed')
          AND id NOT IN (
            SELECT rollback_of FROM config_change_log WHERE rollback_of IS NOT NULL
          )
        ORDER BY id DESC LIMIT 1
        """
    )
    if row is None:
        return False
    baseline_ic = json.loads(row["new_value"]).get("baseline_ic")
    if baseline_ic is None:
        return False
    live_w = await _weights_by_status(pool, "live")
    live_ic = await composite_ic(pool, live_w, 90)
    if live_ic is None or live_ic >= baseline_ic - DEGRADE_TOL:
        return False
    prev = json.loads(row["old_value"])
    now = datetime.now(UTC)
    for sig, w in prev.items():
        await pool.execute(
            "INSERT INTO signal_weight_current (signal_name,status,weight,last_updated,reason) "
            "VALUES ($1,'live',$2,$3,'auto_rollback') "
            "ON CONFLICT (signal_name,status) DO UPDATE SET "
            "weight=EXCLUDED.weight, last_updated=EXCLUDED.last_updated, reason=EXCLUDED.reason",
            sig, w, now,
        )
    await pool.execute(
        "INSERT INTO config_change_log (user_id, field, old_value, new_value, source, rollback_of) "
        "VALUES (0,'signal_weights',$1,$2,'auto_rollback',$3)",
        json.dumps(live_w), json.dumps(prev), row["id"],
    )
    return True
```

Delete the temporary `async def _maybe_rollback(pool): return False` stub added in Task 6.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_adaptive_weights_orchestration.py -v`
Expected: PASS (all 4 orchestration tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/adaptive_weights.py tests/backtest/test_adaptive_weights_orchestration.py
git commit -m "feat(weights): auto-rollback live weights when composite IC degrades below baseline"
```

---

### Task 8: wire into `run_monthly_ic_backtest` + e2e safety

**Files:**
- Modify: `alpha_agent/backtest/ic_engine.py:135-209` (`run_monthly_ic_backtest`)
- Test: `tests/backtest/test_ic_engine.py` (extend with one e2e test) OR a new `tests/backtest/test_ic_engine_adaptive_e2e.py`

**Context:** `run_monthly_ic_backtest` currently writes `signal_ic_history` AND applies the old inline weight rule (`valid_ics`/`weight`/`reason` block, roughly lines 186-208). Keep the IC-history-writing loop; replace ONLY the inline weight block with a single post-loop call to `apply_adaptive_weights(pool, _ACTIVE_SIGNALS)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_ic_engine_adaptive_e2e.py
from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.backtest.ic_engine import run_monthly_ic_backtest
from alpha_agent.fusion.combine import load_weights
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def _seed_pair(pool, ticker, as_of, signal_val, ret_5d, signal_name="news"):
    # Mirror the helper in test_ic_engine.py: signal row + 6 daily_prices rows.
    import json
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker,date,composite,rating,confidence,breakdown,partial,fetched_at) "
        "VALUES ($1,$2::date,$3,'HOLD',0.7,$4::jsonb,false,$5) "
        "ON CONFLICT (ticker,date) DO UPDATE SET breakdown=EXCLUDED.breakdown",
        ticker, as_of.date(), float(signal_val),
        json.dumps({"breakdown": [{"signal": signal_name, "z": float(signal_val)}]}), as_of,
    )
    entry, exit_ = 100.0, 100.0 * (1 + ret_5d)
    for off, c in enumerate([entry, entry, entry, entry, entry, exit_]):
        await pool.execute(
            "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, (as_of + timedelta(days=off)).date(), c,
        )


@pytest.mark.asyncio
async def test_run_backtest_produces_live_weights_via_adaptive(pool):
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    for i in range(15):
        await _seed_pair(pool, f"T{i:02d}", now - timedelta(days=20 - i + 5),
                         signal_val=i * 0.1, ret_5d=i * 0.005)
    await run_monthly_ic_backtest(pool)
    # IC history written:
    assert await pool.fetchval("SELECT count(*) FROM signal_ic_history WHERE signal_name='news'") > 0
    # Live weights exist (cold-start seed) and load_weights sees them (live only):
    weights = await load_weights(pool)
    assert "news" in weights
    # Safety: no shadow row leaked into load_weights (it filters status='live').
    live_count = await pool.fetchval(
        "SELECT count(*) FROM signal_weight_current WHERE signal_name='news' AND status='live'")
    assert live_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_ic_engine_adaptive_e2e.py -v`
Expected: Initially this may PASS partially via the OLD rule, but it will FAIL the intent once the old rule is removed and before the wire-in is added, run it after Step 3's removal to confirm. (If it passes against the old rule, that is acceptable; the real verification is Step 4 with the full suite.)

- [ ] **Step 3: Rewire `run_monthly_ic_backtest`**

In `alpha_agent/backtest/ic_engine.py`, inside `run_monthly_ic_backtest`, keep the loop that computes IC per window and writes `signal_ic_history`. REMOVE the inline weight block (the `valid_ics = [...]`, the `weight`/`reason` branches, and the `INSERT INTO signal_weight_current ...` upsert). After the loop, add:

```python
    from alpha_agent.backtest.adaptive_weights import apply_adaptive_weights
    await apply_adaptive_weights(pool, _ACTIVE_SIGNALS)
    return updated
```

Keep `updated` counting the signals whose IC history was processed (increment it in the loop as before, just without the weight upsert). Update the function docstring: weights are now produced by the Phase 1b adaptive layer (EWMA-ICIR + cap + floor + shadow/promote/rollback), not the inline mean-IC rule.

- [ ] **Step 4: Run the full backtest + fusion suite**

Run: `uv run pytest tests/backtest/ tests/fusion/ tests/storage/ -v`
Expected: PASS. The three pre-existing `tests/backtest/test_ic_engine.py` tests assumed the OLD weight rule (`weight==0.0`, `reason=='low_ic'`). Those assertions are now obsolete: update them to assert the adaptive outcome instead, that `signal_ic_history` rows were written and a live `signal_weight_current` row exists for the signal (drop the `reason=='low_ic'`/`weight==0.0` assertions, which encoded the removed rule). Keep the IC-history window assertions.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/ic_engine.py tests/backtest/test_ic_engine.py tests/backtest/test_ic_engine_adaptive_e2e.py
git commit -m "feat(ic): run_monthly_ic_backtest applies adaptive weights (Phase 1b)"
```

---

## Self-Review

**Spec coverage (Phase 1b, section 6 of the design):**
- EWMA-ICIR replacing raw mean-IC: Task 2 (`compute_ewma_icir`) + Task 6 (`_gather_icir` aggregates per-window ICIR into the candidate).
- Change cap (15% per update): Task 3 (`apply_change_cap`), applied in Task 6.
- Diversification floor + hard-drop after N consecutive bad windows: Task 3 (`apply_floor_or_drop`), state in the V012 `consecutive_bad_windows` column (Task 1).
- Shadow / promote / rollback: Task 1 (status + shadow_streak columns), Task 6 (shadow write + 5-day promotion streak), Task 7 (auto-rollback vs frozen baseline via `config_change_log`).
- Composite-IC comparison substrate: Task 5.
- Live-only consumption (shadow must not leak): Task 4.
- Wired into the live daily path: Task 8 (`run_monthly_ic_backtest`, which the Phase 1a daily cron already calls).

**Out of scope (separate later plans):** confidence calibration (Phase 1c), the methodology proposer (Phase 2), and the Evolution self-analysis UI panel (design section 9). This plan is the auto-tier weight hardening only.

**Placeholder scan:** No TBD/TODO. The single forward reference is the temporary `_maybe_rollback` stub introduced in Task 6 and replaced in Task 7; it is explicitly called out in both tasks so the suite stays green at each commit.

**Type consistency:** `apply_adaptive_weights(pool, active_signals) -> dict` (Task 6) is called from `run_monthly_ic_backtest` with `_ACTIVE_SIGNALS` (Task 8). `composite_ic(pool, weights: dict[str,float], window_days, fwd_days=5)` (Task 5) is used by both `apply_adaptive_weights` and `_maybe_rollback`. `apply_floor_or_drop(...) -> (weight, consecutive_bad, dropped)` (Task 3) is unpacked identically in Task 6. `config_change_log` inserts use exactly its V009 columns (`user_id, field, old_value, new_value, source, rollback_of`); `signal_weight_current` inserts use the V012 shape (`signal_name, status, weight, last_updated, reason, consecutive_bad_windows, shadow_streak`) with the widened `(signal_name, status)` PK.

**Early-data caveat (carry into execution):** with only ~10 days of IC history, most signals have < 2 IC points per window early on, so `compute_ewma_icir` returns None → `apply_floor_or_drop` treats them as bad windows → they sit at the floor (not hard-dropped until 3 consecutive bad windows). This is the intended conservative cold-start behavior; weights only sharpen as `signal_ic_history` accumulates day over day.
