# Phase 1a: Forward-Return Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dormant walk-forward IC engine a real forward-return source (a daily-close price table) so `signal_ic_history` and `signal_weight_current` finally populate, activating the measurement half of the self-loop and fixing the P0-3 "IC columns empty" symptom for real.

**Architecture:** Add a `daily_prices(ticker, date, close)` table. Rewire `ic_engine.compute_walk_forward_ic` to compute the forward 5 trading-day return from `daily_prices` via a `LEAD(close, 5)` window (5 trading days, not 5 calendar days, which the old `minute_bars` join got wrong). Populate `daily_prices` via a backfill script run against production (production yfinance works, local IP rate-limits) plus a daily append cron. Invoke the already-existing `/api/cron/ic_backtest_monthly` endpoint daily.

**Tech Stack:** Python 3.12, asyncpg, FastAPI, numpy, yfinance, Postgres (Neon), pytest + pytest-postgresql (`applied_db` async fixture), uv for running.

---

## File Structure

- `alpha_agent/storage/migrations/V011__daily_prices.sql` (new): the `daily_prices` table.
- `alpha_agent/storage/queries.py` (modify): add `upsert_daily_close` + (test-only convenience) nothing else; the IC join reads `daily_prices` directly in `ic_engine`.
- `alpha_agent/backtest/ic_engine.py` (modify): rewire the forward-return leg of `compute_walk_forward_ic` from `minute_bars` to `daily_prices` with a 5 trading-day `LEAD`.
- `scripts/backfill_daily_prices.py` (new): one-time + repeatable backfill of `daily_prices` (yfinance daily history), runnable locally against the prod DATABASE_URL.
- `alpha_agent/api/routes/cron_routes.py` (modify): add a `/api/cron/daily_prices` append endpoint.
- `api/cron/daily_prices.py` (new): the daily-append handler.
- `tests/storage/test_migration_v011.py` (new): migration applies + shape.
- `tests/backtest/test_ic_engine_daily_prices.py` (new): IC computed from `daily_prices`, walk-forward exclusion, 5-trading-day offset.

---

### Task 1: V011 `daily_prices` migration

**Files:**
- Create: `alpha_agent/storage/migrations/V011__daily_prices.sql`
- Test: `tests/storage/test_migration_v011.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v011.py
import pytest


@pytest.mark.asyncio
async def test_daily_prices_table_exists_and_upserts(applied_db):
    # applied_db is an asyncpg pool with all migrations applied.
    await applied_db.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ('AAPL', '2026-01-02', 185.5)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """
    )
    # Upsert (same PK) must replace, not error.
    await applied_db.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ('AAPL', '2026-01-02', 190.0)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """
    )
    row = await applied_db.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'AAPL' AND date = '2026-01-02'"
    )
    assert row["close"] == pytest.approx(190.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_migration_v011.py -v`
Expected: FAIL with an asyncpg `UndefinedTableError: relation "daily_prices" does not exist`.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V011__daily_prices.sql (2026-05-21)
--
-- Daily-close price history for the universe. The forward-return leg of
-- the walk-forward IC engine reads this instead of minute_bars (which is
-- only a rolling 7-day cache and so cannot serve 30/60/90-day windows).
-- One row per ticker per trading day; the IC engine derives the forward
-- 5 trading-day return via LEAD(close, 5) over (ticker ordered by date).
CREATE TABLE IF NOT EXISTS daily_prices (
    ticker text NOT NULL,
    date date NOT NULL,
    close double precision NOT NULL,
    PRIMARY KEY (ticker, date)
);

-- The IC query windows by ticker ordered by date; this index serves both
-- the PK lookups and the window scan.
CREATE INDEX IF NOT EXISTS idx_daily_prices_ticker_date
    ON daily_prices (ticker, date);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_migration_v011.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V011__daily_prices.sql tests/storage/test_migration_v011.py
git commit -m "feat(db): V011 daily_prices table for forward-return IC source"
```

---

### Task 2: `upsert_daily_close` query helper

**Files:**
- Modify: `alpha_agent/storage/queries.py` (append a new function at end of file)
- Test: `tests/storage/test_daily_prices_queries.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_daily_prices_queries.py
import pytest

from alpha_agent.storage.queries import upsert_daily_close


@pytest.mark.asyncio
async def test_upsert_daily_close_inserts_and_replaces(applied_db):
    await upsert_daily_close(applied_db, "MSFT", "2026-01-05", 410.0)
    await upsert_daily_close(applied_db, "MSFT", "2026-01-05", 415.0)  # same PK
    row = await applied_db.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'MSFT' AND date = '2026-01-05'"
    )
    assert row["close"] == pytest.approx(415.0)


@pytest.mark.asyncio
async def test_upsert_daily_close_skips_nonpositive(applied_db):
    # A zero/negative close is bad data (yfinance gap); the helper must skip it.
    await upsert_daily_close(applied_db, "NVDA", "2026-01-06", 0.0)
    row = await applied_db.fetchrow(
        "SELECT close FROM daily_prices WHERE ticker = 'NVDA' AND date = '2026-01-06'"
    )
    assert row is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/storage/test_daily_prices_queries.py -v`
Expected: FAIL with `ImportError: cannot import name 'upsert_daily_close'`.

- [ ] **Step 3: Write minimal implementation**

Append to `alpha_agent/storage/queries.py`:

```python
async def upsert_daily_close(
    pool: asyncpg.Pool, ticker: str, date: str, close: float
) -> None:
    """Insert/replace one daily close. Skips non-positive closes (yfinance
    gap rows) so the IC engine's return ratio never divides by zero."""
    if close is None or close <= 0:
        return
    await pool.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ($1, $2::date, $3)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """,
        ticker.upper(), date, float(close),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/storage/test_daily_prices_queries.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/queries.py tests/storage/test_daily_prices_queries.py
git commit -m "feat(db): upsert_daily_close helper with non-positive guard"
```

---

### Task 3: Rewire `compute_walk_forward_ic` to `daily_prices` (5 trading-day LEAD)

**Files:**
- Modify: `alpha_agent/backtest/ic_engine.py:74-132` (the `compute_walk_forward_ic` body)
- Test: `tests/backtest/test_ic_engine_daily_prices.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_ic_engine_daily_prices.py
import json
from datetime import date, timedelta

import pytest

from alpha_agent.backtest.ic_engine import compute_walk_forward_ic


async def _seed(pool, ticker, as_of: date, z: float, closes: list[float]):
    """Insert one daily_signals_fast row carrying signal 'factor' z, plus a
    run of daily_prices closes starting at as_of (one per trading day)."""
    await pool.execute(
        """
        INSERT INTO daily_signals_fast (ticker, date, composite, breakdown, fetched_at)
        VALUES ($1, $2::date, 0.0, $3::jsonb, now())
        ON CONFLICT (ticker, date) DO UPDATE SET breakdown = EXCLUDED.breakdown
        """,
        ticker, as_of.isoformat(),
        json.dumps({"breakdown": [{"signal": "factor", "z": z}]}),
    )
    for i, c in enumerate(closes):
        d = as_of + timedelta(days=i)
        await pool.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1,$2::date,$3) "
            "ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close",
            ticker, d.isoformat(), c,
        )


@pytest.mark.asyncio
async def test_ic_uses_5_trading_day_lead_and_is_positive(applied_db):
    # Three tickers; higher z -> higher realized fwd-5-row return. A perfect
    # monotone relationship should give Spearman IC = 1.0.
    base = date.today() - timedelta(days=40)
    # close[as_of]=100, close 5 rows later encodes the return: bigger z -> bigger jump.
    await _seed(applied_db, "AAA", base, z=-1.0, closes=[100, 100, 100, 100, 100, 100])  # +0%
    await _seed(applied_db, "BBB", base, z=0.0, closes=[100, 100, 100, 100, 100, 105])   # +5%
    await _seed(applied_db, "CCC", base, z=1.0, closes=[100, 100, 100, 100, 100, 110])   # +10%
    # _MIN_OBS is 10 in the engine; lower it for the test via monkeypatch is
    # cleaner, but here we seed 12 tickers to clear the floor instead.
    for k in range(9):
        z = (k - 4) / 4.0
        await _seed(applied_db, f"T{k}", base, z=z, closes=[100, 100, 100, 100, 100, 100 + z * 10])
    result = await compute_walk_forward_ic(applied_db, "factor", 90)
    assert result is not None
    ic, n_obs = result
    assert n_obs >= 10
    assert ic > 0.9  # near-perfect monotone z -> fwd return


@pytest.mark.asyncio
async def test_ic_excludes_as_of_without_5_day_exit(applied_db):
    # An as_of whose 5th-ahead trading-day close does not exist yet must be
    # excluded (walk-forward: never peek at an unobservable exit).
    recent = date.today()
    await _seed(applied_db, "ZZZ", recent, z=0.5, closes=[100, 101])  # only 2 days, no +5 exit
    result = await compute_walk_forward_ic(applied_db, "factor", 90)
    # Only the seedless recent row exists -> below _MIN_OBS -> None.
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/backtest/test_ic_engine_daily_prices.py -v`
Expected: FAIL. The current engine joins `minute_bars` (empty in the test DB) so it returns None / 0 observations, failing `test_ic_uses_5_trading_day_lead_and_is_positive`.

- [ ] **Step 3: Rewrite the forward-return query**

In `alpha_agent/backtest/ic_engine.py`, replace the SQL block inside `compute_walk_forward_ic` (the `rows = await pool.fetch(""" ... """, signal_name, window_start, fwd_cutoff)` call) with this `daily_prices` version:

```python
    rows = await pool.fetch(
        """
        WITH sig AS (
            SELECT
                f.ticker,
                f.date AS as_of,
                (elem->>'z')::double precision AS signal_z
            FROM daily_signals_fast f
            CROSS JOIN LATERAL jsonb_array_elements(f.breakdown->'breakdown') AS elem
            WHERE elem->>'signal' = $1
              AND f.date >= $2
              AND f.date <= $3
              AND (elem->>'z') IS NOT NULL
        ),
        fwd AS (
            SELECT
                ticker,
                date,
                close AS close_entry,
                LEAD(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS close_exit
            FROM daily_prices
        )
        SELECT
            s.signal_z,
            (fwd.close_exit / fwd.close_entry - 1)::double precision AS fwd_5d
        FROM sig s
        JOIN fwd
          ON fwd.ticker = s.ticker
         AND fwd.date = s.as_of
        WHERE fwd.close_entry > 0
          AND fwd.close_exit IS NOT NULL
        """,
        signal_name,
        window_start,
        fwd_cutoff,
    )
```

Also update the docstring "Schema adaptation note" and the forward-return bullet to say the exit price now comes from `daily_prices` via `LEAD(close, 5)` (5 trading days), and that `close_exit IS NULL` (no observable exit) naturally enforces the walk-forward guarantee.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/backtest/test_ic_engine_daily_prices.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the existing IC-engine tests to confirm no regression**

Run: `uv run pytest tests/ -k "ic_engine or ic_backtest" -v`
Expected: PASS (or pre-existing DB-less skips unchanged). Note any test that seeded `minute_bars` for IC; if one exists, update it to seed `daily_prices` the same way as the new test.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/backtest/ic_engine.py tests/backtest/test_ic_engine_daily_prices.py
git commit -m "feat(ic): forward-return leg reads daily_prices via 5-trading-day LEAD"
```

---

### Task 4: `daily_prices` population (backfill script + daily append cron)

**Files:**
- Create: `scripts/backfill_daily_prices.py`
- Create: `api/cron/daily_prices.py`
- Modify: `alpha_agent/api/routes/cron_routes.py` (add the `/api/cron/daily_prices` route)

- [ ] **Step 1: Write the backfill script**

```python
#!/usr/bin/env python3
"""Backfill daily_prices with ~3y of daily closes for the universe.

yfinance daily history is rate-limited on the local IP but works from the
production backend; this script runs LOCALLY against the prod DATABASE_URL,
pulling daily closes via yfinance (period configurable) and upserting them.
Run before the IC loop has any history:

    uv run python scripts/backfill_daily_prices.py --period 3y
    uv run python scripts/backfill_daily_prices.py --period 3y --tickers AAPL,MSFT

Idempotent: ON CONFLICT upsert, so re-running refreshes existing rows.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha_agent.data.universe import load_universe_tickers  # noqa: E402
from alpha_agent.signals.yf_helpers import get_ticker  # noqa: E402
from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import upsert_daily_close  # noqa: E402


async def _backfill_one(pool, ticker: str, period: str) -> int:
    df = get_ticker(ticker).history(period=period)
    if df is None or df.empty:
        return 0
    n = 0
    for ts, row in df.iterrows():
        close = row.get("Close")
        if close is None:
            continue
        await upsert_daily_close(pool, ticker, ts.date().isoformat(), float(close))
        n += 1
    return n


async def main(tickers: list[str], period: str) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set. Add it to .env before running.")
    if not tickers:
        tickers = list(load_universe_tickers())
    pool = await get_pool(db_url)
    try:
        total = 0
        for tk in tickers:
            try:
                n = await _backfill_one(pool, tk, period)
                total += n
                print(f"{tk}: {n} closes")
            except Exception as exc:  # noqa: BLE001
                print(f"{tk}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Done: {total} closes across {len(tickers)} tickers.")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3y")
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    tk = [t for t in args.tickers.split(",") if t.strip()] if args.tickers else []
    asyncio.run(main(tk, args.period))
```

Note: confirm `alpha_agent/data/universe.py` exposes a ticker-list loader; if the function name differs, use the actual loader (the panel parquet's ticker column, the same source `list_universes` uses).

- [ ] **Step 2: Write the daily-append cron handler**

```python
# api/cron/daily_prices.py
"""Daily append of today's close for the universe into daily_prices.

Mirrors the minute_bars cron pattern. Hobby function budget is ~300s, so
this supports limit/offset multi-shot like the other crons.
"""
from __future__ import annotations

import os
from typing import Any

from alpha_agent.data.universe import load_universe_tickers
from alpha_agent.signals.yf_helpers import get_ticker
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import upsert_daily_close


async def handler(limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    tickers = list(load_universe_tickers())
    start = offset or 0
    end = (start + limit) if limit else len(tickers)
    n = 0
    for tk in tickers[start:end]:
        try:
            df = get_ticker(tk).history(period="5d")
            if df is None or df.empty:
                continue
            ts = df.index[-1]
            close = df["Close"].iloc[-1]
            await upsert_daily_close(pool, tk, ts.date().isoformat(), float(close))
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return {"cron": "daily_prices", "updated": n, "range": [start, end]}
```

- [ ] **Step 3: Add the cron route**

In `alpha_agent/api/routes/cron_routes.py`, after the `cron_minute_bars` route, add:

```python
@router.post("/daily_prices")
@router.get("/daily_prices")
async def cron_daily_prices(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Append today's close for the universe into daily_prices (the
    forward-return source for the walk-forward IC engine)."""
    from api.cron.daily_prices import handler
    return await handler(limit=limit, offset=offset)
```

- [ ] **Step 4: Verify the route is registered + handler imports**

Run: `uv run python -c "from alpha_agent.api.app import create_app; app = create_app(); paths = [r.path for r in app.routes]; assert '/api/cron/daily_prices' in paths, paths; print('route OK')"`
Expected: `route OK`. (If `create_app` needs env, run with the existing test env pattern used by other cron tests.)

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_daily_prices.py api/cron/daily_prices.py alpha_agent/api/routes/cron_routes.py
git commit -m "feat(cron): daily_prices backfill script + daily append endpoint"
```

---

### Task 5: Daily invocation wiring + real-shape verification

**Files:**
- Modify: `vercel.json` (only if the Hobby cron slot is available) OR a GitHub Actions workflow file under `.github/workflows/` (preferred, matches existing multi-shot pattern).

- [ ] **Step 1: Decide the scheduler**

Vercel Hobby caps cron count (memory: `feedback_vercel_hobby_cron_daily_only`); `vercel.json` already uses its slot for `slow_daily`. The repo already drives full-SP500 coverage via GitHub Actions multi-shot (see the `slow_daily` docstring). Schedule the two daily steps there.

- [ ] **Step 2: Add a GitHub Actions workflow**

```yaml
# .github/workflows/daily-evolution.yml
name: daily-evolution
on:
  schedule:
    - cron: "0 14 * * 1-5"   # ~10min after slow_daily (13:30 UTC), weekdays
  workflow_dispatch: {}
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: Append today's daily_prices (multi-shot)
        run: |
          for off in 0 140 280 420; do
            curl -fsS -X POST "https://alpha.bobbyzhong.com/api/cron/daily_prices?limit=140&offset=$off" || true
          done
      - name: Run walk-forward IC backtest (populates IC + weights)
        run: curl -fsS -X POST "https://alpha.bobbyzhong.com/api/cron/ic_backtest_monthly"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily-evolution.yml
git commit -m "ci: daily evolution workflow (daily_prices append + IC backtest)"
```

- [ ] **Step 4: Apply V011 to prod + backfill (manual, after merge)**

```bash
# Apply migration (idempotent):
uv run python -c "import asyncio, os; from dotenv import load_dotenv; load_dotenv(); from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"
# Backfill ~3y of closes (local run, prod DB):
uv run python scripts/backfill_daily_prices.py --period 3y
```

- [ ] **Step 5: Real-shape verification (acceptance)**

After the backfill + one IC run, confirm the loop produced real data:

```bash
# IC history now has rows (was empty pre-Phase-1a):
uv run python -c "import asyncio, os; from dotenv import load_dotenv; load_dotenv(); import asyncpg; \
print(asyncio.run(asyncpg.connect(os.environ['DATABASE_URL']).__await__()) ) " 2>/dev/null || true
curl -s "https://alpha.bobbyzhong.com/api/_health/signals" | python3 -m json.tool | grep -E "n_obs_30d|icir_30d" | head
```
Expected: at least some signals show `n_obs_30d > 0` and non-null `icir_30d` (real IC, not all-null). On the stock detail page, the AttributionTable Rank IC / ICIR / IR columns now show numbers for signals that cleared `_MIN_OBS`, and the "accumulating" banner disappears for those.

- [ ] **Step 6: Commit any verification fixups**

If acceptance surfaced a shape mismatch (e.g. `load_universe_tickers` name, or the `daily_signals_fast` PK for the test seed), fix it and commit:

```bash
git add -A && git commit -m "fix(ic): align Phase 1a wiring with real schema shapes"
```

---

## Self-Review

**Spec coverage (Phase 1a only):** daily_prices table (Task 1), forward-return rewire to daily_prices with trading-day offset (Task 3), population/backfill (Task 4), daily cron wiring (Task 5), real-shape acceptance (Task 5 Step 5). Covered. Phases 1b/1c/2 are intentionally separate plans.

**Placeholder scan:** No TBD/TODO. Two flagged confirmations (the `load_universe_tickers` loader name, and whether any existing IC test seeds `minute_bars`) are explicit verification steps with the fix instruction inline, not placeholders.

**Type consistency:** `upsert_daily_close(pool, ticker, date, close)` defined in Task 2 is used identically in the backfill script + cron handler (Task 4). The `daily_prices(ticker, date, close)` columns match across migration, helper, IC query, and tests. `compute_walk_forward_ic(pool, signal_name, window_days)` signature is unchanged (only its SQL body changes), so `run_monthly_ic_backtest` keeps working.

**Out of scope reminder:** EWMA-ICIR weighting, change caps, shadow/rollback (Phase 1b), confidence calibration (Phase 1c), methodology proposer + Evolution UI (Phase 2), and full CPCV are NOT in this plan.
