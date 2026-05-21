# Phase 1c: Confidence Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform's displayed confidence mean what it says, by measuring realized directional hit-rate per stated-confidence level (reliability curve + Brier) and recalibrating confidence through an isotonic map that only suppresses overconfidence, so a "70% confident" call historically hits ~70% of the time rather than over-promising.

**Architecture:** A new pure-ish module `alpha_agent/backtest/confidence_calibration.py` holds: the hit definition (`_hit`), a DB gatherer of `(stated_confidence, hit)` pairs over a rolling window (joining `daily_signals_fast` ratings to the `daily_prices` 5-trading-day forward return), a numpy-only isotonic fit (PAVA, no sklearn), reliability/Brier computation, a one-directional `apply_calibration`, and a `run_calibration(pool)` orchestrator that stores the fitted map + diagnostics into a new `confidence_calibration` table. The three live read sites (`picks`, `signal_lookup`, `build_card`) load the latest map once and pass `compute_confidence`'s output through `apply_calibration`. `run_calibration` is invoked by the existing daily cron right after the IC backtest.

**Tech Stack:** Python 3.12, asyncpg, numpy (PAVA isotonic, no scipy/sklearn, lambda size limits), Postgres (Neon), pytest + pytest-postgresql (`applied_db` DSN fixture → build a pool via `get_pool`), uv.

**Decisions locked (2026-05-21):** rolling 90-day fit window (fall back to all-available history when < 90 days exist); apply mode = suppress overconfidence only (`calibrated = min(isotonic(stated), stated)`, never raises); global identity fallback when fewer than 50 `(confidence, hit)` pairs; hit = pure `sign(forward 5-day return)` matches the rating direction, no deadband.

---

## Existing code this builds on

- **Ratings (5-tier):** `alpha_agent/fusion/rating.py`, `map_to_tier(composite) -> Tier` where `Tier = Literal["BUY","OW","HOLD","UW","SELL"]` (BUY > 1.5, OW > 0.5, HOLD >= -0.5, UW >= -1.5, SELL < -1.5). `compute_confidence(zs: Iterable[float]) -> float` is the raw signal-agreement gauge (0..1).
- **Confidence read sites (apply targets):** `alpha_agent/api/routes/picks.py:189`, `alpha_agent/api/signal_lookup.py:120`, `alpha_agent/cli/build_card.py:108`, each calls `compute_confidence(z_values)`.
- **Stored predictions:** `daily_signals_fast(ticker, date, composite, rating, confidence, breakdown JSONB, ...)`, historical rating + confidence per ticker per day.
- **Forward return source (Phase 1a, live):** `daily_prices(ticker, date, close)`; the 5-trading-day forward return is `LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) / close - 1`.
- **Daily cron:** `alpha_agent/api/routes/cron_routes.py` + the GH Actions `daily_prices_puller` job already runs `ic_backtest_monthly` daily; `run_calibration` hooks in right after.
- **Test fixture:** `applied_db` (from `tests/storage/conftest.py`) is a DSN string; build a pool via `get_pool(applied_db)`.

---

## File Structure

- `alpha_agent/storage/migrations/V013__confidence_calibration.sql` (new): the `confidence_calibration` table.
- `alpha_agent/backtest/confidence_calibration.py` (new): `_hit`, `gather_confidence_hits`, `isotonic_fit` (PAVA), `apply_calibration`, `reliability_and_brier`, `run_calibration`, `load_active_calibration`.
- `alpha_agent/fusion/rating.py` (modify): add `calibrated_confidence(zs, cal_map)` thin wrapper (keeps `compute_confidence` pure).
- `alpha_agent/api/routes/picks.py`, `alpha_agent/api/signal_lookup.py`, `alpha_agent/cli/build_card.py` (modify): load the active map once and route confidence through `calibrated_confidence`.
- `alpha_agent/api/routes/ic_backtest.py` (modify): call `run_calibration` after the IC backtest (so the daily cron produces a fresh map).
- Tests: `tests/storage/test_migration_v013.py`, `tests/backtest/test_confidence_calibration_math.py`, `tests/backtest/test_confidence_calibration_db.py`.

---

### Task 1: V013 `confidence_calibration` migration

**Files:**
- Create: `alpha_agent/storage/migrations/V013__confidence_calibration.sql`
- Test: `tests/storage/test_migration_v013.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v013.py
import json

import pytest

from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_confidence_calibration_table_upserts(pool):
    await pool.execute(
        """
        INSERT INTO confidence_calibration
            (as_of, isotonic_map, buckets, n_pairs, applied)
        VALUES (now(), $1::jsonb, $2::jsonb, 120, true)
        """,
        json.dumps({"x": [0.0, 0.5, 1.0], "y": [0.0, 0.4, 0.6]}),
        json.dumps([{"lo": 0.0, "hi": 0.1, "hit_rate": 0.0, "brier": 0.0, "n": 5}]),
    )
    row = await pool.fetchrow(
        "SELECT isotonic_map, n_pairs, applied FROM confidence_calibration "
        "ORDER BY as_of DESC LIMIT 1"
    )
    assert row["n_pairs"] == 120
    assert row["applied"] is True
    assert json.loads(row["isotonic_map"])["y"] == [0.0, 0.4, 0.6]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v013.py -v`
Expected: FAIL with `UndefinedTableError: relation "confidence_calibration" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V013__confidence_calibration.sql (2026-05-21)
--
-- Phase 1c: stores the fitted confidence->realized-hit-rate isotonic map plus
-- the reliability/Brier diagnostics, one row per calibration run (the daily
-- cron appends a fresh row). The live read path loads the most recent row and
-- passes displayed confidence through isotonic_map (suppress-overconfidence
-- only). `applied=false` rows are diagnostics-only (e.g. below the min-sample
-- threshold) and must NOT be used to recalibrate.
CREATE TABLE IF NOT EXISTS confidence_calibration (
    id bigserial PRIMARY KEY,
    as_of timestamptz NOT NULL DEFAULT now(),
    isotonic_map jsonb NOT NULL,   -- {"x": [...], "y": [...]} monotone breakpoints
    buckets jsonb NOT NULL,        -- [{lo, hi, hit_rate, brier, n}, ...] reliability curve
    n_pairs integer NOT NULL,      -- (confidence, hit) sample count used
    applied boolean NOT NULL       -- false = identity fallback (too few samples)
);

CREATE INDEX IF NOT EXISTS idx_confidence_calibration_as_of
    ON confidence_calibration (as_of DESC);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_migration_v013.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V013__confidence_calibration.sql tests/storage/test_migration_v013.py
git commit -m "feat(db): V013 confidence_calibration table"
```

---

### Task 2: hit definition + `(confidence, hit)` gatherer

**Files:**
- Create: `alpha_agent/backtest/confidence_calibration.py`
- Test: `tests/backtest/test_confidence_calibration_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_confidence_calibration_db.py
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_agent.backtest.confidence_calibration import _hit, gather_confidence_hits
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


def test_hit_direction_rules():
    assert _hit("BUY", 0.03) is True      # up call, up return
    assert _hit("OW", -0.01) is False     # up call, down return
    assert _hit("SELL", -0.02) is True    # down call, down return
    assert _hit("UW", 0.01) is False      # down call, up return
    assert _hit("HOLD", 0.05) is None     # excluded
    assert _hit("BUY", 0.0) is False      # exactly flat is not "up"


async def _seed(pool, ticker, as_of, rating, confidence, fwd_pct):
    await pool.execute(
        "INSERT INTO daily_signals_fast (ticker,date,composite,rating,confidence,breakdown,fetched_at) "
        "VALUES ($1,$2::date,0.0,$3,$4,$5::jsonb,now()) "
        "ON CONFLICT (ticker,date) DO UPDATE SET rating=EXCLUDED.rating, confidence=EXCLUDED.confidence",
        ticker, as_of, rating, confidence, json.dumps({"breakdown": []}),
    )
    closes = [100, 100, 100, 100, 100, 100 * (1 + fwd_pct)]
    for i, c in enumerate(closes):
        await pool.execute(
            "INSERT INTO daily_prices (ticker,date,close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
            ticker, as_of + timedelta(days=i), c,
        )


@pytest.mark.asyncio
async def test_gather_excludes_hold_and_pairs_confidence_with_hit(pool):
    base = date.today() - timedelta(days=30)
    await _seed(pool, "AAA", base, "BUY", 0.8, 0.05)    # hit  (conf 0.8)
    await _seed(pool, "BBB", base, "SELL", 0.6, 0.04)   # miss (conf 0.6, up vs down call)
    await _seed(pool, "CCC", base, "HOLD", 0.9, 0.05)   # excluded
    pairs = await gather_confidence_hits(pool, window_days=90)
    by_conf = {round(c, 2): h for c, h in pairs}
    assert 0.8 in by_conf and by_conf[0.8] == 1   # BUY hit -> 1
    assert 0.6 in by_conf and by_conf[0.6] == 0   # SELL miss -> 0
    assert 0.9 not in by_conf                      # HOLD excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py -v`
Expected: FAIL, `ImportError: cannot import name '_hit'`.

- [ ] **Step 3: Write the module's first two functions**

```python
# alpha_agent/backtest/confidence_calibration.py
"""Phase 1c confidence calibration.

Measures realized directional hit-rate per stated confidence (reliability
curve + Brier), fits a monotone isotonic map (numpy PAVA, no sklearn), and
applies it on the live read path to suppress overconfidence only. The daily
cron appends a fresh calibration row; the read path loads the latest.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

MIN_PAIRS: int = 50          # below this, fall back to identity (no recalibration)
FIT_WINDOW_DAYS: int = 90    # rolling fit window; uses all available if < this
_FWD_DAYS: int = 5
_UP_TIERS = frozenset({"BUY", "OW"})
_DOWN_TIERS = frozenset({"UW", "SELL"})


def _hit(rating: str, fwd_5d: float) -> bool | None:
    """True/False if the rating's directional call matched the realized
    forward 5-day return sign; None for HOLD (excluded from calibration).
    Pure sign match, no deadband: a non-positive return fails an up-call."""
    if rating in _UP_TIERS:
        return fwd_5d > 0
    if rating in _DOWN_TIERS:
        return fwd_5d < 0
    return None


async def gather_confidence_hits(pool, window_days: int = FIT_WINDOW_DAYS) -> list[tuple[float, int]]:
    """Return [(stated_confidence, hit01), ...] over the rolling window: each
    non-HOLD daily_signals_fast row with an observable 5-trading-day forward
    return (from daily_prices) contributes one pair. hit01 is 1/0."""
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    fwd_cutoff = (now - timedelta(days=_FWD_DAYS)).date()
    rows = await pool.fetch(
        """
        WITH fwd AS (
            SELECT ticker, date, close AS ce,
                   LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS cx
            FROM daily_prices
        )
        SELECT f.rating, f.confidence,
               (fwd.cx / fwd.ce - 1)::double precision AS fwd_5d
        FROM daily_signals_fast f
        JOIN fwd ON fwd.ticker = f.ticker AND fwd.date = f.date
        WHERE f.date >= $1 AND f.date <= $2
          AND f.rating IS NOT NULL AND f.confidence IS NOT NULL
          AND fwd.ce > 0 AND fwd.cx IS NOT NULL
        """,
        window_start, fwd_cutoff,
    )
    pairs: list[tuple[float, int]] = []
    for r in rows:
        h = _hit(r["rating"], float(r["fwd_5d"]))
        if h is None:
            continue
        pairs.append((float(r["confidence"]), 1 if h else 0))
    return pairs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/confidence_calibration.py tests/backtest/test_confidence_calibration_db.py
git commit -m "feat(calib): hit definition + confidence-hit gatherer over daily_prices"
```

---

### Task 3: isotonic fit (numpy PAVA) + suppress-only apply

**Files:**
- Modify: `alpha_agent/backtest/confidence_calibration.py` (append `_pava`, `isotonic_fit`, `apply_calibration`)
- Test: `tests/backtest/test_confidence_calibration_math.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_confidence_calibration_math.py
import pytest

from alpha_agent.backtest.confidence_calibration import (
    _pava,
    apply_calibration,
    isotonic_fit,
)


def test_pava_is_non_decreasing():
    out = _pava([0.3, 0.1, 0.2, 0.9, 0.4])
    assert all(out[i] <= out[i + 1] + 1e-12 for i in range(len(out) - 1))


def test_isotonic_none_below_min_pairs():
    # Fewer than MIN_PAIRS (50) -> None (identity fallback).
    assert isotonic_fit([(0.5, 1)] * 49) is None


def test_isotonic_suppresses_overconfident_region():
    # 60 pairs, 5 confidence levels, realized hit-rate = confidence * 0.5
    # (systematically overconfident). The fitted map at high confidence must
    # sit well below the diagonal.
    pairs = []
    for conf in (0.1, 0.3, 0.5, 0.7, 0.9):
        n_hit = round(12 * conf * 0.5)
        pairs += [(conf, 1)] * n_hit + [(conf, 0)] * (12 - n_hit)
    cal = isotonic_fit(pairs)
    assert cal is not None
    mapped_high = float(__import__("numpy").interp(0.9, cal["x"], cal["y"]))
    assert mapped_high < 0.6  # 0.9 stated -> well below, near ~0.45


def test_apply_calibration_is_suppress_only():
    cal = {"x": [0.0, 1.0], "y": [0.0, 0.4]}  # maps 0.9 -> 0.36
    assert apply_calibration(0.9, cal) == pytest.approx(0.36)
    # A map that would RAISE confidence is clamped to raw (never inflates).
    cal_up = {"x": [0.0, 1.0], "y": [0.0, 1.0]}  # identity-ish, maps 0.5 -> 0.5
    assert apply_calibration(0.5, cal_up) == pytest.approx(0.5)
    cal_inflate = {"x": [0.0, 1.0], "y": [0.5, 1.0]}  # maps 0.2 -> 0.6 (inflation)
    assert apply_calibration(0.2, cal_inflate) == pytest.approx(0.2)  # clamped


def test_apply_calibration_identity_when_no_map():
    assert apply_calibration(0.77, None) == pytest.approx(0.77)
    assert apply_calibration(0.77, {"x": [], "y": []}) == pytest.approx(0.77)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_confidence_calibration_math.py -v`
Expected: FAIL, `ImportError: cannot import name '_pava'`.

- [ ] **Step 3: Append to `confidence_calibration.py`**

```python
def _pava(y) -> np.ndarray:
    """Pool-adjacent-violators isotonic regression (non-decreasing), equal
    weights. Returns the fitted values aligned to the input order."""
    vals: list[float] = []
    cnts: list[int] = []
    for v in y:
        vals.append(float(v))
        cnts.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, c2 = vals.pop(), cnts.pop()
            v1, c1 = vals.pop(), cnts.pop()
            cn = c1 + c2
            vals.append((v1 * c1 + v2 * c2) / cn)
            cnts.append(cn)
    out: list[float] = []
    for v, c in zip(vals, cnts):
        out.extend([v] * c)
    return np.array(out)


def isotonic_fit(pairs: list[tuple[float, int]]) -> dict | None:
    """Fit a monotone non-decreasing confidence -> hit-rate map via PAVA.
    Returns {"x": [...], "y": [...]} breakpoints (strictly increasing x), or
    None if fewer than MIN_PAIRS samples (identity fallback upstream)."""
    if len(pairs) < MIN_PAIRS:
        return None
    arr = sorted(pairs, key=lambda p: p[0])
    xs = np.array([p[0] for p in arr], dtype=float)
    ys = np.array([float(p[1]) for p in arr], dtype=float)
    fitted = _pava(ys)
    # Collapse to unique x (np.interp needs strictly increasing x). The fitted
    # value is constant within a pooled block, so the mean over a tied x is exact.
    ux = np.unique(xs)
    uy = np.array([float(fitted[xs == x].mean()) for x in ux])
    return {"x": ux.tolist(), "y": uy.tolist()}


def apply_calibration(raw_confidence: float, cal_map: dict | None) -> float:
    """Suppress overconfidence only: calibrated = min(isotonic(raw), raw).
    Identity when there is no usable map (None / empty), so a thin or missing
    calibration never inflates a displayed confidence."""
    raw = float(raw_confidence)
    if not cal_map:
        return raw
    xs, ys = cal_map.get("x"), cal_map.get("y")
    if not xs or not ys:
        return raw
    mapped = float(np.interp(raw, xs, ys))
    return min(mapped, raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_confidence_calibration_math.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/confidence_calibration.py tests/backtest/test_confidence_calibration_math.py
git commit -m "feat(calib): numpy PAVA isotonic fit + suppress-only apply"
```

---

### Task 4: reliability curve + Brier

**Files:**
- Modify: `alpha_agent/backtest/confidence_calibration.py` (append `reliability_and_brier`)
- Test: `tests/backtest/test_confidence_calibration_math.py` (extend)

- [ ] **Step 1: Append the failing test**

```python
# append to tests/backtest/test_confidence_calibration_math.py
from alpha_agent.backtest.confidence_calibration import reliability_and_brier  # noqa: E402


def test_reliability_buckets_hit_rate_and_brier():
    # Two clear buckets: conf 0.1 (hit-rate 0.0) and conf 0.9 (hit-rate 1.0).
    pairs = [(0.1, 0)] * 10 + [(0.9, 1)] * 10
    buckets = reliability_and_brier(pairs, n_buckets=10)
    by = {(b["lo"], b["hi"]): b for b in buckets if b["n"] > 0}
    low = next(b for k, b in by.items() if k[0] <= 0.1 < k[1])
    high = next(b for k, b in by.items() if k[0] <= 0.9 < k[1])
    assert low["hit_rate"] == pytest.approx(0.0)
    assert high["hit_rate"] == pytest.approx(1.0)
    # Brier in the 0.1 bucket: mean((0.1-0)^2) = 0.01; in 0.9 bucket: (0.9-1)^2 = 0.01.
    assert low["brier"] == pytest.approx(0.01)
    assert high["brier"] == pytest.approx(0.01)
    assert low["n"] == 10 and high["n"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_confidence_calibration_math.py -v`
Expected: FAIL, `ImportError: cannot import name 'reliability_and_brier'`.

- [ ] **Step 3: Append to `confidence_calibration.py`**

```python
def reliability_and_brier(pairs: list[tuple[float, int]], n_buckets: int = 10) -> list[dict]:
    """Bucket pairs by stated confidence into n_buckets equal-width [0,1] bins;
    per bucket report realized hit_rate, Brier (mean (confidence - hit)^2), and
    count. Empty buckets are reported with n=0 so the reliability curve is dense."""
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    out: list[dict] = []
    confs = np.array([p[0] for p in pairs], dtype=float)
    hits = np.array([p[1] for p in pairs], dtype=float)
    for i in range(n_buckets):
        lo, hi = float(edges[i]), float(edges[i + 1])
        # last bucket is closed on the right so confidence == 1.0 lands somewhere.
        in_bin = (confs >= lo) & (confs < hi) if i < n_buckets - 1 else (confs >= lo) & (confs <= hi)
        n = int(in_bin.sum())
        if n == 0:
            out.append({"lo": lo, "hi": hi, "hit_rate": None, "brier": None, "n": 0})
            continue
        c_in, h_in = confs[in_bin], hits[in_bin]
        out.append({
            "lo": lo, "hi": hi,
            "hit_rate": float(h_in.mean()),
            "brier": float(np.mean((c_in - h_in) ** 2)),
            "n": n,
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_confidence_calibration_math.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/backtest/confidence_calibration.py tests/backtest/test_confidence_calibration_math.py
git commit -m "feat(calib): reliability curve + per-bucket Brier"
```

---

### Task 5: `run_calibration` orchestrator + loader + cron wire-in

**Files:**
- Modify: `alpha_agent/backtest/confidence_calibration.py` (add `import json` at top; append `run_calibration`, `load_active_calibration`)
- Modify: `alpha_agent/api/routes/ic_backtest.py` (call `run_calibration` after the IC backtest)
- Test: `tests/backtest/test_confidence_calibration_db.py` (extend)

- [ ] **Step 1: Append the failing test**

```python
# append to tests/backtest/test_confidence_calibration_db.py
from alpha_agent.backtest.confidence_calibration import (  # noqa: E402
    load_active_calibration,
    run_calibration,
)


@pytest.mark.asyncio
async def test_run_calibration_stores_applied_map_when_enough_pairs(pool):
    base = date.today() - timedelta(days=30)
    # 60 overconfident pairs: BUY at confidence 0.9 but only ~half hit.
    for i in range(60):
        rating = "BUY" if i % 2 == 0 else "SELL"
        # BUY with negative return = miss; SELL with negative = hit -> ~50% hit at conf 0.9
        await _seed(pool, f"T{i:02d}", base, rating, 0.9, -0.02)
    res = await run_calibration(pool)
    assert res["n_pairs"] >= 50 and res["applied"] is True
    cal = await load_active_calibration(pool)
    assert cal is not None and cal["x"]
    # The active map suppresses the overconfident 0.9 region.
    from alpha_agent.backtest.confidence_calibration import apply_calibration
    assert apply_calibration(0.9, cal) < 0.9


@pytest.mark.asyncio
async def test_run_calibration_identity_when_too_few_pairs(pool):
    base = date.today() - timedelta(days=30)
    await _seed(pool, "AAA", base, "BUY", 0.8, 0.05)  # 1 pair, < MIN_PAIRS
    res = await run_calibration(pool)
    assert res["applied"] is False
    assert await load_active_calibration(pool) is None  # nothing applied yet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py -v`
Expected: FAIL, `ImportError: cannot import name 'run_calibration'`.

- [ ] **Step 3: Append to `confidence_calibration.py`** (and add `import json` to the top import block)

```python
async def run_calibration(pool) -> dict:
    """Gather (confidence, hit) pairs over the rolling window, fit the isotonic
    map, compute the reliability/Brier diagnostics, and append a row to
    confidence_calibration. `applied` is False when below MIN_PAIRS (the map is
    stored as empty so the loader treats it as identity)."""
    pairs = await gather_confidence_hits(pool)
    cal_map = isotonic_fit(pairs)
    buckets = reliability_and_brier(pairs)
    applied = cal_map is not None
    await pool.execute(
        "INSERT INTO confidence_calibration (as_of, isotonic_map, buckets, n_pairs, applied) "
        "VALUES (now(), $1::jsonb, $2::jsonb, $3, $4)",
        json.dumps(cal_map or {"x": [], "y": []}),
        json.dumps(buckets),
        len(pairs), applied,
    )
    return {"n_pairs": len(pairs), "applied": applied}


async def load_active_calibration(pool) -> dict | None:
    """Most recent APPLIED calibration map, or None (identity) if none exists.
    Read once per request on the live path and passed to apply_calibration."""
    row = await pool.fetchrow(
        "SELECT isotonic_map FROM confidence_calibration "
        "WHERE applied = true ORDER BY as_of DESC LIMIT 1"
    )
    if row is None:
        return None
    m = json.loads(row["isotonic_map"])
    return m if m.get("x") else None
```

- [ ] **Step 4: Wire into the daily cron**

Read `alpha_agent/api/routes/ic_backtest.py`. In the `ic_backtest_monthly` handler, after `await run_monthly_ic_backtest(pool)`, add a calibration step and include it in the response:

```python
    from alpha_agent.backtest.confidence_calibration import run_calibration
    calib = await run_calibration(pool)
    # ... fold calib into the returned dict, e.g. {..., "calibration": calib}
```

Match the route's existing return/response shape (read it first). The Phase 1a `daily_prices_puller` GH job already POSTs `ic_backtest_monthly` daily, so no workflow change is needed: calibration now runs daily as part of that call.

- [ ] **Step 5: Run the DB tests + verify the route imports**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py -v`
Expected: PASS (4 tests).
Run: `uv run python -c "from alpha_agent.api.routes.ic_backtest import router; print('route OK')"`
Expected: `route OK` (no import error from the added run_calibration call).

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/backtest/confidence_calibration.py alpha_agent/api/routes/ic_backtest.py tests/backtest/test_confidence_calibration_db.py
git commit -m "feat(calib): run_calibration orchestrator + loader, wired into daily IC cron"
```

---

### Task 6: apply calibration on the live read path

**Files:**
- Modify: `alpha_agent/fusion/rating.py` (add `calibrated_confidence`)
- Modify: `alpha_agent/api/routes/picks.py`, `alpha_agent/api/signal_lookup.py` (route confidence through it)
- Modify: `alpha_agent/cli/build_card.py` (use the wrapper with no map = identity, for uniformity)
- Test: `tests/backtest/test_confidence_calibration_db.py` (extend with a read-path integration test)

- [ ] **Step 1: Append the failing test**

```python
# append to tests/backtest/test_confidence_calibration_db.py
from alpha_agent.fusion.rating import calibrated_confidence, compute_confidence  # noqa: E402


@pytest.mark.asyncio
async def test_calibrated_confidence_suppresses_via_active_map(pool):
    base = date.today() - timedelta(days=30)
    for i in range(60):
        rating = "BUY" if i % 2 == 0 else "SELL"
        await _seed(pool, f"T{i:02d}", base, rating, 0.9, -0.02)
    await run_calibration(pool)
    cal = await load_active_calibration(pool)
    zs = [3.0, 3.0, 3.0]  # high-agreement z's -> high raw confidence
    raw = compute_confidence(zs)
    calibrated = calibrated_confidence(zs, cal)
    assert calibrated <= raw  # suppress-only: never inflates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py -v`
Expected: FAIL, `ImportError: cannot import name 'calibrated_confidence'`.

- [ ] **Step 3: Add `calibrated_confidence` to `alpha_agent/fusion/rating.py`**

```python
def calibrated_confidence(zs, cal_map=None) -> float:
    """compute_confidence passed through the Phase 1c calibration map
    (suppress overconfidence only). cal_map=None -> raw confidence unchanged."""
    from alpha_agent.backtest.confidence_calibration import apply_calibration
    return apply_calibration(compute_confidence(zs), cal_map)
```

(Use a function-level import to avoid any import-ordering coupling between `fusion` and `backtest`; `confidence_calibration` itself imports nothing from `fusion`, so there is no cycle, but the local import keeps `rating.py` import-light.)

- [ ] **Step 4: Route the live read sites through it**

In `alpha_agent/api/routes/picks.py` and `alpha_agent/api/signal_lookup.py`: read each file to find the handler that calls `compute_confidence(z_values)` (picks.py:~189, signal_lookup.py:~120). Once per request, load the active map before the loop:

```python
    from alpha_agent.backtest.confidence_calibration import load_active_calibration
    cal_map = await load_active_calibration(pool)
```

Then replace `confidence = compute_confidence(z_values)` with:

```python
    confidence = calibrated_confidence(z_values, cal_map)
```

(Import `calibrated_confidence` from `alpha_agent.fusion.rating` alongside the existing `compute_confidence` import; `compute_confidence` may still be imported if used elsewhere in the file, otherwise switch the import.)

In `alpha_agent/cli/build_card.py` (a CLI with no live calibration context): replace `confidence = compute_confidence(zs)` with `confidence = calibrated_confidence(zs, None)` so all sites use one entry point; passing `None` is identity, leaving CLI output unchanged.

- [ ] **Step 5: Run the calibration tests + the picks/signal API tests + confirm no regression**

Run: `uv run pytest tests/backtest/test_confidence_calibration_db.py tests/backtest/test_confidence_calibration_math.py tests/api/ -v`
Expected: PASS. If any existing picks/signal test asserts a specific confidence value, confirm it still holds (with no active calibration row in the test DB, `load_active_calibration` returns None → identity → unchanged confidence). Report any failure rather than weakening it.

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check alpha_agent/fusion/rating.py alpha_agent/api/routes/picks.py alpha_agent/api/signal_lookup.py alpha_agent/cli/build_card.py alpha_agent/backtest/confidence_calibration.py
git add alpha_agent/fusion/rating.py alpha_agent/api/routes/picks.py alpha_agent/api/signal_lookup.py alpha_agent/cli/build_card.py tests/backtest/test_confidence_calibration_db.py
git commit -m "feat(calib): apply suppress-only calibration on live confidence read path"
```

---

## Self-Review

**Spec coverage (Phase 1c, design section 7):**
- Measure (reliability + Brier per bucket, hit = sign(fwd 5d) matches rating direction, HOLD excluded): Task 2 (`_hit`, `gather_confidence_hits`) + Task 4 (`reliability_and_brier`).
- Recalibrate (isotonic over rolling held-out window, stored in `confidence_calibration`): Task 1 (table), Task 3 (PAVA `isotonic_fit`), Task 5 (`run_calibration` over the 90d window, stored).
- Apply (live path routes `compute_confidence` through the map; suppresses overconfidence only): Task 3 (`apply_calibration`), Task 6 (`calibrated_confidence` at the 3 read sites).

**Locked-decision coverage:** rolling 90d with all-available fallback = `FIT_WINDOW_DAYS=90` in `gather_confidence_hits` (the window is a date filter; thin history naturally yields fewer pairs, no special-case needed). Suppress-only = `min(mapped, raw)` in `apply_calibration`. Identity below 50 pairs = `MIN_PAIRS=50` → `isotonic_fit` returns None → `run_calibration` writes `applied=false` → `load_active_calibration` returns None → `apply_calibration` is identity. Pure sign match, HOLD excluded = `_hit`.

**Out of scope (separate plan):** the Evolution UI panel that renders the reliability curve / Brier / what-auto-changed (design section 9) and the Phase 2 methodology proposer. Phase 1c stores the diagnostics (the `buckets` column) for that future UI but does not build it.

**Placeholder scan:** No TBD/TODO. The cron wire-in (Task 5 Step 4) and the read-site edits (Task 6 Step 4) are "read the file, find the call site" steps with the exact replacement shown inline, consistent with how Phases 1a/1b handled call-site edits.

**Type consistency:** `apply_calibration(raw: float, cal_map: dict|None) -> float` is used by `calibrated_confidence` (Task 6) and the math tests (Task 3). `isotonic_fit(pairs) -> dict|None` feeds `run_calibration` (Task 5), whose stored map is read back by `load_active_calibration` and passed to `apply_calibration`, the `{"x":[...], "y":[...]}` shape is consistent across fit, store, load, and apply. `gather_confidence_hits -> list[tuple[float,int]]` feeds both `isotonic_fit` and `reliability_and_brier`.

**Early-data caveat (carry into execution):** with ~10 days of predictions, `gather_confidence_hits` will return well under 50 pairs, so `run_calibration` writes `applied=false` and the live path stays identity (raw confidence shown) until enough history accrues. This is the intended conservative behavior; the reliability/Brier `buckets` still get recorded each day for later inspection.
