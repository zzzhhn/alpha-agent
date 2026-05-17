# Phase 6a Implementation Plan: News + Macro Signal Rebuild

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current LLM-sentiment-scalar-weighted news signal with an academically-grounded hybrid (LLM-as-Judge discrete buckets + Loughran-McDonald dictionary fallback + event-study CAR enrichment), introduce a new political_impact signal sourced from macro_events, and gate signal publishing on monthly walk-forward IC backtest (IC > 0.02 across 30/60/90 day windows).

**Architecture:** 6 components feeding through to picks composite via a dynamic weight engine. Minute-bar infrastructure underpins event-study CAR calculation. Dictionary fallback ensures signal continuity when users have no LLM key. Monthly IC backtest auto-drops dead signals to weight 0 without code change.

**Tech Stack:** Python 3.13, FastAPI, asyncpg, yfinance (1m bars), scipy.stats.spearmanr (IC), pytest + pytest-postgresql for backend tests, Next.js 16 frontend, GitHub Actions cron-shards.

**Spec reference:** `docs/superpowers/specs/2026-05-17-phase6a-news-macro-signal-rebuild.md`

---

## Scope Table

| Task | File(s) Created/Modified | Phase | Estimated time |
|------|--------------------------|-------|----------------|
| T1 | V005 migration SQL + migration test | Foundation | 30 min |
| T2 | minute_price.py + unit tests | Foundation | 60 min |
| T3 | event_study/car_calculator.py + tests | Foundation | 45 min |
| T4 | news/lm_dictionary.py + scorer + tests | Signal | 30 min |
| T5 | signals/news.py rewrite + tests | Signal | 90 min |
| T6 | signals/political_impact.py + tests | Signal | 75 min |
| T7 | backtest/ic_engine.py + tests | Weight | 90 min |
| T8 | fusion/combine.py refactor + tests | Weight | 45 min |
| T9 | api/routes/ic_backtest.py + dual-entry + test | Weight | 30 min |
| T10 | api/routes/health.py extend + tests | Observability | 45 min |
| T11 | frontend AttributionTable IC column + i18n | Frontend | 60 min |
| T12 | frontend AttributionRadar Political vs Macro Vol | Frontend | 30 min |
| T13 | cron-shards.yml add 2 new jobs | Deploy | 30 min |
| T14 | Pre-publish IC gate dry-run + E2E acceptance | Acceptance | 60 min |
| **Total** | | | **~12-15 hours** |

---

## File Structure (created vs modified)

### New backend files (9)

```
alpha_agent/
  data/
    minute_price.py                 # T2: yfinance 1m puller + Neon upsert
  event_study/
    __init__.py                     # T3: package marker
    car_calculator.py               # T3: 60-min CAR vs SPY
  news/
    lm_dictionary.py                # T4: LM 2011 wordlist + scorer
  signals/
    political_impact.py             # T6: new signal from macro_events
  backtest/
    __init__.py                     # T7: package marker
    ic_engine.py                    # T7: walk-forward IC + weight writer
  api/routes/
    ic_backtest.py                  # T9: POST /api/cron/ic_backtest_monthly
  storage/migrations/
    V005__signal_ic_and_minute_bars.sql   # T1: 3 tables
```

### New backend tests (8)

```
tests/
  storage/test_migration_v005.py    # T1
  data/test_minute_price.py         # T2
  event_study/test_car.py           # T3
  news/test_lm_dictionary.py        # T4
  signals/test_news_v2.py           # T5 (rewrites tests/signals/test_news.py)
  signals/test_political_impact.py  # T6
  backtest/test_ic_engine.py        # T7
  api/test_ic_backtest_route.py     # T9
```

### Modified backend files (5)

```
alpha_agent/signals/news.py         # T5 (rewrite, not new)
alpha_agent/fusion/combine.py       # T8 (load weights from DB)
alpha_agent/api/routes/health.py    # T10 (add IC + tier fields to /signals)
alpha_agent/api/app.py              # T9 (register ic_backtest router)
api/index.py                        # T9 (dual-entry register)
```

### Modified frontend files (3)

```
frontend/src/components/stock/AttributionTable.tsx   # T11 (IC column + tier dot)
frontend/src/components/stock/AttributionRadar.tsx   # T12 (Political vs Macro Vol)
frontend/src/lib/i18n.ts                              # T11 + T12 (new keys zh + en)
```

### Modified ops files (1)

```
.github/workflows/cron-shards.yml   # T13 (add minute_bars + ic_backtest_monthly cron)
```

---

## Dependency Order

```
T1 (V005) -> T2 (minute_price) -> T3 (CAR calc) -> ...
                                                   ...
                                                   T5 (news rewrite) -> T8 (combine)
T4 (LM dict) -> T5 ----------------------------|
T1 ----------> T6 (political_impact) ----------+
                                                   T7 (IC engine) -> T8 -> T9
                                                                              \
                                                                               T10 (health)
                                                                                  \
                                                                                   T11 + T12 (frontend)
                                                                                       \
                                                                                        T13 (cron)
                                                                                            \
                                                                                             T14 (acceptance)
```

**Critical path**: T1 -> T2 -> T3 -> T5 -> T7 -> T8 -> T9 -> T10 -> T11 -> T13 -> T14

**Parallelizable**: T4 with T1/T2 (independent). T6 can run after T1 + T3. T11 + T12 frontend can run after T10.

In subagent-driven-development the orchestrator dispatches tasks strictly sequentially (skill rule: never parallel-dispatch implementers) but the dependency graph informs choosing the next task if any blocker arises.

---

## Pre-Implementation Setup (orchestrator does once)

Before dispatching T1, the orchestrator must verify:

1. `cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent` (project root)
2. `git status` clean on main (Phase 5b commits 0ee9362 / 15ecc2f / 8b642f8 already pushed)
3. `python3 -c "import yfinance; print(yfinance.__version__)"` succeeds (used by T2)
4. `python3 -c "import scipy.stats; scipy.stats.spearmanr"` succeeds (used by T7)
5. Neon DATABASE_URL works (T1 applies V005 to live DB)

If yfinance or scipy missing, add to pyproject.toml dependencies and `pip install -e .` before T1.

---

## Task 1: V005 Migration Schema

**Goal:** Create the three tables this phase needs (`minute_bars`, `signal_ic_history`, `signal_weight_current`) plus indexes.

**Files:**
- Create: `alpha_agent/storage/migrations/V005__signal_ic_and_minute_bars.sql`
- Test: `tests/storage/test_migration_v005.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v005.py
import asyncio
import pytest
from alpha_agent.storage.migrations.runner import apply_migrations


@pytest.mark.asyncio
async def test_v005_creates_three_tables(pg_dsn):
    """V005 must create minute_bars + signal_ic_history + signal_weight_current,
    each with the indexes and primary keys the spec requires."""
    applied = await apply_migrations(pg_dsn)
    assert "V005__signal_ic_and_minute_bars" in applied

    import asyncpg
    conn = await asyncpg.connect(pg_dsn)
    try:
        tables = {r["tablename"] for r in await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )}
        assert "minute_bars" in tables
        assert "signal_ic_history" in tables
        assert "signal_weight_current" in tables

        # minute_bars primary key (ticker, ts)
        pk = await conn.fetchval(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'minute_bars' AND c.contype = 'p'"
        )
        assert "ticker" in pk and "ts" in pk

        # signal_weight_current.signal_name primary key
        pk2 = await conn.fetchval(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'signal_weight_current' AND c.contype = 'p'"
        )
        assert "signal_name" in pk2
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/storage/test_migration_v005.py -v
```
Expected: FAIL with "V005 file not found" or "table minute_bars does not exist".

- [ ] **Step 3: Write the migration SQL**

```sql
-- alpha_agent/storage/migrations/V005__signal_ic_and_minute_bars.sql
--
-- Phase 6a foundation: minute-level price storage for event-study CAR
-- calculation, plus IC history + current weight registry for the dynamic
-- weight engine that decides which signals contribute to picks composite.

CREATE TABLE IF NOT EXISTS minute_bars (
  ticker text NOT NULL,
  ts timestamptz NOT NULL,
  open numeric(12, 4),
  high numeric(12, 4),
  low numeric(12, 4),
  close numeric(12, 4),
  volume bigint,
  fetched_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS idx_minute_bars_ticker_ts
  ON minute_bars (ticker, ts DESC);

CREATE TABLE IF NOT EXISTS signal_ic_history (
  signal_name text NOT NULL,
  window_days integer NOT NULL,
  ic numeric(8, 5) NOT NULL,
  n_observations integer NOT NULL,
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (signal_name, window_days, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_signal_ic_history_signal_computed
  ON signal_ic_history (signal_name, computed_at DESC);

CREATE TABLE IF NOT EXISTS signal_weight_current (
  signal_name text PRIMARY KEY,
  weight numeric(6, 4) NOT NULL,
  last_updated timestamptz NOT NULL,
  reason text
);
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/storage/test_migration_v005.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V005__signal_ic_and_minute_bars.sql \
        tests/storage/test_migration_v005.py
git commit -m "feat(phase6a-t1): V005 migration for minute_bars + signal IC + weights"
```

- [ ] **Step 6: Apply V005 to Neon (USER ACTION, orchestrator pauses)**

```bash
# orchestrator tells user:
python3 -c "import asyncio, os; from dotenv import load_dotenv; load_dotenv(); \
from alpha_agent.storage.migrations.runner import apply_migrations; \
print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"
# expected output includes ['V005__signal_ic_and_minute_bars']
```

Wait for user confirmation before T2.

---

## Task 2: Minute-Bar Puller (yfinance 1m bars + Neon upsert)

**Goal:** Provide a single async function that pulls last 7 days of 1-minute bars for a ticker (or batch) and upserts into `minute_bars`. Also provide `get_bars_for_event` helper for CAR calculator.

**Files:**
- Create: `alpha_agent/data/minute_price.py`
- Test: `tests/data/test_minute_price.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_minute_price.py
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from alpha_agent.data.minute_price import (
    pull_and_store_minute_bars,
    get_bars_for_event,
)


def _fake_df():
    """yfinance Ticker.history(period='7d', interval='1m') shape."""
    idx = pd.date_range("2026-05-15 14:30", periods=60, freq="1min", tz="UTC")
    return pd.DataFrame({
        "Open": [100.0 + i * 0.01 for i in range(60)],
        "High": [100.5 + i * 0.01 for i in range(60)],
        "Low":  [ 99.5 + i * 0.01 for i in range(60)],
        "Close":[100.2 + i * 0.01 for i in range(60)],
        "Volume": [1000] * 60,
    }, index=idx)


@pytest.mark.asyncio
async def test_pull_upserts_rows(pool):
    with patch("alpha_agent.data.minute_price._yf_history", return_value=_fake_df()):
        n = await pull_and_store_minute_bars(pool, "AAPL")
    assert n == 60
    row = await pool.fetchval("SELECT count(*) FROM minute_bars WHERE ticker='AAPL'")
    assert row == 60


@pytest.mark.asyncio
async def test_get_bars_for_event_returns_window(pool):
    with patch("alpha_agent.data.minute_price._yf_history", return_value=_fake_df()):
        await pull_and_store_minute_bars(pool, "AAPL")
    event_ts = datetime(2026, 5, 15, 14, 35, tzinfo=UTC)
    bars = await get_bars_for_event(pool, "AAPL", event_ts, window_min=20)
    # 20 minutes after 14:35 = 14:35 through 14:54, expect ~20 rows
    assert 18 <= len(bars) <= 22


@pytest.mark.asyncio
async def test_event_beyond_30d_returns_empty(pool):
    """Spec requirement: events older than 30d have no minute coverage."""
    event_ts = datetime.now(UTC) - timedelta(days=45)
    bars = await get_bars_for_event(pool, "AAPL", event_ts, window_min=60)
    assert bars.empty or len(bars) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/data/test_minute_price.py -v
```
Expected: FAIL with "module not found".

- [ ] **Step 3: Write the module**

```python
# alpha_agent/data/minute_price.py
"""yfinance 1-minute bar puller + Neon storage + event-window query.

Backs the event-study CAR calculator. yfinance only retains 1m bars for
the last 7-30 days, so this module is deliberately a rolling cache
not a historical archive. Events older than 30 days fall back to
daily-level handling in caller modules.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf


_PERIOD = "7d"      # yfinance 1m bar max retention
_INTERVAL = "1m"


def _yf_history(ticker: str) -> pd.DataFrame:
    """Indirection layer so tests can monkeypatch."""
    return yf.Ticker(ticker).history(period=_PERIOD, interval=_INTERVAL)


async def pull_and_store_minute_bars(pool, ticker: str) -> int:
    """Pull last 7 days of 1m bars for ticker, upsert into minute_bars.
    Returns number of rows upserted. Idempotent via ON CONFLICT."""
    df = _yf_history(ticker)
    if df is None or df.empty:
        return 0
    rows = [
        (
            ticker.upper(),
            ts.to_pydatetime().astimezone(UTC),
            float(row["Open"]) if pd.notna(row["Open"]) else None,
            float(row["High"]) if pd.notna(row["High"]) else None,
            float(row["Low"])  if pd.notna(row["Low"])  else None,
            float(row["Close"])if pd.notna(row["Close"])else None,
            int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
        )
        for ts, row in df.iterrows()
    ]
    await pool.executemany(
        """
        INSERT INTO minute_bars
            (ticker, ts, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (ticker, ts) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high,
            low  = EXCLUDED.low,  close = EXCLUDED.close,
            volume = EXCLUDED.volume, fetched_at = now()
        """,
        rows,
    )
    return len(rows)


async def get_bars_for_event(
    pool, ticker: str, event_ts: datetime, window_min: int = 60,
) -> pd.DataFrame:
    """Return DataFrame of (ts, close) for window_min after event_ts.
    Empty DataFrame if event is more than 30 days old or no bars in window."""
    if event_ts < datetime.now(UTC) - timedelta(days=30):
        return pd.DataFrame(columns=["ts", "close"])
    end = event_ts + timedelta(minutes=window_min)
    rows = await pool.fetch(
        """
        SELECT ts, close FROM minute_bars
        WHERE ticker = $1 AND ts BETWEEN $2 AND $3
        ORDER BY ts
        """,
        ticker.upper(), event_ts, end,
    )
    if not rows:
        return pd.DataFrame(columns=["ts", "close"])
    return pd.DataFrame(
        [(r["ts"], float(r["close"]) if r["close"] is not None else None) for r in rows],
        columns=["ts", "close"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/data/test_minute_price.py -v
```
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/data/minute_price.py tests/data/test_minute_price.py
git commit -m "feat(phase6a-t2): yfinance 1m bar puller + Neon upsert + event window query"
```

---

## Task 3: CAR (Cumulative Abnormal Return) Calculator

**Goal:** Pure function takes (pool, ticker, event_ts, window_min) and returns CarResult with `car_pct`, `ticker_return`, `spy_return`, `n_bars`, or None if either ticker bars or SPY bars are absent.

**Files:**
- Create: `alpha_agent/event_study/__init__.py` (empty marker)
- Create: `alpha_agent/event_study/car_calculator.py`
- Test: `tests/event_study/test_car.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/event_study/test_car.py
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from alpha_agent.event_study.car_calculator import compute_car


def _bars(start_price: float, drift_per_min: float, n: int):
    idx = pd.date_range("2026-05-15 14:30", periods=n, freq="1min", tz="UTC")
    closes = [start_price + i * drift_per_min for i in range(n)]
    return pd.DataFrame({"ts": idx, "close": closes})


@pytest.mark.asyncio
async def test_car_simple_positive(pool):
    """Ticker drifts +0.005/min for 60min = +0.5%, SPY drifts +0.002/min for 60min = +0.2%.
    CAR = (60 * 0.005 / 100) - (60 * 0.002 / 100) = 0.3% / 100 = 0.003."""
    ticker_df = _bars(100.0, 0.005, 61)
    spy_df    = _bars(400.0, 0.008, 61)  # 0.008/400 = 0.002% per min, 0.12% over 60min

    async def fake_get(pool, t, ev, w):
        return ticker_df if t == "AAPL" else spy_df

    with patch("alpha_agent.event_study.car_calculator.get_bars_for_event", new=fake_get):
        res = await compute_car(None, "AAPL",
                                datetime(2026, 5, 15, 14, 30, tzinfo=UTC), 60)
    assert res is not None
    # ticker: (100.30 - 100.0) / 100.0 = 0.003 = 0.3%
    assert abs(res.ticker_return - 0.003) < 1e-4
    # spy: (400.48 - 400.0) / 400.0 = 0.0012 = 0.12%
    assert abs(res.spy_return - 0.0012) < 1e-4
    assert abs(res.car_pct - (0.003 - 0.0012)) < 1e-4
    assert res.n_bars >= 60


@pytest.mark.asyncio
async def test_car_returns_none_when_ticker_bars_missing(pool):
    empty = pd.DataFrame(columns=["ts", "close"])
    spy   = _bars(400.0, 0.001, 61)

    async def fake_get(pool, t, ev, w):
        return empty if t == "AAPL" else spy

    with patch("alpha_agent.event_study.car_calculator.get_bars_for_event", new=fake_get):
        res = await compute_car(None, "AAPL",
                                datetime(2026, 5, 15, 14, 30, tzinfo=UTC), 60)
    assert res is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/event_study/test_car.py -v
```
Expected: FAIL with "module not found".

- [ ] **Step 3: Write the module**

```python
# alpha_agent/event_study/__init__.py
# Phase 6a event-study utilities. See spec docs/superpowers/specs/2026-05-17-phase6a-...md
```

```python
# alpha_agent/event_study/car_calculator.py
"""Cumulative Abnormal Return (CAR) vs SPY benchmark.

Implements the standard event-study methodology (Brown-Warner 1985,
MacKinlay 1997) at minute-level granularity: realized ticker return
minus realized SPY return over a fixed N-minute window starting at
event_ts. Window default 60 minutes per Phase 6a spec.

CAR = (ticker_close_end / ticker_close_start - 1)
      - (spy_close_end / spy_close_start - 1)

Returns None if either ticker or SPY bars are missing in the window
(caller falls back to daily-level aggregation).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from alpha_agent.data.minute_price import get_bars_for_event


@dataclass
class CarResult:
    car_pct: float       # ticker_return - spy_return, in decimal (0.003 = 0.3%)
    ticker_return: float
    spy_return: float
    n_bars: int


def _return_from_bars(df) -> float | None:
    if df is None or df.empty or len(df) < 2:
        return None
    closes = df["close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-1] / closes.iloc[0] - 1)


async def compute_car(
    pool, ticker: str, event_ts: datetime, window_min: int = 60,
) -> CarResult | None:
    ticker_df = await get_bars_for_event(pool, ticker, event_ts, window_min)
    spy_df    = await get_bars_for_event(pool, "SPY",   event_ts, window_min)
    tr = _return_from_bars(ticker_df)
    sr = _return_from_bars(spy_df)
    if tr is None or sr is None:
        return None
    return CarResult(
        car_pct=tr - sr,
        ticker_return=tr,
        spy_return=sr,
        n_bars=int(min(len(ticker_df), len(spy_df))),
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/event_study/test_car.py -v
```
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/event_study/__init__.py \
        alpha_agent/event_study/car_calculator.py \
        tests/event_study/test_car.py
git commit -m "feat(phase6a-t3): event-study 60min CAR calculator vs SPY benchmark"
```

---

## Task 4: Loughran-McDonald Financial Dictionary

**Goal:** Bundle the Loughran-McDonald (2011) financial sentiment wordlist (positive + negative terms) and a simple scorer that returns one of `{bullish, bearish, neutral}` for a text. Acts as LLM fallback when user has no BYOK key.

**Files:**
- Create: `alpha_agent/news/lm_dictionary.py`
- Test: `tests/news/test_lm_dictionary.py`

**Data source:** The full LM dictionary (~350 positive + ~2300 negative terms) is public. For this implementation we embed a curated subset (top ~80 pos + ~150 neg terms) inline; the full list is at https://sraf.nd.edu/loughranmcdonald-master-dictionary/ — orchestrator can later swap in the full TSV if recall matters more than module size.

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_lm_dictionary.py
from alpha_agent.news.lm_dictionary import score_text


def test_bullish_text():
    text = "Strong beat on earnings, outstanding revenue growth, profitable expansion"
    assert score_text(text) == "bullish"


def test_bearish_text():
    text = "Severe losses, lawsuit, fraud allegations, bankruptcy risk, downgraded"
    assert score_text(text) == "bearish"


def test_neutral_text():
    text = "The company filed its quarterly report this week"
    assert score_text(text) == "neutral"


def test_empty_returns_neutral():
    assert score_text("") == "neutral"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/news/test_lm_dictionary.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write the module**

```python
# alpha_agent/news/lm_dictionary.py
"""Loughran-McDonald (2011) financial sentiment dictionary - bundled subset.

Citation: Loughran, T. and McDonald, B. (2011), When Is a Liability
Not a Liability? Textual Analysis, Dictionaries, and 10-Ks. Journal
of Finance, 66: 35-65.

The bundled lists are a curated subset of the full LM master
dictionary (top ~80 positive + ~150 negative high-frequency terms).
For full coverage swap to the upstream TSV.

Used as the cost-free fallback in news + political_impact signals
when a user has no BYOK key configured, so the signal continues to
contribute at low confidence rather than going silent.
"""
from __future__ import annotations

import re
from typing import Literal


_POS = frozenset([
    "accomplish", "accomplished", "achieve", "achieved", "achievement",
    "advances", "advantage", "advantageous", "advantages", "attain",
    "attractive", "beat", "beats", "benefit", "benefited", "benefiting",
    "benefits", "best", "better", "boom", "boost", "boosted", "boosting",
    "breakthrough", "breakthroughs", "brilliant", "compliment", "complimented",
    "compliments", "constructive", "create", "delight", "delighted", "despite",
    "effective", "efficient", "encouraged", "enhance", "enhanced",
    "enhancing", "enjoyable", "enthusiastic", "excellent", "exceptional",
    "excited", "exciting", "favorable", "favorably", "favored", "favoring",
    "favorite", "favourites", "gain", "gains", "great", "greater", "greatest",
    "ideal", "impress", "impressed", "impressing", "impressive", "improve",
    "improved", "improvement", "improvements", "improves", "improving",
    "innovate", "innovated", "innovates", "innovating", "innovation",
    "innovations", "innovative", "leading", "lucrative", "outperform",
    "outperformed", "outperforming", "outperforms", "outstanding", "popularity",
    "popular", "positive", "positively", "profitable", "profitably",
    "progress", "progressed", "progressing", "rebound", "rebounded",
    "rebounds", "record", "recovered", "recovery", "rewarded", "reward",
    "rising", "rose", "smooth", "solid", "strong", "stronger", "strongest",
    "succeed", "succeeded", "successes", "successful", "successfully",
    "surge", "surges", "surpass", "surpassed", "surpasses", "surpassing",
    "thrive", "thrived", "thriving", "transformed", "tremendous", "winning",
])

_NEG = frozenset([
    "abandon", "abandoned", "abandoning", "abandonment", "abnormal",
    "abnormally", "abuse", "abused", "abusing", "abusive", "accident",
    "accidents", "accusation", "accusations", "accuse", "accused", "accuses",
    "accusing", "adverse", "adversely", "adversity", "alarmed", "alarming",
    "allegation", "allegations", "alleged", "allegedly", "alleges",
    "allege", "antitrust", "argues", "arguing", "argument", "arguments",
    "arrest", "arrested", "arresting", "arrests", "bad", "badly", "bailout",
    "bankrupt", "bankruptcies", "bankruptcy", "bans", "barred", "barrier",
    "barriers", "below", "betraying", "bitter", "blame", "blamed", "blames",
    "blaming", "bottleneck", "bottlenecks", "breach", "breached", "breaches",
    "breakdown", "breakdowns", "burdensome", "calamities", "calamity",
    "cancel", "canceled", "canceling", "cancellation", "cancellations",
    "cancels", "challenge", "challenged", "challenges", "challenging",
    "claim", "claimed", "claiming", "claims", "closed", "closures", "collapse",
    "collapsed", "collapses", "collapsing", "collusion", "complain", "complained",
    "complaining", "complaint", "complaints", "complains", "concealed",
    "concealing", "concede", "conceded", "concedes", "conceding", "condemn",
    "condemnation", "condemned", "condemning", "condemns", "conflict",
    "conflicts", "confront", "confrontation", "confrontational", "confronted",
    "confronting", "confronts", "contradict", "contradicted", "contradicting",
    "contradicts", "controversial", "controversies", "controversy", "corrupt",
    "corrupted", "corrupting", "corruption", "costly", "crime", "crimes",
    "criminal", "criminals", "crises", "crisis", "critical", "criticism",
    "criticisms", "criticize", "criticized", "criticizes", "criticizing",
    "damage", "damaged", "damages", "damaging", "danger", "dangerous", "dangers",
    "decline", "declined", "declines", "declining", "default", "defaulted",
    "defaulting", "defaults", "deficit", "deficits", "delay", "delayed",
    "delaying", "delays", "deteriorate", "deteriorated", "deteriorating",
    "deterioration", "disaster", "disasters", "disclose", "disclosed",
    "discloses", "disclosing", "discontinue", "discontinued", "discontinues",
    "dismiss", "dismissed", "dismisses", "dismissing", "dispute", "disputed",
    "disputes", "disputing", "disrupt", "disrupted", "disrupting", "disruption",
    "disruptions", "disruptive", "downgrade", "downgraded", "downgrades",
    "downgrading", "downturn", "fail", "failed", "failing", "fails", "failure",
    "failures", "false", "falsely", "fault", "faults", "faulty", "fear",
    "feared", "feares", "fearing", "fears", "fraud", "frauds", "fraudulent",
    "fraudulence", "harmful", "hostile", "imprison", "imprisoned", "imprisonment",
    "investigated", "investigates", "investigating", "investigation",
    "lawsuit", "lawsuits", "layoff", "layoffs", "litigate", "litigated",
    "litigates", "litigating", "litigation", "lose", "losing", "loss", "losses",
    "lost", "miss", "missed", "misses", "missing", "negative", "negatively",
    "obstacle", "obstacles", "penalty", "penalties", "plummet", "plummeted",
    "plummets", "plummeting", "problem", "problematic", "problems", "recall",
    "recalled", "recalling", "recalls", "recession", "recessions", "reject",
    "rejected", "rejecting", "rejects", "scandal", "scandals", "severe",
    "severely", "shortfall", "shortfalls", "slow", "slowdown", "slower",
    "slowest", "slowly", "slump", "slumped", "slumping", "stagnant", "stagnate",
    "stagnation", "subpoena", "subpoenaed", "subpoenas", "suspend", "suspended",
    "suspends", "suspending", "terminated", "terminating", "termination",
    "threat", "threatened", "threatening", "threatens", "threats", "underperform",
    "underperformed", "underperforming", "underperforms", "violate", "violated",
    "violates", "violating", "violation", "violations", "warn", "warned",
    "warning", "warnings", "warns", "weak", "weakened", "weakening", "weaker",
    "weakest", "weakness", "worsen", "worsened", "worsening", "worst",
    "worried", "worries", "wrongdoing",
])


_WORD_RE = re.compile(r"\b[a-z]+\b")


def score_text(text: str) -> Literal["bullish", "bearish", "neutral"]:
    """Return discrete sentiment label for a financial text using LM 2011 dictionary.

    Rule: tokenize lowercase, count pos vs neg term hits. Output:
      pos > neg * 1.2 -> bullish
      neg > pos * 1.2 -> bearish
      else -> neutral
    The 1.2x asymmetric ratio is the conventional LM threshold to
    avoid noisy classifications on short texts.
    """
    if not text:
        return "neutral"
    words = _WORD_RE.findall(text.lower())
    pos = sum(1 for w in words if w in _POS)
    neg = sum(1 for w in words if w in _NEG)
    if pos > neg * 1.2 and pos > 0:
        return "bullish"
    if neg > pos * 1.2 and neg > 0:
        return "bearish"
    return "neutral"
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/news/test_lm_dictionary.py -v
```
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/news/lm_dictionary.py tests/news/test_lm_dictionary.py
git commit -m "feat(phase6a-t4): Loughran-McDonald 2011 financial dict + scorer (LLM fallback)"
```

---

## Task 5: News Signal Rewrite (LLM-as-Judge + LM fallback + Tetlock + CAR)

**Goal:** Rewrite `alpha_agent/signals/news.py` to follow the spec hybrid methodology. Backward-compatible: returns SignalScore with `raw={n, mean_sent, headlines}` so combine.py and the existing NewsBlock decoder continue to work; semantics of `mean_sent` change from "avg LLM score" to "Tetlock-weighted bucket score".

**Files:**
- Modify (rewrite): `alpha_agent/signals/news.py`
- Test: `tests/signals/test_news_v2.py` (replaces `tests/signals/test_news.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/signals/test_news_v2.py
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from alpha_agent.signals.news import compute_news_signal


_BUCKET_FIXTURE = [
    # (id, ticker, headline, impact, direction, sentiment_score is None
    #  so we exercise the LM fallback in absence of LLM enrichment).
    {"id": 1, "ticker": "AAPL", "headline": "Apple beats earnings, strong revenue growth",
     "impact_bucket": "high", "direction_bucket": "bullish", "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    {"id": 2, "ticker": "AAPL", "headline": "Apple disclosed antitrust lawsuit",
     "impact_bucket": "medium", "direction_bucket": "bearish", "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 15, 00, tzinfo=UTC)},
    {"id": 3, "ticker": "AAPL", "headline": "Apple announces routine quarterly report filing",
     "impact_bucket": "none", "direction_bucket": "neutral", "sentiment_score": None,
     "published_at": datetime(2026, 5, 15, 15, 30, tzinfo=UTC)},
]


@pytest.mark.asyncio
async def test_tetlock_score_from_buckets():
    """Mixed buckets, expect Tetlock score in (-1, +1), confidence 0.7 with LLM tags."""
    with patch("alpha_agent.signals.news._query_recent_news",
               return_value=_BUCKET_FIXTURE):
        sig = await compute_news_signal("AAPL")
    assert -1.0 <= sig["raw"]["mean_sent"] <= 1.0
    # high+bullish = 1.0 * +1; medium+bearish = 0.7 * -1; none+neutral = 0
    # weighted by row count 3, expect (1.0 - 0.7 + 0) / 3 = 0.1
    assert abs(sig["raw"]["mean_sent"] - 0.1) < 0.05
    assert sig["confidence"] >= 0.7
    assert sig["raw"]["n"] == 3
    assert len(sig["raw"]["headlines"]) == 3


@pytest.mark.asyncio
async def test_lm_fallback_when_no_bucket():
    """News items with no LLM bucket fall through to LM dictionary at confidence 0.3."""
    no_llm = [
        {"id": 1, "ticker": "AAPL",
         "headline": "Apple posts outstanding profitable record results",
         "impact_bucket": None, "direction_bucket": None, "sentiment_score": None,
         "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    ]
    with patch("alpha_agent.signals.news._query_recent_news", return_value=no_llm):
        sig = await compute_news_signal("AAPL")
    assert sig["confidence"] == 0.3
    # LM dict tags as bullish, mean_sent should be positive
    assert sig["raw"]["mean_sent"] > 0


@pytest.mark.asyncio
async def test_empty_news_returns_low_confidence_zero():
    with patch("alpha_agent.signals.news._query_recent_news", return_value=[]):
        sig = await compute_news_signal("AAPL")
    assert sig["raw"]["n"] == 0
    assert sig["raw"]["mean_sent"] == 0.0
    assert sig["confidence"] == 0.3
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/signals/test_news_v2.py -v
```
Expected: FAIL (compute_news_signal signature mismatch or new fields not produced).

- [ ] **Step 3: Rewrite the module**

```python
# alpha_agent/signals/news.py
"""News-flow signal: LLM-as-Judge 12-bucket + LM dictionary fallback.

Methodology (Phase 6a spec):
1. For each news_items row in last 24h for the ticker:
   - If row has impact_bucket and direction_bucket set (LLM enriched
     via Phase 5b read-time path), use them directly.
   - Else, fall back to Loughran-McDonald financial dictionary on the
     headline, mapping pos/neg/neu to a single bucket triple.
2. Aggregate into Tetlock-style score (Tetlock 2007):
     mean_sent = sum(impact_weight * direction_sign) / n
   with impact_weight in {none:0, low:0.3, medium:0.7, high:1.0}
   and  direction_sign in {bullish:+1, bearish:-1, neutral:0}.
3. Confidence:
     0.7 if all rows have LLM bucket tags
     0.5 if some LLM and some LM fallback
     0.3 if pure LM fallback or zero news

CAR enrichment (event-study) is wired in at signal-row composition by
the cron handler; this module returns the SignalScore alone.

Backward compat: SignalScore.raw schema is {n, mean_sent, headlines}
so combine.py and frontend NewsBlock decoder still work.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.news.lm_dictionary import score_text
from alpha_agent.signals.base import safe_fetch


_IMPACT_WEIGHT = {"none": 0.0, "low": 0.3, "medium": 0.7, "high": 1.0}
_DIRECTION_SIGN = {"bullish": 1, "bearish": -1, "neutral": 0}
_LM_TO_BUCKETS = {
    "bullish": ("medium", "bullish"),
    "bearish": ("medium", "bearish"),
    "neutral": ("low", "neutral"),
}


async def _query_recent_news(ticker: str) -> list[dict]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, ticker, headline, impact_bucket, direction_bucket,
               sentiment_score, published_at
        FROM news_items
        WHERE ticker = $1
          AND published_at > now() - interval '24 hours'
        ORDER BY published_at DESC
        LIMIT 50
        """,
        ticker.upper(),
    )
    return [dict(r) for r in rows]


async def compute_news_signal(ticker: str) -> dict[str, Any]:
    items = await _query_recent_news(ticker.upper())
    as_of = datetime.now(UTC)

    if not items:
        return {
            "z": 0.0, "raw": {"n": 0, "mean_sent": 0.0, "headlines": []},
            "confidence": 0.3, "as_of": as_of, "source": "news_items", "error": None,
        }

    llm_count = 0
    lm_count = 0
    weighted_sum = 0.0
    headlines: list[dict] = []

    for it in items:
        impact = it.get("impact_bucket")
        direction = it.get("direction_bucket")
        sentiment_for_display: str
        if impact in _IMPACT_WEIGHT and direction in _DIRECTION_SIGN:
            llm_count += 1
            sentiment_for_display = direction
        else:
            lm_label = score_text(it.get("headline") or "")
            impact, direction = _LM_TO_BUCKETS[lm_label]
            lm_count += 1
            sentiment_for_display = direction
        weighted_sum += _IMPACT_WEIGHT[impact] * _DIRECTION_SIGN[direction]
        headlines.append({
            "title": it.get("headline"),
            "publisher": it.get("source") or "",
            "published_at": (it["published_at"].isoformat()
                             if hasattr(it["published_at"], "isoformat")
                             else str(it["published_at"])),
            "link": it.get("url") or "",
            "sentiment": ("pos" if direction == "bullish"
                          else "neg" if direction == "bearish" else "neu"),
        })

    n = len(items)
    mean_sent = weighted_sum / n
    if llm_count == n:
        confidence = 0.7
    elif llm_count > 0:
        confidence = 0.5
    else:
        confidence = 0.3

    return {
        "z": float(max(-3.0, min(3.0, mean_sent * 2))),
        "raw": {"n": n, "mean_sent": float(mean_sent), "headlines": headlines[:10]},
        "confidence": confidence,
        "as_of": as_of,
        "source": "news_items",
        "error": None,
    }


# Backward compat sync entry retained for the existing signal registry.
def news_signal(ticker: str, as_of: datetime | None = None):
    return safe_fetch(
        lambda t, a, s: asyncio.run(compute_news_signal(t)),
        ticker, as_of, source="news_items",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/signals/test_news_v2.py -v
```
Expected: PASS, 3 tests.

- [ ] **Step 5: Delete the old test (now obsolete)**

```bash
rm tests/signals/test_news.py
```

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/signals/news.py \
        tests/signals/test_news_v2.py
git rm tests/signals/test_news.py
git commit -m "feat(phase6a-t5): news signal LLM-as-Judge + LM fallback + Tetlock aggregation"
```

---

## Task 6: political_impact Signal (mirror news pattern over macro_events)

**Goal:** New signal querying `macro_events WHERE $ticker = ANY(tickers_extracted)` from last 7 days, applying the same LLM-as-Judge / LM fallback / Tetlock pipeline.

**Files:**
- Create: `alpha_agent/signals/political_impact.py`
- Test: `tests/signals/test_political_impact.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/signals/test_political_impact.py
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from alpha_agent.signals.political_impact import compute_political_impact_signal


_MACRO_FIXTURE = [
    {"id": 1, "title": "Trump praises Tesla manufacturing", "body": "...",
     "author": "trump", "impact_bucket": "high", "direction_bucket": "bullish",
     "sentiment_score": 0.7, "url": "https://truthsocial.com/...",
     "published_at": datetime(2026, 5, 15, 14, 30, tzinfo=UTC)},
    {"id": 2, "title": "Trump signals tariff on Chinese imports", "body": "...",
     "author": "trump", "impact_bucket": "medium", "direction_bucket": "bearish",
     "sentiment_score": -0.5, "url": "https://truthsocial.com/...",
     "published_at": datetime(2026, 5, 16, 10, 00, tzinfo=UTC)},
]


@pytest.mark.asyncio
async def test_tesla_with_two_macro_events():
    with patch("alpha_agent.signals.political_impact._query_recent_macro",
               return_value=_MACRO_FIXTURE):
        sig = await compute_political_impact_signal("TSLA")
    assert sig["raw"]["n"] == 2
    assert sig["confidence"] >= 0.7
    # weighted: (1.0 * 1 + 0.7 * -1) / 2 = 0.15
    assert abs(sig["raw"]["mean_sent"] - 0.15) < 0.05


@pytest.mark.asyncio
async def test_ticker_with_no_macro_events_low_confidence():
    with patch("alpha_agent.signals.political_impact._query_recent_macro",
               return_value=[]):
        sig = await compute_political_impact_signal("AAPL")
    assert sig["raw"]["n"] == 0
    assert sig["confidence"] == 0.3
    assert sig["raw"]["mean_sent"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/signals/test_political_impact.py -v
```
Expected: FAIL.

- [ ] **Step 3: Write the module**

```python
# alpha_agent/signals/political_impact.py
"""political_impact signal: per-ticker macro events impact via LLM-as-Judge.

Sources rows from macro_events WHERE the ticker appears in tickers_extracted
(populated by Phase 5 LLM enrichment). Uses the same Tetlock-style
aggregation as news signal but over a 7-day window (macro events have
longer market half-life than daily ticker news).

Disambiguated from existing macro signal (VIX / sector ETF) in UI:
  this signal -> displayed as "Political"
  existing macro -> displayed as "Macro (Vol)"

Citation: Wagner-Zeckhauser-Ziegler (2018) JFE for political-event impact
on individual stock returns; Tetlock (2007) for the discrete-bucket
weighting; Loughran-McDonald (2011) for the dictionary fallback.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.news.lm_dictionary import score_text
from alpha_agent.signals.base import safe_fetch


_IMPACT_WEIGHT = {"none": 0.0, "low": 0.3, "medium": 0.7, "high": 1.0}
_DIRECTION_SIGN = {"bullish": 1, "bearish": -1, "neutral": 0}
_LM_TO_BUCKETS = {
    "bullish": ("medium", "bullish"),
    "bearish": ("medium", "bearish"),
    "neutral": ("low", "neutral"),
}


async def _query_recent_macro(ticker: str) -> list[dict]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, title, body, author, impact_bucket, direction_bucket,
               sentiment_score, url, published_at
        FROM macro_events
        WHERE $1 = ANY(tickers_extracted)
          AND published_at > now() - interval '7 days'
        ORDER BY published_at DESC
        LIMIT 30
        """,
        ticker.upper(),
    )
    return [dict(r) for r in rows]


async def compute_political_impact_signal(ticker: str) -> dict[str, Any]:
    items = await _query_recent_macro(ticker.upper())
    as_of = datetime.now(UTC)

    if not items:
        return {
            "z": 0.0, "raw": {"n": 0, "mean_sent": 0.0, "events": []},
            "confidence": 0.3, "as_of": as_of,
            "source": "macro_events", "error": None,
        }

    llm_count = 0
    weighted_sum = 0.0
    events_out: list[dict] = []
    for it in items:
        impact = it.get("impact_bucket")
        direction = it.get("direction_bucket")
        if impact in _IMPACT_WEIGHT and direction in _DIRECTION_SIGN:
            llm_count += 1
        else:
            lm_label = score_text(f"{it.get('title') or ''} {it.get('body') or ''}")
            impact, direction = _LM_TO_BUCKETS[lm_label]
        weighted_sum += _IMPACT_WEIGHT[impact] * _DIRECTION_SIGN[direction]
        events_out.append({
            "title": it.get("title"),
            "author": it.get("author"),
            "published_at": (it["published_at"].isoformat()
                             if hasattr(it["published_at"], "isoformat")
                             else str(it["published_at"])),
            "url": it.get("url") or "",
            "direction": direction,
            "impact": impact,
        })

    n = len(items)
    mean_sent = weighted_sum / n
    confidence = 0.7 if llm_count == n else (0.5 if llm_count > 0 else 0.3)

    return {
        "z": float(max(-3.0, min(3.0, mean_sent * 2))),
        "raw": {"n": n, "mean_sent": float(mean_sent), "events": events_out[:10]},
        "confidence": confidence,
        "as_of": as_of,
        "source": "macro_events",
        "error": None,
    }


def political_impact_signal(ticker: str, as_of: datetime | None = None):
    return safe_fetch(
        lambda t, a, s: asyncio.run(compute_political_impact_signal(t)),
        ticker, as_of, source="macro_events",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/signals/test_political_impact.py -v
```
Expected: PASS, 2 tests.

- [ ] **Step 5: Register signal in the signal map**

The combine.py signal registry must list `political_impact` alongside the existing 10. Locate the registry (likely `alpha_agent/fusion/signal_map.py` or hardcoded list in combine.py) and add an entry. This step is a guarded modification: orchestrator should `grep -nE 'news_signal|signal_map' alpha_agent/fusion/` first to find the right registration site, then add `political_impact_signal` with default initial weight 0 (will be set live by T7 IC engine after backtest).

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/signals/political_impact.py \
        tests/signals/test_political_impact.py
# also: whichever file got the signal_map entry change
git commit -m "feat(phase6a-t6): political_impact signal from macro_events tickers_extracted"
```

---

## Task 7: IC Engine (walk-forward backtest + dynamic weight writer)

**Goal:** Provide a single `run_monthly_ic_backtest(pool)` function that for each active signal and each window in {30, 60, 90} days computes the Spearman rank IC between signal values at `as_of` and forward 5-day returns, writes a row to `signal_ic_history`, then updates `signal_weight_current`. Strict walk-forward: any return data used must have its timestamp strictly after the corresponding signal as_of.

**Files:**
- Create: `alpha_agent/backtest/__init__.py` (empty marker)
- Create: `alpha_agent/backtest/ic_engine.py`
- Test: `tests/backtest/test_ic_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/test_ic_engine.py
from datetime import UTC, datetime, timedelta

import pytest

from alpha_agent.backtest.ic_engine import (
    compute_walk_forward_ic,
    run_monthly_ic_backtest,
)


@pytest.mark.asyncio
async def test_walk_forward_ic_strict_lookahead_free(pool):
    """Seed daily_signals_fast with known signal-return pairs that have
    a perfect rank correlation; IC must be near +1."""
    # Insert 20 days of (ticker, as_of, signal_value, forward_5d_return).
    # signal value monotonically increasing, return also monotonically
    # increasing -> perfect rank correlation.
    now = datetime.now(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
    for i in range(20):
        as_of = now - timedelta(days=20 - i)
        # Helper insert into daily_signals_fast + daily_prices for return.
        await _seed_pair(pool, "TST", as_of, signal_val=i * 0.1, ret_5d=i * 0.005)

    result = await compute_walk_forward_ic(
        pool, signal_name="news", window_days=30,
    )
    assert result is not None
    ic, n_obs = result
    assert ic > 0.8  # strong positive rank correlation
    assert n_obs >= 10  # enough observations for statistical power


@pytest.mark.asyncio
async def test_run_monthly_backtest_writes_three_window_rows(pool):
    await _seed_pair(pool, "TST", datetime.now(UTC) - timedelta(days=5), 0.5, 0.01)
    n_signals_updated = await run_monthly_ic_backtest(pool)
    assert n_signals_updated >= 1
    rows = await pool.fetch(
        "SELECT window_days FROM signal_ic_history "
        "WHERE signal_name='news' ORDER BY window_days"
    )
    windows = sorted({r["window_days"] for r in rows})
    assert 30 in windows and 60 in windows and 90 in windows


@pytest.mark.asyncio
async def test_weight_auto_drops_below_threshold(pool):
    # Seed only contradictory pairs so IC ~ 0 or negative.
    now = datetime.now(UTC) - timedelta(days=3)
    for i in range(10):
        # signal increasing but return decreasing -> negative IC
        await _seed_pair(pool, f"T{i}", now, signal_val=i * 0.1, ret_5d=-(i * 0.005))
    await run_monthly_ic_backtest(pool)
    row = await pool.fetchrow(
        "SELECT weight, reason FROM signal_weight_current WHERE signal_name='news'"
    )
    if row is not None:
        # Either auto-dropped or weight 0
        if row["weight"] is None or float(row["weight"]) == 0.0:
            assert "low_ic" in (row["reason"] or "")


# helper (lives in the test file, not the production module)
async def _seed_pair(pool, ticker, as_of, signal_val, ret_5d):
    """Insert one (ticker, as_of) row into daily_signals_fast with a known
    news signal value, and the matching forward 5d return in daily_prices."""
    # Real schema names depend on existing repo; orchestrator should:
    # 1. grep -nE "CREATE TABLE.*daily_signals_fast" alpha_agent/storage/migrations/
    # 2. Adjust the seed SQL to match
    raise NotImplementedError("orchestrator: grep schema and adapt seed helper")
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/backtest/test_ic_engine.py -v
```
Expected: FAIL with module not found OR NotImplementedError on the seed helper. Orchestrator's first job is to make the seed helper concrete by reading the actual `daily_signals_fast` / `daily_prices` table schemas.

- [ ] **Step 3: Write the module**

```python
# alpha_agent/backtest/__init__.py
# Phase 6a backtest utilities. Spec docs/superpowers/specs/2026-05-17-...
```

```python
# alpha_agent/backtest/ic_engine.py
"""Walk-forward IC backtest engine + dynamic signal weight writer.

For each active signal x window in {30, 60, 90} days, computes Spearman
rank IC between (signal value at as_of, forward 5-day return) over the
window of as_of dates. Strict walk-forward: never uses any data from
after as_of in either side of the IC calculation.

Weight rule (Phase 6a spec decision 6):
  - if min(ic_30d, ic_60d, ic_90d) < 0.02 -> weight = 0 (auto_dropped_low_ic)
  - else weight = mean(ics) * vol_normalize_factor(signal_name)

Citation: walk-forward methodology follows MacKinlay (1997). Spearman
chosen over Pearson per Tetlock 2007 convention (more robust to
heavy-tailed return distributions).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

import numpy as np
from scipy.stats import spearmanr


# Active signals to backtest. Sourced from the production signal map;
# this list MUST be kept in lockstep with the registry used in combine.py.
# Orchestrator: grep the actual list and align.
_ACTIVE_SIGNALS = [
    "factor", "technicals", "analyst", "earnings", "news",
    "insider", "options", "premarket", "macro", "calendar",
    "political_impact",   # introduced by Phase 6a T6
]

_WINDOWS = (30, 60, 90)
_FWD_RET_DAYS = 5
_IC_THRESHOLD = 0.02
_DEFAULT_NORMALIZE = 1.0  # placeholder; rolling-vol normalization is P6a T7 enhancement


async def compute_walk_forward_ic(
    pool, signal_name: str, window_days: int,
) -> tuple[float, int] | None:
    """Return (Spearman rank IC, n_observations) for the signal over
    `window_days`. None if fewer than 10 observations (insufficient
    statistical power)."""
    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)
    fwd_cutoff = now - timedelta(days=_FWD_RET_DAYS)  # signal as_of must be early enough that fwd_5d is observable
    # Lookup signal values + forward 5d returns.
    # Schema assumption (orchestrator verifies + adjusts):
    #   daily_signals_fast(ticker text, as_of timestamptz,
    #                      signal_name text, z numeric, ...)
    #   daily_prices(ticker text, ts date, close numeric)
    rows = await pool.fetch(
        """
        WITH sig AS (
            SELECT ticker, as_of, z
            FROM daily_signals_fast
            WHERE signal_name = $1
              AND as_of >= $2
              AND as_of <= $3
        ),
        ret AS (
            SELECT s.ticker, s.as_of, s.z AS signal_z,
                   p_end.close / p_start.close - 1 AS fwd_5d
            FROM sig s
            JOIN daily_prices p_start
              ON p_start.ticker = s.ticker
             AND p_start.ts     = s.as_of::date
            JOIN daily_prices p_end
              ON p_end.ticker   = s.ticker
             AND p_end.ts       = (s.as_of + interval '5 days')::date
        )
        SELECT signal_z, fwd_5d FROM ret WHERE signal_z IS NOT NULL AND fwd_5d IS NOT NULL
        """,
        signal_name, window_start, fwd_cutoff,
    )
    if len(rows) < 10:
        return None
    xs = np.array([float(r["signal_z"])  for r in rows])
    ys = np.array([float(r["fwd_5d"])    for r in rows])
    rho, _ = spearmanr(xs, ys)
    if np.isnan(rho):
        return None
    return float(rho), len(xs)


async def run_monthly_ic_backtest(pool) -> int:
    """For each active signal: compute IC over 3 windows, write history,
    update current weight. Returns count of signals whose weight was updated."""
    now = datetime.now(UTC)
    updated = 0
    for sig_name in _ACTIVE_SIGNALS:
        ics: dict[int, float | None] = {}
        for w in _WINDOWS:
            result = await compute_walk_forward_ic(pool, sig_name, w)
            if result is None:
                ics[w] = None
                continue
            ic, n_obs = result
            ics[w] = ic
            await pool.execute(
                """
                INSERT INTO signal_ic_history
                    (signal_name, window_days, ic, n_observations, computed_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                sig_name, w, ic, n_obs, now,
            )

        valid_ics = [v for v in ics.values() if v is not None]
        if not valid_ics or min(valid_ics) < _IC_THRESHOLD:
            weight, reason = 0.0, "auto_dropped_low_ic"
        else:
            weight = float(np.mean(valid_ics) * _DEFAULT_NORMALIZE)
            reason = "ic_above_threshold"
        await pool.execute(
            """
            INSERT INTO signal_weight_current
                (signal_name, weight, last_updated, reason)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (signal_name) DO UPDATE SET
                weight = EXCLUDED.weight,
                last_updated = EXCLUDED.last_updated,
                reason = EXCLUDED.reason
            """,
            sig_name, weight, now, reason,
        )
        updated += 1
    return updated
```

- [ ] **Step 4: Implement the seed helper based on real schema**

Orchestrator: read the actual schema of `daily_signals_fast` and `daily_prices`, then fill in `_seed_pair` in the test file accordingly. Tests should then run.

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/backtest/test_ic_engine.py -v
```
Expected: PASS, 3 tests after seed helper completed.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/backtest/__init__.py alpha_agent/backtest/ic_engine.py \
        tests/backtest/test_ic_engine.py
git commit -m "feat(phase6a-t7): walk-forward IC backtest + dynamic weight writer"
```

---

## Task 8: combine.py Refactor (load weights from signal_weight_current)

**Goal:** Replace hardcoded signal-weight table in `combine.py` with a load from the `signal_weight_current` DB table; signals with weight 0 (auto-dropped by T7 IC engine) drop out of composite cleanly.

**Files:**
- Modify: `alpha_agent/fusion/combine.py`
- Test: extend existing combine test or new `tests/fusion/test_combine_dynamic_weights.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/fusion/test_combine_dynamic_weights.py
import pytest

from alpha_agent.fusion.combine import combine, load_weights


@pytest.mark.asyncio
async def test_load_weights_from_db(pool):
    """signal_weight_current must drive combine weights, not a hardcoded dict."""
    await pool.execute(
        """
        INSERT INTO signal_weight_current
            (signal_name, weight, last_updated, reason)
        VALUES ($1, $2, now(), 'ic_above_threshold')
        """,
        "news", 0.045,
    )
    weights = await load_weights(pool)
    assert weights.get("news") == 0.045


@pytest.mark.asyncio
async def test_combine_drops_zero_weight_signals(pool):
    """Signals with weight 0 (auto-dropped) must not contribute."""
    await pool.execute(
        "INSERT INTO signal_weight_current(signal_name, weight, last_updated, reason) "
        "VALUES ('premarket', 0, now(), 'auto_dropped_low_ic')"
    )
    weights = await load_weights(pool)
    breakdown_in = [
        {"signal": "news", "z": 1.0, "confidence": 0.7,
         "weight_static": 0.1, "raw": {}, "source": "x"},
        {"signal": "premarket", "z": 2.0, "confidence": 0.5,
         "weight_static": 0.1, "raw": {}, "source": "x"},
    ]
    result = combine(breakdown_in, weights_override=weights)
    # premarket auto-dropped, only news contributes
    assert result["composite_score"] is not None
    pm_entry = next((b for b in result["breakdown"] if b["signal"] == "premarket"), None)
    if pm_entry:
        assert pm_entry["weight_effective"] == 0 or pm_entry["weight_effective"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/fusion/test_combine_dynamic_weights.py -v
```
Expected: FAIL (load_weights not exported or combine doesn't accept weights_override).

- [ ] **Step 3: Refactor combine.py (incremental, preserve existing API)**

Orchestrator opens `alpha_agent/fusion/combine.py`, locates the current weight table (likely a top-level dict like `_WEIGHTS = {...}`), and:

1. Adds `async def load_weights(pool) -> dict[str, float]` which selects all rows from `signal_weight_current`. If table empty (cold start before T7 first run), returns the legacy hardcoded dict.
2. Adds optional kwarg `weights_override: dict[str, float] | None = None` to `combine(...)`. When supplied, uses it; else uses the static fallback.
3. Cron handler / picks endpoint should be updated to:
   ```python
   weights = await load_weights(pool)
   composite = combine(breakdown_rows, weights_override=weights)
   ```

Keep the legacy signature (combine without weights_override) working so non-Phase-6a callers don't break.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/fusion/test_combine_dynamic_weights.py -v
```
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/fusion/combine.py tests/fusion/test_combine_dynamic_weights.py
git commit -m "feat(phase6a-t8): combine loads weights from signal_weight_current, drops 0-weight"
```

---

## Task 9: ic_backtest Cron Endpoint + Dual-Entry Register

**Goal:** Provide POST `/api/cron/ic_backtest_monthly` that invokes `run_monthly_ic_backtest` and records a stamp in `cron_runs`. Register in BOTH `app.py` AND `api/index.py` (the dual-entry rule from MEMORY).

**Files:**
- Create: `alpha_agent/api/routes/ic_backtest.py`
- Modify: `alpha_agent/api/app.py`
- Modify: `api/index.py`
- Test: `tests/api/test_ic_backtest_route.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ic_backtest_route.py
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_ic_backtest_endpoint_returns_count(app):
    """POST /api/cron/ic_backtest_monthly should invoke the engine and return
    a JSON envelope with 'signals_updated' count."""
    async def fake_run(pool):
        return 11
    with patch("alpha_agent.api.routes.ic_backtest.run_monthly_ic_backtest",
               new=fake_run):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/cron/ic_backtest_monthly")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["signals_updated"] == 11
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/api/test_ic_backtest_route.py -v
```
Expected: FAIL (route not registered).

- [ ] **Step 3: Write the route module**

```python
# alpha_agent/api/routes/ic_backtest.py
"""POST /api/cron/ic_backtest_monthly - monthly walk-forward IC backtest.

Invoked by GHA cron on the 1st of each month. Runs all active signals
through 30/60/90d backtest windows, writes results to signal_ic_history
and signal_weight_current. Auto-drops signals whose IC falls below
0.02 by setting their weight = 0; combine.py then ignores them in
composite computation until next month.

No auth (cron-only endpoint; GHA Actions IP can be ratelimited at
Vercel level later if needed).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.backtest.ic_engine import run_monthly_ic_backtest

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.post("/ic_backtest_monthly")
async def ic_backtest_monthly() -> dict[str, Any]:
    pool = await get_db_pool()
    started_at = datetime.now(UTC)
    n = await run_monthly_ic_backtest(pool)
    # Stamp cron_runs (same pattern as other cron handlers)
    await pool.execute(
        """
        INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details)
        VALUES ($1, $2, now(), true, 0, $3::jsonb)
        """,
        "ic_backtest_monthly", started_at,
        f'{{"signals_updated": {n}}}',
    )
    return {"ok": True, "signals_updated": n}
```

- [ ] **Step 4: Register in BOTH entry points (dual-entry rule)**

In `api/index.py` (under the existing `_load(...)` block):

```python
_load("ic_backtest", "alpha_agent.api.routes.ic_backtest")
```

In `alpha_agent/api/app.py` (under the existing register block):

```python
def _import_ic_backtest():
    from alpha_agent.api.routes.ic_backtest import router
    return router

_load("ic_backtest", _import_ic_backtest)
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/api/test_ic_backtest_route.py -v
```
Expected: PASS, 1 test.

- [ ] **Step 6: Commit + push (route is visible in production after this commit)**

```bash
git add alpha_agent/api/routes/ic_backtest.py \
        alpha_agent/api/app.py api/index.py \
        tests/api/test_ic_backtest_route.py
git commit -m "feat(phase6a-t9): /api/cron/ic_backtest_monthly endpoint, dual-entry"
git push
```

- [ ] **Step 7: Post-deploy verify**

After Vercel ready:
```
curl -s https://alpha.bobbyzhong.com/api/_health/routers | python3 -m json.tool | grep -A 2 ic_backtest
# expected: loaded=true
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://alpha.bobbyzhong.com/api/cron/ic_backtest_monthly
# expected: 200, body {"ok": true, "signals_updated": <int>}
```

If route 404s, the dual-entry rule was violated. Check both files registered the import.

---

## Task 10: Extend /api/_health/signals with live IC + tier

**Goal:** Add three IC window values + current weight + tier color to each signal entry returned by `/api/_health/signals`. Tier rules: green if min(ic_30d, ic_60d, ic_90d) > 0.02; yellow if 0.01 < min <= 0.02; red if dropped (weight = 0).

**Files:**
- Modify: `alpha_agent/api/routes/health.py`
- Test: `tests/api/test_health_signals_extended.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_health_signals_extended.py
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_signals_includes_ic_and_tier(app, pool):
    # Seed three IC rows for news signal
    await pool.execute(
        "INSERT INTO signal_ic_history(signal_name, window_days, ic, n_observations, computed_at) "
        "VALUES ('news', 30, 0.045, 100, now()), "
        "       ('news', 60, 0.052, 200, now()), "
        "       ('news', 90, 0.039, 300, now())"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current(signal_name, weight, last_updated, reason) "
        "VALUES ('news', 0.045, now(), 'ic_above_threshold')"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/_health/signals")
    body = r.json()
    news_entry = next(s for s in body["signals"] if s["name"] == "news")
    assert "live_ic_30d" in news_entry
    assert abs(news_entry["live_ic_30d"] - 0.045) < 1e-3
    assert news_entry["tier"] == "green"
    assert news_entry["weight_current"] == 0.045


@pytest.mark.asyncio
async def test_dropped_signal_shows_red_tier(app, pool):
    await pool.execute(
        "INSERT INTO signal_weight_current(signal_name, weight, last_updated, reason) "
        "VALUES ('premarket', 0, now(), 'auto_dropped_low_ic')"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/api/_health/signals")
    body = r.json()
    pm = next(s for s in body["signals"] if s["name"] == "premarket")
    assert pm["tier"] == "red"
    assert pm["weight_current"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/api/test_health_signals_extended.py -v
```
Expected: FAIL (fields not in response).

- [ ] **Step 3: Extend the endpoint**

Locate `/api/_health/signals` in `alpha_agent/api/routes/health.py` (it currently iterates `_SIGNAL_NAMES` returning name + last_success + last_error + error_count_24h). Add per-signal fields:

```python
# inside health_signals(), for each signal name:
ic_30d = await pool.fetchval(
    "SELECT ic FROM signal_ic_history "
    "WHERE signal_name = $1 AND window_days = 30 "
    "ORDER BY computed_at DESC LIMIT 1", name)
ic_60d = await pool.fetchval(
    "SELECT ic FROM signal_ic_history "
    "WHERE signal_name = $1 AND window_days = 60 "
    "ORDER BY computed_at DESC LIMIT 1", name)
ic_90d = await pool.fetchval(
    "SELECT ic FROM signal_ic_history "
    "WHERE signal_name = $1 AND window_days = 90 "
    "ORDER BY computed_at DESC LIMIT 1", name)
weight_row = await pool.fetchrow(
    "SELECT weight, reason FROM signal_weight_current WHERE signal_name = $1", name)
weight_current = float(weight_row["weight"]) if weight_row else None
reason = weight_row["reason"] if weight_row else None

# Tier rule
ics = [v for v in (ic_30d, ic_60d, ic_90d) if v is not None]
if reason == "auto_dropped_low_ic" or (weight_current is not None and weight_current == 0.0):
    tier = "red"
elif ics and min(ics) > 0.02:
    tier = "green"
elif ics and min(ics) > 0.01:
    tier = "yellow"
else:
    tier = "unknown"
```

Add the four new fields (`live_ic_30d`, `live_ic_60d`, `live_ic_90d`, `weight_current`, `tier`) to the SignalStatus Pydantic model. Backward compat: existing fields (`name`, `last_success`, `last_error`, `error_count_24h`) unchanged.

Also add `political_impact` to `_SIGNAL_NAMES` list at the top of the file so it appears in the response.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/api/test_health_signals_extended.py -v
```
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/health.py tests/api/test_health_signals_extended.py
git commit -m "feat(phase6a-t10): /api/_health/signals exposes live IC + tier + weight"
```

---

## Task 11: Frontend AttributionTable - IC column + tier dot + dropped grayout

**Goal:** Show users which signals are currently active vs auto-dropped, and surface the IC value driving the weight. Reuse the same data path (signals are part of card.breakdown already; add live IC by fetching `/api/_health/signals` once per page load).

**Files:**
- Modify: `frontend/src/components/stock/AttributionTable.tsx`
- Modify: `frontend/src/lib/i18n.ts` (5 new keys per locale)
- Create: `frontend/src/lib/api/signal_health.ts` (small helper to call /api/_health/signals)

- [ ] **Step 1: Read the existing AttributionTable**

Orchestrator: read `frontend/src/components/stock/AttributionTable.tsx` to understand current row structure (columns currently shown).

- [ ] **Step 2: Write the new API helper**

```typescript
// frontend/src/lib/api/signal_health.ts
import { apiGet } from "./client";

export interface SignalHealthEntry {
  name: string;
  live_ic_30d: number | null;
  live_ic_60d: number | null;
  live_ic_90d: number | null;
  weight_current: number | null;
  tier: "green" | "yellow" | "red" | "unknown";
  last_success: string | null;
  last_error: string | null;
  error_count_24h: number;
}

export const fetchSignalHealth = () =>
  apiGet<{ signals: SignalHealthEntry[] }>("/api/_health/signals");
```

- [ ] **Step 3: Modify AttributionTable to consume signal_health**

```typescript
// frontend/src/components/stock/AttributionTable.tsx (key change excerpt)

import { useEffect, useState } from "react";
import { fetchSignalHealth, type SignalHealthEntry } from "@/lib/api/signal_health";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

const TIER_DOT: Record<SignalHealthEntry["tier"], string> = {
  green:   "bg-tm-pos",
  yellow:  "bg-tm-warn",
  red:     "bg-tm-neg",
  unknown: "bg-tm-muted",
};

export default function AttributionTable({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [healthMap, setHealthMap] = useState<Record<string, SignalHealthEntry>>({});

  useEffect(() => {
    setLocale(getLocaleFromStorage());
    fetchSignalHealth().then(({ signals }) => {
      const m: Record<string, SignalHealthEntry> = {};
      for (const s of signals) m[s.name] = s;
      setHealthMap(m);
    }).catch(() => {});
  }, []);

  return (
    <table>
      <thead>
        <tr>
          <th>{t(locale, "attribution.signal")}</th>
          <th>{t(locale, "attribution.z")}</th>
          <th>{t(locale, "attribution.contribution")}</th>
          <th>{t(locale, "attribution.live_ic")}</th>
          <th>{t(locale, "attribution.tier")}</th>
        </tr>
      </thead>
      <tbody>
        {card.breakdown.map((b) => {
          const h = healthMap[b.signal];
          const isDropped = h?.tier === "red" || h?.weight_current === 0;
          return (
            <tr key={b.signal} className={isDropped ? "opacity-40" : ""}>
              <td>{b.signal}</td>
              <td>{b.z?.toFixed(2) ?? "-"}</td>
              <td>{b.contribution?.toFixed(3) ?? "-"}</td>
              <td>{h?.live_ic_30d?.toFixed(3) ?? "-"}</td>
              <td>
                <span className={`inline-block h-2 w-2 rounded-full ${TIER_DOT[h?.tier ?? "unknown"]}`}
                      title={isDropped ? t(locale, "attribution.dropped_tooltip") : ""}/>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Add 5 i18n keys per locale**

```typescript
// frontend/src/lib/i18n.ts (zh block, in attribution.* section if exists, else above news.*)
"attribution.signal": "信号",
"attribution.z": "z",
"attribution.contribution": "贡献",
"attribution.live_ic": "live IC (30d)",
"attribution.tier": "tier",
"attribution.dropped_tooltip": "本周期 IC < 0.02 自动 drop,weight = 0",
```

```typescript
// en block
"attribution.signal": "Signal",
"attribution.z": "z",
"attribution.contribution": "Contribution",
"attribution.live_ic": "Live IC (30d)",
"attribution.tier": "Tier",
"attribution.dropped_tooltip": "Auto-dropped this cycle (IC < 0.02, weight = 0)",
```

- [ ] **Step 5: Verify TypeScript + ESLint**

```
cd frontend && npx tsc --noEmit && npx next lint --max-warnings 0
```
Expected: 0 errors / 0 warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/stock/AttributionTable.tsx \
        frontend/src/lib/api/signal_health.ts \
        frontend/src/lib/i18n.ts
git commit -m "feat(phase6a-t11): AttributionTable shows live IC + tier dot + dropped grayout"
```

---

## Task 12: Frontend AttributionRadar - Political vs Macro (Vol) disambiguate

**Goal:** Avoid confusion between existing `macro` signal (VIX / volatility) and the new `political_impact` signal. Display labels are renamed; backend signal names retained.

**Files:**
- Modify: `frontend/src/components/stock/AttributionRadar.tsx`
- Modify: `frontend/src/lib/i18n.ts` (2 new keys per locale)

- [ ] **Step 1: Read the existing radar component**

Orchestrator: read `AttributionRadar.tsx` to find where the signal name is rendered on the polygon vertex label.

- [ ] **Step 2: Add display-label mapping**

```typescript
// At top of AttributionRadar.tsx
const SIGNAL_DISPLAY_LABEL: Record<string, string> = {
  macro: "Macro (Vol)",
  political_impact: "Political",
};

function displayName(signalName: string, locale: Locale): string {
  // First check i18n (allows zh translation), then fallback to English alias map.
  const key = `attribution.signal_label_${signalName}`;
  const translated = t(locale, key);
  if (translated !== key) return translated;
  return SIGNAL_DISPLAY_LABEL[signalName] ?? signalName;
}

// Replace any vertex label render that previously used signalName directly
// with displayName(signalName, locale).
```

- [ ] **Step 3: Add 2 i18n keys per locale**

```typescript
// zh block
"attribution.signal_label_macro": "宏观 (波动率)",
"attribution.signal_label_political_impact": "政治",
```

```typescript
// en block
"attribution.signal_label_macro": "Macro (Vol)",
"attribution.signal_label_political_impact": "Political",
```

- [ ] **Step 4: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npx next lint --max-warnings 0
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stock/AttributionRadar.tsx frontend/src/lib/i18n.ts
git commit -m "feat(phase6a-t12): radar renames macro to Macro (Vol), adds Political vertex"
```

---

## Task 13: GHA cron-shards.yml - add 2 new jobs

**Goal:** Schedule `minute_bars_puller` (every 4h market hours, segmented 8 shots) + `ic_backtest_monthly` (1st of month 04:00 UTC).

**Files:**
- Modify: `.github/workflows/cron-shards.yml`

- [ ] **Step 1: Add two new schedule lines**

Under the existing `on.schedule:` list:

```yaml
    # Minute bars puller for event-study CAR, every 4h during market hours
    - cron: '15 14,18 * * 1-5'
    # IC backtest monthly, 1st of month 04:00 UTC
    - cron: '0 4 1 * *'
```

- [ ] **Step 2: Add two new workflow_dispatch input options**

```yaml
        options:
          ...existing...
          - minute_bars_puller
          - ic_backtest_monthly
```

- [ ] **Step 3: Add two new jobs**

```yaml
  minute_bars_puller:
    if: |
      github.event.schedule == '15 14,18 * * 1-5' ||
      (github.event_name == 'workflow_dispatch' && inputs.job == 'minute_bars_puller')
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: pull SP500 minute bars (8 shots x limit=75)
        run: |
          set -e
          for offset in 0 75 150 225 300 375 450 525; do
            HTTP=$(curl -s --max-time 290 -o /tmp/shot.json -w "%{http_code}" \
              "$BACKEND_BASE/api/cron/minute_bars?limit=75&offset=$offset")
            echo "offset=$offset HTTP=$HTTP"
            cat /tmp/shot.json | head -c 200; echo
            [ "$HTTP" = "200" ] || exit 1
            sleep 10
          done

  ic_backtest_monthly:
    if: |
      github.event.schedule == '0 4 1 * *' ||
      (github.event_name == 'workflow_dispatch' && inputs.job == 'ic_backtest_monthly')
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: monthly walk-forward IC backtest
        run: |
          HTTP=$(curl -s --max-time 600 -o /tmp/shot.json -w "%{http_code}" \
            -X POST "$BACKEND_BASE/api/cron/ic_backtest_monthly")
          cat /tmp/shot.json | head -c 400; echo
          [ "$HTTP" = "200" ] || exit 1
```

The `minute_bars_puller` step depends on a `/api/cron/minute_bars` endpoint that loops over a slice of tickers and calls `pull_and_store_minute_bars` for each. Orchestrator: this endpoint is a wrapper similar to existing news cron handlers — add it in `alpha_agent/api/routes/cron_routes.py` calling into a new helper in `api/cron/minute_bars_handler.py`. Small adjacent task, ~20 min.

- [ ] **Step 4: Validate YAML syntax**

```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/cron-shards.yml'))" && echo OK
```
Expected: OK.

- [ ] **Step 5: Commit + push**

```bash
git add .github/workflows/cron-shards.yml \
        alpha_agent/api/routes/cron_routes.py \
        api/cron/minute_bars_handler.py
git commit -m "feat(phase6a-t13): GHA cron jobs for minute_bars puller + monthly IC backtest"
git push
```

- [ ] **Step 6: Manually trigger once via gh CLI to verify**

```
gh workflow run cron-shards.yml --repo zzzhhn/alpha-agent --field job=minute_bars_puller
sleep 30
gh run list --workflow=cron-shards.yml --limit 1
# verify status success
```

---

## Task 14: Pre-publish IC Gate + E2E Acceptance

**Goal:** Verify the spec's 6 end-to-end acceptance criteria pass. Run dry-run IC backtest on news + political_impact and confirm IC > 0.02 across all 3 windows before declaring them publishable.

**Files:** (no new files, this is a verification ritual)

- [ ] **Step 1: Manually trigger ic_backtest_monthly once**

```
curl -X POST https://alpha.bobbyzhong.com/api/cron/ic_backtest_monthly
# expect: {"ok": true, "signals_updated": <= 11}
```

- [ ] **Step 2: Verify all 6 acceptance criteria from spec**

| # | Check | Command |
|---|---|---|
| 1 | /api/_health/signals returns 11 entries with IC populated | `curl -s alpha.bobbyzhong.com/api/_health/signals | python3 -m json.tool | grep -c live_ic_30d` |
| 2 | news + political_impact both tier=green | `... | grep -B 1 -A 6 '"news"\|"political_impact"' | grep tier` |
| 3 | Stock page AttributionTable shows IC column | Open browser, verify visually |
| 4 | TSLA with Trump truth in last 7d moves composite by >= 0.05 | Run two queries: with vs without political_impact in breakdown, compare composite_score |
| 5 | Monthly cron success | `gh run list --workflow=cron-shards.yml --limit 1` shows ic_backtest_monthly success |
| 6 | Simulate news IC drop -> weight auto-drops | Insert synthetic low-IC rows into signal_ic_history, rerun ic_backtest, verify signal_weight_current.news = 0 |

- [ ] **Step 3: If any criterion fails, file as Phase 6a-blocker bug, do not declare done**

Phase 6a is only DONE when all 6 criteria pass and `git log --oneline phase6a` shows T1 through T14 commits.

- [ ] **Step 4: Final commit + tag (only after all green)**

```bash
git tag phase6a-acceptance-passed
git push --tags
```

---

## Risk Mitigation Checklist

| Risk (from spec) | Plan-level mitigation |
|---|---|
| yfinance 1m only 7-30d, most backfill events not event-study eligible | T2's `get_bars_for_event` returns empty for events > 30d; T3 CAR returns None; T5/T6 fall back to Tetlock daily aggregation cleanly |
| Walk-forward IC lookahead bias | T7's `compute_walk_forward_ic` SQL uses `s.as_of + interval '5 days'` for forward return, never `now()`; test_walk_forward_ic_strict_lookahead_free locks the behavior |
| Political vs Macro confusion | T12 adds display-label override; backend signal names retained |
| LM-only IC < 0.02 -> false signal death | T7 currently merges LLM + LM into one IC; P6b backlog item: split into separate signal_ic_history rows for analysis |
| Monthly cron silent fail | T9 stamps cron_runs; T10 surfaces last_updated via /api/_health/signals tier; alert if last_updated > 35d |
| Sector-conditional political_impact IC | Out of scope for 6a; P6b backlog (introduce sector-conditional weight engine) |

---

## DONE Criteria (Plan-Level)

Phase 6a plan execution is DONE when:

1. All 14 tasks committed in order on main branch
2. All 14 task-level tests pass
3. All 6 spec acceptance criteria pass post-deploy
4. `phase6a-acceptance-passed` git tag pushed
5. The 5 open questions from spec are resolved in commit messages or follow-up commits
6. MEMORY.md indexed with 1-2 new feedback entries if any surprising blockers surfaced during implementation

---




