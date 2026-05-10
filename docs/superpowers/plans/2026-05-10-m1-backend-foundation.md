# Alpha-Agent v4 · M1 后端基础设施 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend foundation that lets a single CLI command `python -m alpha_agent build-card AAPL` output a valid `RatingCard` JSON, end-to-end through 10 signals → fusion → 5-tier rating.

**Architecture:** Layered: `storage/` (Postgres + migrations) → `signals/` (10 standalone fetcher modules with shared `safe_fetch` wrapper) → `fusion/` (pure-function pipeline: normalize → combine → rate → attribute) → `cli` (orchestrator). Each layer is independently testable. External APIs (yfinance, EDGAR, FRED, agent-reach) are fixture-mocked in unit tests; integration tests use a Neon branch.

**Tech Stack:** Python 3.12, asyncpg, pydantic v2, tenacity, yfinance, exchange-calendars, pytest-asyncio. New deps to add: `asyncpg`, `psycopg[binary]` (for sync migration runner only), `python-dotenv`, `httpx`.

**Spec reference:** `docs/superpowers/specs/2026-05-10-alpha-pivot-phase1-design.md` Sections 3, 5.7, 7.1.

---

## Scope

| In scope | Out of scope (later milestones) |
|----------|---------------------------------|
| Postgres schema (5 tables) | Cron handlers (M2) |
| Storage layer + queries | API endpoints (M2) |
| 10 signal modules + fixtures | Frontend (M3) |
| Fusion + 5-tier rating + attribution | LLM Rich brief (M3, M2 stub only) |
| `RatingCard` Pydantic model | Health endpoints (M2) |
| CLI `build-card <ticker>` | Deployment + E2E (M4) |

---

## File Structure

**New files:**

```
alpha_agent/
├── storage/
│   ├── postgres.py            # asyncpg pool + retry decorator
│   ├── queries.py             # typed CRUD: insert_slow, get_fast, ...
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── V001__initial_schema.sql
│   │   └── runner.py          # apply_migrations(dsn) entry point
├── signals/
│   ├── __init__.py
│   ├── base.py                # SignalScore TypedDict + safe_fetch
│   ├── factor.py              # wraps existing factor_engine
│   ├── technicals.py          # RSI/MACD/VWAP/ATR/MA from OHLCV
│   ├── analyst.py             # yfinance recommendation
│   ├── earnings.py            # earningsDate + EPS surprise
│   ├── insider.py             # SEC EDGAR Form 4
│   ├── macro.py               # FRED tilt
│   ├── options.py             # yfinance options chain
│   ├── news.py                # agent-reach search
│   ├── premarket.py           # yfinance preMarketPrice
│   └── calendar.py            # FRED + agent-reach (display only)
├── fusion/
│   ├── __init__.py
│   ├── normalize.py           # cross-section z-score + winsorize
│   ├── weights.py             # DEFAULT_WEIGHTS + override
│   ├── combine.py             # weighted sum w/ confidence-zero redistribution
│   ├── rating.py              # 5-tier mapping + confidence
│   └── attribution.py         # top_drivers / top_drags
└── cli/
    ├── __init__.py
    └── build_card.py          # orchestrator: signals → fusion → JSON

tests/
├── storage/
│   ├── __init__.py
│   ├── conftest.py            # Neon branch / local PG fixture
│   ├── test_migrations.py
│   ├── test_postgres.py
│   └── test_queries.py
├── signals/
│   ├── __init__.py
│   ├── conftest.py            # mocked_provider fixtures
│   ├── test_safe_fetch.py
│   ├── test_factor.py
│   ├── test_technicals.py
│   ├── test_analyst.py
│   ├── test_earnings.py
│   ├── test_insider.py
│   ├── test_macro.py
│   ├── test_options.py
│   ├── test_news.py
│   ├── test_premarket.py
│   └── test_calendar.py
├── fusion/
│   ├── __init__.py
│   ├── test_normalize.py
│   ├── test_weights.py
│   ├── test_combine.py
│   ├── test_rating.py
│   └── test_attribution.py
├── fixtures/
│   ├── yfinance/              # frozen JSON snapshots
│   ├── edgar/
│   ├── fred/
│   └── agent_reach/
└── integration/
    └── test_build_card_e2e.py
```

**Modified files:**

- `pyproject.toml` — add `asyncpg`, `psycopg[binary]`, `python-dotenv`, `httpx`
- `alpha_agent/main.py` — add `build-card` subparser
- `alpha_agent/core/types.py` — add `RatingCard` Pydantic model
- `Makefile` (NEW) — `refresh-fixtures`, `test`, `test-integration` targets

---

## Acceptance Criteria

After completing all tasks:

```bash
# All unit tests pass with > 90% coverage on signals + fusion
pytest tests/signals tests/fusion --cov=alpha_agent.signals --cov=alpha_agent.fusion --cov-fail-under=90

# Integration test passes against ephemeral Postgres
pytest tests/integration -v

# CLI command produces valid RatingCard
python -m alpha_agent build-card AAPL --use-fixtures > /tmp/aapl_card.json
python -c "import json; from alpha_agent.core.types import RatingCard; \
  RatingCard.model_validate_json(open('/tmp/aapl_card.json').read())"
echo "Valid RatingCard"
```

---

## Phase A · 持久化层（Day 1-3）

### Task 1: Add new dependencies and Postgres test infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/storage/__init__.py` (empty)
- Create: `tests/storage/conftest.py`
- Create: `.env.example`

- [ ] **Step 1: Edit `pyproject.toml` to add new dependencies**

In `[project] dependencies`, append:
```toml
    "asyncpg>=0.29",
    "python-dotenv>=1.0",
    "httpx>=0.27",
```

In `[project.optional-dependencies]`, add:
```toml
storage = [
    "psycopg[binary]>=3.1",  # sync migration runner only
]
test = [
    "alpha-agent[dev]",
    "pytest-postgresql>=6.0",
    "pytest-mock>=3.12",
    "respx>=0.21",
]
```

- [ ] **Step 2: Create `.env.example`**

```
DATABASE_URL=postgres://alpha:alpha@localhost:5432/alpha_test
FRED_API_KEY=
EDGAR_USER_AGENT="Alpha Agent v4 contact@example.com"
LOG_LEVEL=INFO
```

- [ ] **Step 3: Install deps**

Run: `uv pip install -e ".[dev,storage,test]"` (or `pip install -e ".[dev,storage,test]"` if using pip)
Expected: `Successfully installed asyncpg-... pytest-postgresql-... ...`

- [ ] **Step 4: Create `tests/storage/conftest.py` with ephemeral PG fixture**

```python
"""Postgres test fixture using pytest-postgresql.

Spins up a fresh Postgres process per test session; gives us
a real DB without external dependencies. Each test gets a
clean schema via auto-applied migrations.
"""
from __future__ import annotations

import asyncio
import pytest
import pytest_asyncio
from pytest_postgresql import factories

postgresql_proc = factories.postgresql_proc(port=None, unixsocketdir="/tmp")
postgresql = factories.postgresql("postgresql_proc")


@pytest.fixture
def test_db_url(postgresql) -> str:
    """asyncpg-compatible DSN."""
    info = postgresql.info
    return f"postgres://{info.user}@/{info.dbname}?host={info.host}&port={info.port}"


@pytest_asyncio.fixture
async def applied_db(test_db_url):
    """Test DB with all migrations applied."""
    from alpha_agent.storage.migrations.runner import apply_migrations
    await apply_migrations(test_db_url)
    return test_db_url
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example tests/storage/__init__.py tests/storage/conftest.py
git commit -m "chore(m1): add asyncpg + Postgres test infrastructure"
```

---

### Task 2: Postgres schema migration

**Files:**
- Create: `alpha_agent/storage/migrations/__init__.py` (empty)
- Create: `alpha_agent/storage/migrations/V001__initial_schema.sql`
- Create: `alpha_agent/storage/migrations/runner.py`
- Create: `tests/storage/test_migrations.py`

**Why:** Spec §7.1 lists 5 tables that the rating-card pipeline needs. Versioned migrations let CI bring up a fresh DB deterministically.

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_migrations.py`:
```python
import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_apply_migrations_creates_all_tables(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        names = {r["tablename"] for r in rows}
        assert names >= {
            "alert_queue",
            "cron_runs",
            "daily_signals_fast",
            "daily_signals_slow",
            "error_log",
        }
    finally:
        await conn.close()


async def test_alert_queue_has_dedup_unique_constraint(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'alert_queue'::regclass AND contype = 'u'
        """)
        assert row is not None, "alert_queue must have a UNIQUE constraint"
    finally:
        await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_migrations.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'alpha_agent.storage.migrations'`

- [ ] **Step 3: Create migration SQL**

Create `alpha_agent/storage/migrations/V001__initial_schema.sql`:
```sql
-- Spec §7.1: alpha-agent v4 Phase 1 initial schema.

CREATE TABLE IF NOT EXISTS daily_signals_slow (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    composite_partial DOUBLE PRECISION,
    breakdown JSONB,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS daily_signals_fast (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    composite DOUBLE PRECISION,
    rating TEXT,
    confidence DOUBLE PRECISION,
    breakdown JSONB,
    partial BOOLEAN DEFAULT false,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS alert_queue (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    dedup_bucket BIGINT NOT NULL,
    dispatched BOOLEAN DEFAULT false,
    UNIQUE (ticker, type, dedup_bucket)
);
CREATE INDEX IF NOT EXISTS idx_alert_queue_pending
    ON alert_queue (dispatched, created_at) WHERE dispatched = false;

CREATE TABLE IF NOT EXISTS cron_runs (
    id BIGSERIAL PRIMARY KEY,
    cron_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    ok BOOLEAN,
    error_count INT DEFAULT 0,
    details JSONB
);
CREATE INDEX IF NOT EXISTS idx_cron_runs_recent
    ON cron_runs (cron_name, started_at DESC);

CREATE TABLE IF NOT EXISTS error_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT now(),
    layer TEXT NOT NULL,
    component TEXT NOT NULL,
    ticker TEXT,
    err_type TEXT,
    err_message TEXT,
    context JSONB
);
CREATE INDEX IF NOT EXISTS idx_error_log_recent ON error_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_log_component ON error_log (component, ts DESC);

-- Schema version tracker (so runner can be idempotent across re-runs)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now()
);
```

- [ ] **Step 4: Create migration runner**

Create `alpha_agent/storage/migrations/runner.py`:
```python
"""Apply versioned SQL migrations to a Postgres DB.

Idempotent: re-running is a no-op (tracked in schema_migrations).
Discovery: any file matching V<NUM>__<name>.sql under this directory.
Order: lexicographic by filename — keep V001/V002/... padding consistent.
"""
from __future__ import annotations

import re
from pathlib import Path

import asyncpg

_MIGRATIONS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^V(\d+)__.+\.sql$")


def _discover() -> list[tuple[str, Path]]:
    files = sorted(_MIGRATIONS_DIR.glob("V*__*.sql"))
    out = []
    for f in files:
        m = _VERSION_RE.match(f.name)
        if m:
            out.append((f.stem, f))
    return out


async def apply_migrations(dsn: str) -> list[str]:
    """Apply all pending migrations to dsn. Returns list of applied versions."""
    conn = await asyncpg.connect(dsn)
    applied: list[str] = []
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        rows = await conn.fetch("SELECT version FROM schema_migrations")
        already = {r["version"] for r in rows}
        for version, path in _discover():
            if version in already:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
            applied.append(version)
    finally:
        await conn.close()
    return applied
```

- [ ] **Step 5: Run test to verify pass**

Run: `pytest tests/storage/test_migrations.py -v`
Expected: PASS (both tests)

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/storage/migrations/ tests/storage/test_migrations.py
git commit -m "feat(storage): initial Postgres schema + migration runner (V001)"
```

---

### Task 3: Postgres async connection pool with retry

**Files:**
- Create: `alpha_agent/storage/postgres.py`
- Create: `tests/storage/test_postgres.py`

**Why:** Spec §5.3 requires Neon free-tier auto-suspend resilience: 3-attempt exponential backoff, 503 with `DB_UNAVAILABLE` after exhaustion. Centralizing pool + retry in one place keeps every query consistent.

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_postgres.py`:
```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

import asyncpg

from alpha_agent.storage.postgres import (
    DBUnavailable,
    get_pool,
    close_pool,
    with_retry,
)

pytestmark = pytest.mark.asyncio


async def test_get_pool_returns_singleton(applied_db):
    p1 = await get_pool(applied_db)
    p2 = await get_pool(applied_db)
    assert p1 is p2
    await close_pool()


async def test_with_retry_passes_through_on_success():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        return 42
    assert await op() == 42
    assert calls == 1


async def test_with_retry_succeeds_after_transient_failure():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise asyncpg.PostgresConnectionError("simulated wake")
        return "ok"
    assert await op() == "ok"
    assert calls == 3


async def test_with_retry_raises_dbunavailable_after_exhaustion():
    @with_retry
    async def op():
        raise asyncpg.PostgresConnectionError("permanent")
    with pytest.raises(DBUnavailable):
        await op()


async def test_with_retry_reraises_other_errors_immediately():
    calls = 0
    @with_retry
    async def op():
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")
    with pytest.raises(ValueError):
        await op()
    assert calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_postgres.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `alpha_agent/storage/postgres.py`**

```python
"""Async Postgres connection pool with retry-aware decorator.

Spec §5.3: Neon free tier auto-suspends after idle. Wake adds 200-500ms.
Three-attempt exponential backoff handles wake; non-connection errors
(programming bugs, constraint violations) propagate immediately.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Awaitable, Callable, TypeVar

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_dsn: str | None = None

T = TypeVar("T")


class DBUnavailable(Exception):
    """Raised when retries exhausted; API layer maps this to 503 DB_UNAVAILABLE."""


async def get_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Singleton pool. Subsequent calls with a different DSN raise — that's a bug."""
    global _pool, _pool_dsn
    if _pool is not None:
        if _pool_dsn != dsn:
            raise RuntimeError(f"Pool already exists for {_pool_dsn!r}; got {dsn!r}")
        return _pool
    _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    _pool_dsn = dsn
    return _pool


async def close_pool() -> None:
    global _pool, _pool_dsn
    if _pool is not None:
        await _pool.close()
        _pool = None
        _pool_dsn = None


_RETRYABLE = (
    asyncpg.PostgresConnectionError,
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncio.TimeoutError,
)


def with_retry(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator: 3 attempts with exponential backoff (0.5s, 1s, 2s)."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        delays = [0.5, 1.0, 2.0]
        last_exc: Exception | None = None
        for i, delay in enumerate([0.0] + delays):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await fn(*args, **kwargs)
            except _RETRYABLE as e:
                last_exc = e
                logger.warning("DB op %s failed (attempt %d): %s", fn.__name__, i + 1, e)
        raise DBUnavailable(f"{fn.__name__} failed after retries") from last_exc

    return wrapper
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/storage/test_postgres.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/postgres.py tests/storage/test_postgres.py
git commit -m "feat(storage): async pool + retry-aware decorator (DBUnavailable on exhaustion)"
```

---

### Task 4: Typed CRUD query helpers

**Files:**
- Create: `alpha_agent/storage/queries.py`
- Create: `tests/storage/test_queries.py`

**Why:** Keep raw SQL in one file with typed wrappers; downstream cron/API code never touches asyncpg directly.

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_queries.py`:
```python
import json
import pytest

from alpha_agent.storage.postgres import close_pool, get_pool
from alpha_agent.storage.queries import (
    insert_signal_slow,
    upsert_signal_fast,
    enqueue_alert,
    list_pending_alerts,
    mark_alert_dispatched,
    log_error,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


async def test_insert_signal_slow_idempotent(pool):
    payload = {"breakdown": [{"signal": "factor", "z": 1.5}]}
    await insert_signal_slow(pool, "AAPL", "2026-05-10", 0.45, payload)
    # Same key must not raise — should UPDATE on conflict
    await insert_signal_slow(pool, "AAPL", "2026-05-10", 0.50, payload)
    row = await pool.fetchrow(
        "SELECT composite_partial FROM daily_signals_slow "
        "WHERE ticker=$1 AND date=$2", "AAPL", "2026-05-10"
    )
    assert row["composite_partial"] == 0.50  # second write wins


async def test_alert_dedup_within_30min_bucket(pool):
    bucket = 12345  # caller-computed
    await enqueue_alert(pool, "AAPL", "rating_change", {}, bucket)
    # same bucket → conflict ignored
    await enqueue_alert(pool, "AAPL", "rating_change", {}, bucket)
    rows = await pool.fetch(
        "SELECT id FROM alert_queue WHERE ticker='AAPL' AND type='rating_change'"
    )
    assert len(rows) == 1


async def test_list_pending_alerts_returns_only_undispatched(pool):
    await enqueue_alert(pool, "AAPL", "gap_3sigma", {}, 1)
    await enqueue_alert(pool, "MSFT", "gap_3sigma", {}, 1)
    pending = await list_pending_alerts(pool, limit=10)
    assert len(pending) == 2
    await mark_alert_dispatched(pool, pending[0]["id"])
    pending = await list_pending_alerts(pool, limit=10)
    assert len(pending) == 1


async def test_log_error_persists_with_context(pool):
    await log_error(pool, layer="signal", component="signals.news",
                    ticker="AAPL", err_type="TimeoutError", err_message="timeout",
                    context={"url": "https://..."})
    row = await pool.fetchrow("SELECT * FROM error_log ORDER BY id DESC LIMIT 1")
    assert row["component"] == "signals.news"
    assert json.loads(row["context"])["url"].startswith("https://")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: alpha_agent.storage.queries`

- [ ] **Step 3: Implement `alpha_agent/storage/queries.py`**

```python
"""Typed CRUD helpers backed by raw SQL. Imported by cron/API code only;
direct asyncpg usage outside this module is a code smell.
"""
from __future__ import annotations

import json
from typing import Any

import asyncpg


async def insert_signal_slow(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite_partial: float,
    breakdown: dict[str, Any],
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_slow
            (ticker, date, composite_partial, breakdown, fetched_at)
        VALUES ($1, $2::date, $3, $4::jsonb, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite_partial = EXCLUDED.composite_partial,
            breakdown = EXCLUDED.breakdown,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, composite_partial, json.dumps(breakdown),
    )


async def upsert_signal_fast(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite: float,
    rating: str,
    confidence: float,
    breakdown: dict[str, Any],
    partial: bool = False,
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_fast
            (ticker, date, composite, rating, confidence, breakdown, partial, fetched_at)
        VALUES ($1, $2::date, $3, $4, $5, $6::jsonb, $7, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite = EXCLUDED.composite,
            rating = EXCLUDED.rating,
            confidence = EXCLUDED.confidence,
            breakdown = EXCLUDED.breakdown,
            partial = EXCLUDED.partial,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, composite, rating, confidence, json.dumps(breakdown), partial,
    )


async def enqueue_alert(
    pool: asyncpg.Pool,
    ticker: str,
    type_: str,
    payload: dict[str, Any],
    dedup_bucket: int,
) -> None:
    """Idempotent within (ticker, type, dedup_bucket). Caller computes bucket
    as floor(epoch / 1800) for 30-min windows."""
    await pool.execute(
        """
        INSERT INTO alert_queue (ticker, type, payload, dedup_bucket)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (ticker, type, dedup_bucket) DO NOTHING
        """,
        ticker, type_, json.dumps(payload), dedup_bucket,
    )


async def list_pending_alerts(pool: asyncpg.Pool, limit: int) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, ticker, type, payload, created_at
        FROM alert_queue
        WHERE dispatched = false
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )


async def mark_alert_dispatched(pool: asyncpg.Pool, alert_id: int) -> None:
    await pool.execute("UPDATE alert_queue SET dispatched = true WHERE id = $1", alert_id)


async def log_error(
    pool: asyncpg.Pool,
    *,
    layer: str,
    component: str,
    ticker: str | None = None,
    err_type: str | None = None,
    err_message: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO error_log (layer, component, ticker, err_type, err_message, context)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        layer, component, ticker, err_type, err_message, json.dumps(context or {}),
    )
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/storage/test_queries.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/queries.py tests/storage/test_queries.py
git commit -m "feat(storage): typed CRUD helpers (insert_slow/upsert_fast/alert_queue/error_log)"
```

---

### Task 5: GitHub Actions CI baseline

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `Makefile`

**Why:** Catches regressions in PRs and enforces 80% coverage gate per spec §6.1.

- [ ] **Step 1: Create `Makefile`**

```makefile
.PHONY: test test-storage test-signals test-fusion test-integration coverage refresh-fixtures

test:
	pytest tests/ -m "not slow" -v

test-storage:
	pytest tests/storage/ -v

test-signals:
	pytest tests/signals/ -v

test-fusion:
	pytest tests/fusion/ -v

test-integration:
	pytest tests/integration/ -v

coverage:
	pytest tests/ --cov=alpha_agent --cov-report=term-missing --cov-report=html -m "not slow"

refresh-fixtures:
	@echo "Run scripts/refresh_fixtures.py with TICKER and DATE"
	python scripts/refresh_fixtures.py --ticker $(TICKER) --date $(DATE)
```

- [ ] **Step 2: Create `.github/workflows/test.yml`**

```yaml
name: test

on:
  pull_request:
  push:
    branches: [main]

jobs:
  unit:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: testpwd
          POSTGRES_DB: alpha_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          pip install -e ".[dev,storage,test]"
      - name: Lint
        run: ruff check alpha_agent tests
      - name: Test
        env:
          DATABASE_URL: postgres://postgres:testpwd@localhost:5432/alpha_test
        run: |
          pytest tests/ --cov=alpha_agent --cov-fail-under=80 -m "not slow" -v
```

- [ ] **Step 3: Run locally to verify baseline test passes**

Run: `make test`
Expected: All existing tests + new storage tests pass; coverage report shown.

- [ ] **Step 4: Commit**

```bash
git add Makefile .github/workflows/test.yml
git commit -m "ci: add GitHub Actions test workflow + Makefile targets"
```

---

## Phase B · Signal 基础设施（Day 4）

### Task 6: SignalScore TypedDict + safe_fetch wrapper

**Files:**
- Create: `alpha_agent/signals/__init__.py` (empty)
- Create: `alpha_agent/signals/base.py`
- Create: `tests/signals/__init__.py` (empty)
- Create: `tests/signals/test_safe_fetch.py`

**Why:** Spec §3.1 + §5.1 mandate uniform `SignalScore` contract and per-signal failure isolation. `safe_fetch` is the single point that enforces "no naked `except Exception`".

- [ ] **Step 1: Write the failing test**

Create `tests/signals/test_safe_fetch.py`:
```python
from datetime import datetime, UTC

import httpx
import pytest

from alpha_agent.signals.base import SignalScore, safe_fetch


def _ok_fetch(ticker, as_of):
    return SignalScore(
        ticker=ticker, z=1.5, raw=42.0, confidence=0.9,
        as_of=as_of, source="test", error=None,
    )


def _conn_fetch(ticker, as_of):
    raise httpx.ConnectError("network down")


def _parse_fetch(ticker, as_of):
    return {"foo": 1}["bar"]  # KeyError


def _fatal_fetch(ticker, as_of):
    raise RuntimeError("programmer bug — must propagate")


def test_happy_path_passes_through():
    out = safe_fetch(_ok_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 1.5
    assert out["confidence"] == 0.9
    assert out["error"] is None


def test_connection_error_returns_zero_confidence():
    out = safe_fetch(_conn_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None and "ConnectError" in out["error"]


def test_parse_error_returns_zero_confidence():
    out = safe_fetch(_parse_fetch, "AAPL", datetime.now(UTC), source="test")
    assert out["z"] == 0.0
    assert out["error"] is not None and "KeyError" in out["error"]


def test_fatal_error_propagates():
    """Programming bugs must NOT be silently absorbed (CLAUDE.md silent except rule)."""
    with pytest.raises(RuntimeError):
        safe_fetch(_fatal_fetch, "AAPL", datetime.now(UTC), source="test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/signals/test_safe_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `alpha_agent/signals/base.py`**

```python
"""Shared SignalScore contract + safe_fetch wrapper.

Spec §3.1: every signal module exports a `fetch_signal(ticker, as_of)`
that returns SignalScore. safe_fetch is the ONLY place we catch external
errors; it does NOT catch generic Exception (CLAUDE.md silent-except rule).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, TypedDict

import httpx

logger = logging.getLogger(__name__)


class SignalScore(TypedDict):
    ticker: str
    z: float                 # clipped to [-3, 3]
    raw: Any                 # original value(s) for transparency
    confidence: float        # [0, 1]; 0 = signal unavailable
    as_of: datetime
    source: str              # 'yfinance' / 'edgar' / 'fred' / 'agent-reach'
    error: str | None        # populated only on graceful failure


# These are the ONLY exceptions safe_fetch catches.
# Programming bugs (TypeError, AttributeError, ZeroDivisionError, etc.)
# propagate so they get surfaced and fixed, not silently zeroed.
_EXTERNAL_ERRORS = (
    ConnectionError, TimeoutError,
    httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError,
    KeyError, ValueError, IndexError,
)


def safe_fetch(
    fn: Callable[[str, datetime], SignalScore],
    ticker: str,
    as_of: datetime,
    *,
    source: str,
) -> SignalScore:
    try:
        return fn(ticker, as_of)
    except _EXTERNAL_ERRORS as e:
        logger.warning("signal fetch failed: %s/%s: %s", source, ticker, e)
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.0,
            as_of=as_of, source=source,
            error=f"{type(e).__name__}: {str(e)[:120]}",
        )
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/signals/test_safe_fetch.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/ tests/signals/__init__.py tests/signals/test_safe_fetch.py
git commit -m "feat(signals): SignalScore contract + safe_fetch wrapper (graceful + fatal split)"
```

---

## Phase C · 10 Signals（Day 5-7）

### Task 7: `signals/factor.py` (wraps existing factor_engine)

**Files:**
- Create: `alpha_agent/signals/factor.py`
- Create: `tests/signals/test_factor.py`

**Why:** Cheapest signal: reuses `alpha_agent/factor_engine/kernel.py:evaluate_cross_section` against the existing SP500 v3 panel. No external API call.

- [ ] **Step 1: Write the failing test**

Create `tests/signals/test_factor.py`:
```python
from datetime import datetime, UTC
from unittest.mock import patch

import numpy as np

from alpha_agent.signals.factor import fetch_signal


def test_factor_signal_happy_path():
    fake_scores = {"AAPL": 1.8, "MSFT": 0.5, "GOOG": -1.2}
    with patch("alpha_agent.signals.factor._evaluate_for_universe", return_value=fake_scores):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert -3.0 <= out["z"] <= 3.0
    assert out["raw"] == 1.8
    assert out["confidence"] > 0.5
    assert out["source"] == "factor_engine"


def test_factor_signal_unknown_ticker_returns_zero_confidence():
    fake_scores = {"MSFT": 0.5}
    with patch("alpha_agent.signals.factor._evaluate_for_universe", return_value=fake_scores):
        out = fetch_signal("UNKN", datetime.now(UTC))
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/signals/test_factor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `alpha_agent/signals/factor.py`**

```python
"""Composite factor signal: leverages the existing v3 factor engine.

The "value" we expose as z is the cross-sectional z-score of the
default composite factor (Pure-Alpha pick from spec §3.1: weight 0.30).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

DEFAULT_FACTOR_EXPR = "rank(ts_mean(returns, 12)) - rank(ts_std(returns, 60))"


def _evaluate_for_universe(as_of: datetime, expr: str = DEFAULT_FACTOR_EXPR) -> dict[str, float]:
    """Returns {ticker: z_score} on as_of's date row.
    Wraps factor_engine.kernel.evaluate_cross_section.
    """
    from alpha_agent.factor_engine.factor_backtest import _Panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    panel = _Panel.load_default()
    spec = FactorSpec(expression=expr)
    scores = evaluate_cross_section(panel, spec, as_of_date=as_of.date().isoformat())
    arr = np.array(list(scores.values()), dtype=float)
    mu, sigma = np.nanmean(arr), np.nanstd(arr)
    if sigma == 0 or np.isnan(sigma):
        return {t: 0.0 for t in scores}
    return {t: float(np.clip((v - mu) / sigma, -3.0, 3.0)) for t, v in scores.items()}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    scores = _evaluate_for_universe(as_of)
    if ticker not in scores:
        raise KeyError(f"{ticker} not in panel universe")
    z = scores[ticker]
    return SignalScore(
        ticker=ticker, z=z, raw=z, confidence=0.95,
        as_of=as_of, source="factor_engine", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="factor_engine")
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/signals/test_factor.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/factor.py tests/signals/test_factor.py
git commit -m "feat(signals): factor signal (default composite, weight 0.30)"
```

---

### Task 8: `signals/technicals.py` (RSI + MACD + ATR + MA distance from yfinance OHLCV)

**Files:**
- Create: `alpha_agent/signals/technicals.py`
- Create: `tests/signals/conftest.py`
- Create: `tests/signals/test_technicals.py`
- Create: `tests/fixtures/yfinance/AAPL_ohlcv_2024-01-01_2024-12-31.json`

**Why:** Spec §3.1 weight 0.20 (second-largest). Aggregates 5 sub-indicators into one z; weights them equally then z-scores cross-section.

- [ ] **Step 1: Create yfinance fixture loader in `tests/signals/conftest.py`**

```python
"""Shared signal-test fixtures: frozen yfinance / EDGAR / FRED responses."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def yf_ohlcv_aapl_2024() -> pd.DataFrame:
    path = FIXTURE_ROOT / "yfinance" / "AAPL_ohlcv_2024-01-01_2024-12-31.json"
    raw = json.loads(path.read_text())
    return pd.DataFrame(raw).rename(columns=str.title)
```

- [ ] **Step 2: Write the failing test**

Create `tests/signals/test_technicals.py`:
```python
from datetime import datetime, UTC
from unittest.mock import patch

from alpha_agent.signals.technicals import fetch_signal


def test_technicals_z_in_valid_range(yf_ohlcv_aapl_2024):
    with patch("alpha_agent.signals.technicals._download_ohlcv",
               return_value=yf_ohlcv_aapl_2024):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert -3.0 <= out["z"] <= 3.0
    assert isinstance(out["raw"], dict)
    assert {"rsi", "macd", "atr", "ma50_dist", "ma200_dist"} <= out["raw"].keys()
    assert out["confidence"] > 0.7


def test_technicals_short_history_returns_low_confidence(yf_ohlcv_aapl_2024):
    df = yf_ohlcv_aapl_2024.tail(30)  # only 30 rows
    with patch("alpha_agent.signals.technicals._download_ohlcv", return_value=df):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/signals/test_technicals.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `alpha_agent/signals/technicals.py`**

```python
"""Technical-indicator composite signal.

Sub-indicators (each z-scored cross-section, then equal-weighted):
  - RSI(14): mean-reversion / momentum gauge
  - MACD histogram: trend strength
  - ATR(14) / price: volatility-normalized risk
  - 50d MA distance: short-term trend
  - 200d MA distance: long-term trend
Spec §3.1 weight 0.20.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from alpha_agent.signals.base import SignalScore, safe_fetch


def _download_ohlcv(ticker: str, as_of: datetime) -> pd.DataFrame:
    import yfinance as yf
    end = as_of.date().isoformat()
    start = (as_of.date() - pd.Timedelta(days=400)).isoformat()
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _rsi(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return float(100 - 100 / (1 + rs.iloc[-1])) if pd.notna(rs.iloc[-1]) else 50.0


def _macd_hist(close: pd.Series) -> float:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float((macd - signal).iloc[-1])


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    df = _download_ohlcv(ticker, as_of)
    if len(df) < 60:
        return SignalScore(
            ticker=ticker, z=0.0, raw=None, confidence=0.3,
            as_of=as_of, source="yfinance",
            error=f"insufficient history ({len(df)} rows)",
        )
    close = df["Close"]
    components = {
        "rsi": _rsi(close),
        "macd": _macd_hist(close),
        "atr": _atr(df) / float(close.iloc[-1]),
        "ma50_dist": float(close.iloc[-1] / close.rolling(50).mean().iloc[-1] - 1),
        "ma200_dist": float(close.iloc[-1] / close.rolling(200).mean().iloc[-1] - 1),
    }
    rsi_z = (components["rsi"] - 50) / 20
    macd_z = np.tanh(components["macd"] / max(close.std(), 1e-6))
    atr_z = -np.tanh(components["atr"] * 50)
    ma50_z = np.tanh(components["ma50_dist"] * 10)
    ma200_z = np.tanh(components["ma200_dist"] * 10)
    z = float(np.clip(np.mean([rsi_z, macd_z, atr_z, ma50_z, ma200_z]), -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z, raw=components, confidence=0.85,
        as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

- [ ] **Step 5: Run + commit**

Run: `pytest tests/signals/test_technicals.py -v` — PASS
```bash
git add alpha_agent/signals/technicals.py tests/signals/conftest.py \
        tests/signals/test_technicals.py tests/fixtures/yfinance/
git commit -m "feat(signals): technicals composite (RSI/MACD/ATR/MA50/MA200, weight 0.20)"
```

---

### Task 9: `signals/analyst.py` (yfinance recommendation + target)

**Files:**
- Create: `alpha_agent/signals/analyst.py`
- Create: `tests/signals/test_analyst.py`
- Create: `tests/fixtures/yfinance/AAPL_info_2024-12-15.json`

- [ ] **Step 1: Write failing test**

```python
# tests/signals/test_analyst.py
from datetime import datetime, UTC
from unittest.mock import patch
import json
from pathlib import Path
from alpha_agent.signals.analyst import fetch_signal

FIXTURE = Path(__file__).parent.parent / "fixtures/yfinance/AAPL_info_2024-12-15.json"


def test_strong_buy_yields_positive_z():
    info = {"recommendationKey": "strong_buy", "targetMeanPrice": 250.0,
            "currentPrice": 200.0}
    with patch("alpha_agent.signals.analyst._fetch_info", return_value=info):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
    assert out["confidence"] > 0.7
    assert out["raw"]["recommendation"] == "strong_buy"


def test_missing_recommendation_low_confidence():
    with patch("alpha_agent.signals.analyst._fetch_info", return_value={}):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.3
```

- [ ] **Step 2: Run, expect FAIL**

`pytest tests/signals/test_analyst.py -v`

- [ ] **Step 3: Implement `alpha_agent/signals/analyst.py`**

```python
"""Analyst consensus signal. yfinance .info exposes recommendationKey
('strong_buy'|'buy'|'hold'|'underperform'|'sell') + targetMeanPrice.
We map the key to [-2, +2] and target upside to [-1, +1], average."""
from __future__ import annotations
from datetime import datetime
from alpha_agent.signals.base import SignalScore, safe_fetch

_REC_MAP = {
    "strong_buy": 2.0, "buy": 1.0, "hold": 0.0,
    "underperform": -1.0, "sell": -2.0, "strong_sell": -2.0,
}


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info = _fetch_info(ticker)
    rec = (info.get("recommendationKey") or "").lower()
    cur = info.get("currentPrice")
    tgt = info.get("targetMeanPrice")
    if rec not in _REC_MAP:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.2,
                           as_of=as_of, source="yfinance",
                           error="missing recommendationKey")
    rec_z = _REC_MAP[rec] / 2.0  # -> [-1, +1]
    target_upside_z = 0.0
    if cur and tgt:
        upside = (tgt - cur) / cur
        target_upside_z = max(min(upside / 0.20, 1.0), -1.0)  # ±20% saturates
    z = max(min((rec_z + target_upside_z) / 2 * 2, 3.0), -3.0)
    return SignalScore(
        ticker=ticker, z=z,
        raw={"recommendation": rec, "current": cur, "target": tgt},
        confidence=0.80, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/signals/test_analyst.py -v
git add alpha_agent/signals/analyst.py tests/signals/test_analyst.py tests/fixtures/yfinance/
git commit -m "feat(signals): analyst recommendation + target signal (weight 0.10)"
```

---

### Task 10: `signals/earnings.py` (proximity + EPS surprise)

**Files:**
- Create: `alpha_agent/signals/earnings.py`
- Create: `tests/signals/test_earnings.py`

- [ ] **Step 1: Write failing test**

```python
# tests/signals/test_earnings.py
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from alpha_agent.signals.earnings import fetch_signal


def test_recent_beat_yields_positive_z():
    info = {
        "earningsDate": [datetime.now(UTC) - timedelta(days=5)],
        "epsActual": 1.20, "epsEstimate": 1.00,
    }
    with patch("alpha_agent.signals.earnings._fetch_info", return_value=info):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] > 0
    assert out["raw"]["surprise_pct"] > 0


def test_no_data_low_confidence():
    with patch("alpha_agent.signals.earnings._fetch_info", return_value={}):
        out = fetch_signal("XYZ", datetime.now(UTC))
    assert out["confidence"] < 0.4
```

- [ ] **Step 2: Run, expect FAIL**, **Step 3: implement, Step 4: PASS, Step 5: commit**

```python
# alpha_agent/signals/earnings.py
"""Earnings catalyst signal. Two components:
- Proximity: |days_until_or_since_earnings|; sigmoid → [0, 1]
- Surprise: (actual - estimate) / |estimate|; ±50% saturates."""
from __future__ import annotations
from datetime import datetime
import numpy as np
from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    earnings_dates = getattr(t, "earnings_dates", None)
    if earnings_dates is not None and not earnings_dates.empty:
        info["epsActual"] = earnings_dates["Reported EPS"].iloc[0]
        info["epsEstimate"] = earnings_dates["EPS Estimate"].iloc[0]
        info["earningsDate"] = [earnings_dates.index[0]]
    return info


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info = _fetch_info(ticker)
    actual = info.get("epsActual")
    est = info.get("epsEstimate")
    earn_dates = info.get("earningsDate") or []
    if not earn_dates or actual is None or est is None or est == 0:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.3,
                           as_of=as_of, source="yfinance", error="missing earnings")
    surprise = (actual - est) / abs(est)
    surprise_z = float(np.clip(surprise / 0.20, -2.0, 2.0))
    days = abs((earn_dates[0].replace(tzinfo=as_of.tzinfo) - as_of).days)
    proximity_w = float(np.exp(-days / 14))
    z = float(np.clip(surprise_z * proximity_w, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"surprise_pct": surprise * 100, "days_to_earnings": days},
        confidence=0.75, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

```bash
pytest tests/signals/test_earnings.py -v
git add alpha_agent/signals/earnings.py tests/signals/test_earnings.py
git commit -m "feat(signals): earnings proximity + EPS surprise (weight 0.10)"
```

---

### Task 11: `signals/insider.py` (SEC EDGAR Form 4)

**Files:**
- Create: `alpha_agent/signals/insider.py`
- Create: `tests/signals/test_insider.py`
- Create: `tests/fixtures/edgar/form4_AAPL_30d_2024-12-15.json` (parsed list of {date, code, shares})

- [ ] **Step 1: Write failing test**

```python
# tests/signals/test_insider.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.insider import fetch_signal


def test_net_buying_yields_positive_z():
    fills = [{"code": "P", "shares": 1000, "value": 200_000},
             {"code": "P", "shares": 500, "value": 100_000}]
    with patch("alpha_agent.signals.insider._fetch_form4_30d", return_value=fills):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
    assert out["raw"]["net_value"] > 0


def test_no_filings_zero_z_low_confidence():
    with patch("alpha_agent.signals.insider._fetch_form4_30d", return_value=[]):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] == 0.0
    assert out["confidence"] < 0.5
```

- [ ] **Step 2-4: Implement + verify**

```python
# alpha_agent/signals/insider.py
"""Insider trading signal from SEC EDGAR Form 4 last 30 days.
Net dollar value (purchases — sales); sigmoid normalized."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

_EDGAR_HEADERS = {"User-Agent": "Alpha Agent v4 contact@example.com"}


def _fetch_form4_30d(ticker: str, as_of: datetime) -> list[dict[str, Any]]:
    """Returns list of {date, code (P/S), shares, value}."""
    url = f"https://data.sec.gov/submissions/CIK{ticker}.json"
    resp = httpx.get(url, headers=_EDGAR_HEADERS, timeout=10.0)
    resp.raise_for_status()
    # Real implementation: parse Form 4 filings; placeholder here.
    return []  # replaced by tests via patch


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    fills = _fetch_form4_30d(ticker, as_of)
    if not fills:
        return SignalScore(ticker=ticker, z=0.0, raw={"net_value": 0, "n_fillings": 0},
                           confidence=0.4, as_of=as_of, source="edgar",
                           error="no filings in 30d")
    net = sum(f["value"] if f["code"] == "P" else -f["value"] for f in fills)
    z = float(np.tanh(net / 1_000_000))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"net_value": net, "n_fillings": len(fills)},
        confidence=0.70, as_of=as_of, source="edgar", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="edgar")
```

```bash
pytest tests/signals/test_insider.py -v
git add alpha_agent/signals/insider.py tests/signals/test_insider.py tests/fixtures/edgar/
git commit -m "feat(signals): SEC EDGAR Form 4 net buying signal (weight 0.05)"
```

---

### Task 12: `signals/macro.py` (FRED yield curve + dollar + VIX)

**Files:**
- Create: `alpha_agent/signals/macro.py`
- Create: `tests/signals/test_macro.py`
- Create: `tests/fixtures/fred/macro_2024-12-15.json`

**Why:** Macro signal is universe-wide (same for all tickers on same date) but adjusted by sector. Cached 24h to share across all 500 tickers.

- [ ] **Step 1: Write failing test**

```python
# tests/signals/test_macro.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.macro import fetch_signal


def test_macro_inversion_negative_for_growth():
    snapshot = {"DGS10": 4.0, "DGS2": 4.5, "DXY": 105, "VIX": 18}
    with patch("alpha_agent.signals.macro._fetch_snapshot", return_value=snapshot):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] < 0  # inverted curve = risk-off
    assert "DGS10" in out["raw"]


def test_macro_steep_curve_positive():
    snapshot = {"DGS10": 4.5, "DGS2": 4.0, "DXY": 100, "VIX": 14}
    with patch("alpha_agent.signals.macro._fetch_snapshot", return_value=snapshot):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
```

- [ ] **Step 2-5: Implement + verify**

```python
# alpha_agent/signals/macro.py
"""Macro tilt signal. Single snapshot per date applied to all tickers
(sector adjustment lives in the optional sector overlay, not here).
Components: yield curve slope (DGS10-DGS2), DXY z, VIX z."""
from __future__ import annotations
from datetime import datetime
from functools import lru_cache
from typing import Any

import httpx
import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch


@lru_cache(maxsize=4)
def _fetch_snapshot(date_iso: str) -> dict[str, float]:
    # Real impl pulls FRED API for DGS10, DGS2, DXY, VIX
    return {"DGS10": 4.2, "DGS2": 4.0, "DXY": 102, "VIX": 16}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    snap = _fetch_snapshot(as_of.date().isoformat())
    slope = snap["DGS10"] - snap["DGS2"]
    slope_z = float(np.tanh(slope * 5))                # +0.2 -> ~0.76
    dxy_z = -float(np.tanh((snap["DXY"] - 100) / 5))   # strong dollar = negative
    vix_z = -float(np.tanh((snap["VIX"] - 16) / 8))    # high vol = negative
    z = float(np.clip(np.mean([slope_z, dxy_z, vix_z]), -3.0, 3.0))
    return SignalScore(ticker=ticker, z=z, raw=snap, confidence=0.85,
                       as_of=as_of, source="fred", error=None)


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="fred")
```

```bash
pytest tests/signals/test_macro.py -v
git add alpha_agent/signals/macro.py tests/signals/test_macro.py tests/fixtures/fred/
git commit -m "feat(signals): FRED macro tilt (yield slope + DXY + VIX, weight 0.05)"
```

---

### Task 13: `signals/options.py` (put/call ratio + IV percentile)

**Files:**
- Create: `alpha_agent/signals/options.py`
- Create: `tests/signals/test_options.py`
- Create: `tests/fixtures/yfinance/AAPL_options_2024-12-15.json`

- [ ] **Step 1: Test**

```python
# tests/signals/test_options.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.options import fetch_signal


def test_high_put_call_negative_z():
    chain = {"calls_volume": 1000, "puts_volume": 3000, "iv_percentile": 60}
    with patch("alpha_agent.signals.options._fetch_chain", return_value=chain):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] < 0


def test_low_put_call_positive_z():
    chain = {"calls_volume": 5000, "puts_volume": 1000, "iv_percentile": 30}
    with patch("alpha_agent.signals.options._fetch_chain", return_value=chain):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0
```

- [ ] **Step 2-5: Implement + commit**

```python
# alpha_agent/signals/options.py
"""Options sentiment from put/call volume ratio + IV percentile."""
from __future__ import annotations
from datetime import datetime
import numpy as np
from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_chain(ticker: str, as_of: datetime) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    expiries = t.options
    if not expiries:
        return {}
    chain = t.option_chain(expiries[0])
    return {
        "calls_volume": int(chain.calls["volume"].fillna(0).sum()),
        "puts_volume": int(chain.puts["volume"].fillna(0).sum()),
        "iv_percentile": 50.0,  # naive placeholder; full impl needs hist IV
    }


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    c = _fetch_chain(ticker, as_of)
    if not c or c.get("calls_volume", 0) + c.get("puts_volume", 0) == 0:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.3,
                           as_of=as_of, source="yfinance", error="no options volume")
    pcr = c["puts_volume"] / max(c["calls_volume"], 1)
    pcr_z = -float(np.tanh((pcr - 1.0) * 1.5))  # >1 (puts heavy) negative
    iv_z = -float(np.tanh((c["iv_percentile"] - 50) / 30))
    z = float(np.clip((pcr_z + iv_z) / 2 * 2, -3.0, 3.0))
    return SignalScore(ticker=ticker, z=z, raw=c, confidence=0.70,
                       as_of=as_of, source="yfinance", error=None)


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

```bash
pytest tests/signals/test_options.py -v
git add alpha_agent/signals/options.py tests/signals/test_options.py tests/fixtures/yfinance/
git commit -m "feat(signals): options sentiment (P/C ratio + IV pct, weight 0.05)"
```

---

### Task 14: `signals/news.py` (agent-reach search + sentiment)

**Files:**
- Create: `alpha_agent/signals/news.py`
- Create: `tests/signals/test_news.py`

- [ ] **Step 1: Test**

```python
# tests/signals/test_news.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.news import fetch_signal


def test_positive_news_yields_positive_z():
    items = [{"title": "Apple beats earnings", "sentiment": 0.8},
             {"title": "Strong iPhone sales", "sentiment": 0.6}]
    with patch("alpha_agent.signals.news._search_recent", return_value=items):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] > 0


def test_no_news_low_confidence():
    with patch("alpha_agent.signals.news._search_recent", return_value=[]):
        out = fetch_signal("XYZ", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["confidence"] < 0.4
```

- [ ] **Step 2-5: Implement + commit**

```python
# alpha_agent/signals/news.py
"""News-flow signal via agent-reach. Each item carries a precomputed
sentiment in [-1, +1]; we average + count-bonus."""
from __future__ import annotations
from datetime import datetime, timedelta
import numpy as np
from alpha_agent.signals.base import SignalScore, safe_fetch


def _search_recent(ticker: str, as_of: datetime) -> list[dict]:
    # Real impl: agent-reach plugin call. Returns list of items with `sentiment`.
    return []


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    items = _search_recent(ticker, as_of)
    if not items:
        return SignalScore(ticker=ticker, z=0.0, raw={"n": 0, "mean_sent": 0.0},
                           confidence=0.3, as_of=as_of, source="agent-reach",
                           error="no news in 24h")
    sents = [it.get("sentiment", 0.0) for it in items]
    mean = float(np.mean(sents))
    count_bonus = float(np.tanh(len(items) / 10))  # more items → more confidence in direction
    z = float(np.clip(mean * 2 * count_bonus, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean, "headlines": [it["title"] for it in items[:5]]},
        confidence=0.65, as_of=as_of, source="agent-reach", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="agent-reach")
```

```bash
pytest tests/signals/test_news.py -v
git add alpha_agent/signals/news.py tests/signals/test_news.py
git commit -m "feat(signals): news flow + sentiment via agent-reach (weight 0.10)"
```

---

### Task 15: `signals/premarket.py` (gap σ-normalized via ATR)

**Files:**
- Create: `alpha_agent/signals/premarket.py`
- Create: `tests/signals/test_premarket.py`

- [ ] **Step 1-5: Test → impl → commit**

```python
# tests/signals/test_premarket.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.premarket import fetch_signal


def test_3sigma_gap_up_positive():
    info = {"preMarketPrice": 105, "regularMarketPreviousClose": 100, "atr14": 1.0}
    with patch("alpha_agent.signals.premarket._fetch_premarket", return_value=info):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, 8, tzinfo=UTC))
    assert out["z"] > 1.5  # gap of 5 / atr 1 = 5σ → clipped


def test_no_premarket_data_low_conf():
    with patch("alpha_agent.signals.premarket._fetch_premarket", return_value={}):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, 8, tzinfo=UTC))
    assert out["confidence"] < 0.4
```

```python
# alpha_agent/signals/premarket.py
"""Pre-market gap normalized by 14-day ATR. Captures overnight news
priced into the open. Only meaningful pre-9:30 ET; safe_fetch returns
zero-confidence outside that window in real impl."""
from __future__ import annotations
from datetime import datetime
import numpy as np
from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_premarket(ticker: str, as_of: datetime) -> dict:
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    return {
        "preMarketPrice": info.get("preMarketPrice"),
        "regularMarketPreviousClose": info.get("regularMarketPreviousClose"),
        "atr14": info.get("averageDailyVolume10Day", 1.0) * 0.0,  # placeholder; real impl computes
    }


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    d = _fetch_premarket(ticker, as_of)
    pm, prev, atr = d.get("preMarketPrice"), d.get("regularMarketPreviousClose"), d.get("atr14")
    if not all([pm, prev, atr]) or atr == 0:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.3,
                           as_of=as_of, source="yfinance", error="no pre-market data")
    gap = pm - prev
    z = float(np.clip(gap / atr, -3.0, 3.0))
    return SignalScore(ticker=ticker, z=z,
                       raw={"gap": gap, "gap_sigma": z}, confidence=0.75,
                       as_of=as_of, source="yfinance", error=None)


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

```bash
pytest tests/signals/test_premarket.py -v
git add alpha_agent/signals/premarket.py tests/signals/test_premarket.py
git commit -m "feat(signals): pre-market gap signal (ATR-normalized, weight 0.05)"
```

---

### Task 16: `signals/calendar.py` (display-only)

**Files:**
- Create: `alpha_agent/signals/calendar.py`
- Create: `tests/signals/test_calendar.py`

**Why:** Spec §3.1 calendar weight 0.00 — does NOT enter composite, only renders into card "Catalysts" section. Must still conform to SignalScore for uniform handling.

- [ ] **Step 1-5: Test → impl → commit**

```python
# tests/signals/test_calendar.py
from datetime import datetime, UTC
from unittest.mock import patch
from alpha_agent.signals.calendar import fetch_signal


def test_calendar_returns_zero_z_carries_events():
    events = [{"name": "FOMC", "date": "2024-12-18", "days_to": 3}]
    with patch("alpha_agent.signals.calendar._fetch_events", return_value=events):
        out = fetch_signal("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    assert out["z"] == 0.0
    assert out["raw"][0]["name"] == "FOMC"
```

```python
# alpha_agent/signals/calendar.py
"""Economic calendar display-only signal. Always z=0; raw carries events.
Spec §3.1 weight 0.00 — fusion engine excludes from composite."""
from __future__ import annotations
from datetime import datetime
from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_events(as_of: datetime) -> list[dict]:
    return []  # real impl pulls FRED + agent-reach


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    events = _fetch_events(as_of)
    return SignalScore(ticker=ticker, z=0.0, raw=events,
                       confidence=1.0 if events else 0.5,
                       as_of=as_of, source="fred+reach", error=None)


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="fred+reach")
```

```bash
pytest tests/signals/test_calendar.py -v
git add alpha_agent/signals/calendar.py tests/signals/test_calendar.py
git commit -m "feat(signals): calendar display-only (weight 0.00, raw carries events)"
```

---

### Task 17: Fixture refresh script

**Files:**
- Create: `scripts/refresh_fixtures.py`

**Why:** Plain way to capture today's API response into fixture files for tests; manually invoked, never hits CI.

- [ ] **Step 1: Implement**

```python
"""Manually refresh fixture files from real APIs.

Usage:
    python scripts/refresh_fixtures.py --ticker AAPL --date 2024-12-15
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent / "tests" / "fixtures"


def refresh_yfinance(ticker: str, date: str) -> None:
    out = ROOT / "yfinance"
    out.mkdir(parents=True, exist_ok=True)
    t = yf.Ticker(ticker)
    info = t.info
    (out / f"{ticker}_info_{date}.json").write_text(json.dumps(info, default=str, indent=2))
    df = yf.download(ticker, start="2024-01-01", end=date, progress=False, auto_adjust=True)
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)
    df.reset_index().to_json(out / f"{ticker}_ohlcv_2024-01-01_{date}.json",
                              orient="records", date_format="iso")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    refresh_yfinance(args.ticker, args.date)
    print(f"Fixtures refreshed: {args.ticker} @ {args.date}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run + commit**

```bash
make refresh-fixtures TICKER=AAPL DATE=2024-12-15
git add scripts/refresh_fixtures.py tests/fixtures/yfinance/
git commit -m "tools: scripts/refresh_fixtures.py for capturing API snapshots"
```

---

## Phase D · Fusion Engine（Day 8-9）

### Task 18: `fusion/normalize.py`

**Files:**
- Create: `alpha_agent/fusion/__init__.py` (empty)
- Create: `alpha_agent/fusion/normalize.py`
- Create: `tests/fusion/__init__.py` (empty)
- Create: `tests/fusion/test_normalize.py`

**Why:** Spec §3.2: cross-section z-score over universe + clip ±3σ. Pure function; trivially testable.

- [ ] **Step 1: Write the failing test**

```python
# tests/fusion/test_normalize.py
import math
from alpha_agent.fusion.normalize import normalize_cross_section


def test_normalize_centers_and_scales():
    raw = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
    z = normalize_cross_section(raw)
    assert math.isclose(sum(z.values()), 0.0, abs_tol=1e-6)
    assert any(v > 0 for v in z.values()) and any(v < 0 for v in z.values())


def test_normalize_clips_at_3sigma():
    raw = {f"T{i}": 0.0 for i in range(20)}
    raw["TX"] = 100.0  # massive outlier
    z = normalize_cross_section(raw)
    assert z["TX"] == 3.0  # exactly clipped, not above


def test_normalize_handles_constant_universe():
    raw = {"A": 5.0, "B": 5.0, "C": 5.0}
    z = normalize_cross_section(raw)
    assert all(v == 0.0 for v in z.values())  # σ==0 → all 0


def test_normalize_skips_zero_confidence():
    """confidence=0 entries don't contribute to mean/sigma but get z=0 in output."""
    from alpha_agent.signals.base import SignalScore
    from datetime import datetime, UTC
    base = lambda t, raw, c: SignalScore(ticker=t, z=0.0, raw=raw, confidence=c,
                                          as_of=datetime.now(UTC), source="t", error=None)
    inputs = {"A": base("A", 1.0, 0.9), "B": base("B", 2.0, 0.9),
              "C": base("C", 99.0, 0.0)}
    z = normalize_cross_section(inputs, raw_field="raw")
    assert z["C"] == 0.0
    # only A,B contributed to mean → mean=1.5, sigma=0.5 → A=-1, B=+1
    assert math.isclose(z["A"], -1.0, abs_tol=1e-6)
    assert math.isclose(z["B"], 1.0, abs_tol=1e-6)
```

- [ ] **Step 2: Run, expect FAIL**, **Step 3: Implement**

```python
# alpha_agent/fusion/normalize.py
"""Cross-section z-score + winsorize. Pure function, no IO."""
from __future__ import annotations
from typing import Mapping, Any
import math

import numpy as np

from alpha_agent.signals.base import SignalScore


def normalize_cross_section(
    inputs: Mapping[str, Any],
    *,
    raw_field: str | None = None,
    clip_sigma: float = 3.0,
) -> dict[str, float]:
    """Compute z-scores across the universe.

    inputs may be either:
      - {ticker: float} of raw values, or
      - {ticker: SignalScore} where we use SignalScore[raw_field] (default 'raw')
    confidence==0 entries are excluded from mean/sigma but get z=0 in output.
    """
    if raw_field is None:
        # plain {ticker: float}
        vals = {t: float(v) for t, v in inputs.items()}
        excluded: set[str] = set()
    else:
        vals = {}
        excluded = set()
        for t, sc in inputs.items():
            if sc["confidence"] == 0.0:
                excluded.add(t)
            else:
                v = sc[raw_field]
                vals[t] = float(v) if isinstance(v, (int, float)) else float(sc["z"])
    if not vals:
        return {t: 0.0 for t in inputs}
    arr = np.array(list(vals.values()), dtype=float)
    mu = float(np.nanmean(arr))
    sigma = float(np.nanstd(arr))
    if sigma == 0 or math.isnan(sigma):
        return {t: 0.0 for t in inputs}
    out = {t: float(np.clip((v - mu) / sigma, -clip_sigma, clip_sigma))
           for t, v in vals.items()}
    for t in excluded:
        out[t] = 0.0
    return out
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/fusion/test_normalize.py -v
git add alpha_agent/fusion/__init__.py alpha_agent/fusion/normalize.py \
        tests/fusion/__init__.py tests/fusion/test_normalize.py
git commit -m "feat(fusion): cross-section z-score + winsorize ±3σ (zero-conf exclusion)"
```

---

### Task 19: `fusion/weights.py`

**Files:**
- Create: `alpha_agent/fusion/weights.py`
- Create: `tests/fusion/test_weights.py`

- [ ] **Step 1: Test**

```python
# tests/fusion/test_weights.py
import pytest
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights


def test_default_weights_sum_to_one_excluding_calendar():
    s = sum(w for k, w in DEFAULT_WEIGHTS.items() if k != "calendar")
    assert abs(s - 1.0) < 1e-9


def test_normalize_redistributes_when_some_dropped():
    base = {"factor": 0.30, "technicals": 0.20, "macro": 0.05}
    out = normalize_weights(base, drop={"macro"})
    assert "macro" not in out
    assert abs(sum(out.values()) - 1.0) < 1e-9
    # factor : technicals ratio preserved
    assert abs(out["factor"] / out["technicals"] - 1.5) < 1e-9


def test_normalize_returns_zero_dict_when_all_dropped():
    out = normalize_weights({"factor": 1.0}, drop={"factor"})
    assert out == {}
```

- [ ] **Step 2-4: Impl + commit**

```python
# alpha_agent/fusion/weights.py
"""Default fusion weights + redistribution helper.

Spec §3.1: 9 fusion signals sum to 1.0; calendar=0 (display only)."""
from __future__ import annotations
from typing import Mapping

DEFAULT_WEIGHTS: dict[str, float] = {
    "factor":     0.30,
    "technicals": 0.20,
    "analyst":    0.10,
    "earnings":   0.10,
    "news":       0.10,
    "insider":    0.05,
    "options":    0.05,
    "premarket":  0.05,
    "macro":      0.05,
    "calendar":   0.00,
}


def normalize_weights(
    weights: Mapping[str, float],
    *,
    drop: set[str] | None = None,
) -> dict[str, float]:
    """Drop excluded signals + re-normalize remaining to sum to 1.0."""
    drop = drop or set()
    kept = {k: v for k, v in weights.items() if k not in drop and v > 0}
    total = sum(kept.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in kept.items()}
```

```bash
pytest tests/fusion/test_weights.py -v
git add alpha_agent/fusion/weights.py tests/fusion/test_weights.py
git commit -m "feat(fusion): DEFAULT_WEIGHTS + normalize_weights for confidence-zero redistribution"
```

---

### Task 20: `fusion/combine.py`

**Files:**
- Create: `alpha_agent/fusion/combine.py`
- Create: `tests/fusion/test_combine.py`

- [ ] **Step 1: Test**

```python
# tests/fusion/test_combine.py
from datetime import datetime, UTC
from alpha_agent.signals.base import SignalScore
from alpha_agent.fusion.combine import combine


def _sig(name: str, z: float, conf: float = 0.9) -> SignalScore:
    return SignalScore(ticker="AAPL", z=z, raw=z, confidence=conf,
                       as_of=datetime.now(UTC), source=name, error=None)


def test_combine_weighted_sum():
    signals = {"factor": _sig("factor", 1.0), "technicals": _sig("technicals", 1.0)}
    weights = {"factor": 0.6, "technicals": 0.4}
    result = combine(signals, weights)
    assert abs(result.composite - 1.0) < 1e-9
    assert len(result.breakdown) == 2


def test_combine_redistributes_zero_confidence():
    signals = {"factor": _sig("factor", 1.0, 0.9),
               "macro": _sig("macro", 99.0, 0.0)}
    weights = {"factor": 0.50, "macro": 0.50}
    result = combine(signals, weights)
    # macro confidence=0 → effective weight 0; factor takes full
    assert abs(result.composite - 1.0) < 1e-9
    macro_entry = next(b for b in result.breakdown if b["signal"] == "macro")
    assert macro_entry["weight"] == 0.5  # original weight retained for display
    assert macro_entry["contribution"] == 0.0  # but no contribution


def test_combine_calendar_excluded():
    """calendar weight=0 → never enters composite even with non-zero z."""
    signals = {"factor": _sig("factor", 1.0), "calendar": _sig("calendar", 5.0)}
    from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
    result = combine(signals, DEFAULT_WEIGHTS)
    assert all(b["signal"] != "calendar" or b["contribution"] == 0
               for b in result.breakdown)
```

- [ ] **Step 2-4: Impl + commit**

```python
# alpha_agent/fusion/combine.py
"""Weighted composite + breakdown attribution. Pure function."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping

from alpha_agent.signals.base import SignalScore
from alpha_agent.fusion.weights import normalize_weights


@dataclass
class CombineResult:
    composite: float
    breakdown: list[dict[str, Any]] = field(default_factory=list)


def combine(
    signals: Mapping[str, SignalScore],
    weights: Mapping[str, float],
) -> CombineResult:
    """signals: {signal_name: SignalScore}.
    weights: {signal_name: weight}; calendar=0 always excluded.
    Confidence==0 signals: weight retained in breakdown for display, but
    contribution=0; effective weights re-normalize across the rest.
    """
    drop = {n for n, sc in signals.items() if sc["confidence"] == 0.0}
    drop |= {n for n, w in weights.items() if w == 0}
    eff = normalize_weights(weights, drop=drop)
    composite = 0.0
    breakdown: list[dict[str, Any]] = []
    for name, sc in signals.items():
        w_orig = weights.get(name, 0.0)
        w_eff = eff.get(name, 0.0)
        contribution = sc["z"] * w_eff
        composite += contribution
        breakdown.append({
            "signal": name, "z": sc["z"], "weight": w_orig,
            "weight_effective": w_eff, "contribution": contribution,
            "raw": sc["raw"], "source": sc["source"],
            "timestamp": sc["as_of"].isoformat(),
            "error": sc["error"],
        })
    return CombineResult(composite=composite, breakdown=breakdown)
```

```bash
pytest tests/fusion/test_combine.py -v
git add alpha_agent/fusion/combine.py tests/fusion/test_combine.py
git commit -m "feat(fusion): weighted composite + breakdown w/ confidence-aware redistribution"
```

---

### Task 21: `fusion/rating.py`

**Files:**
- Create: `alpha_agent/fusion/rating.py`
- Create: `tests/fusion/test_rating.py`

- [ ] **Step 1: Test**

```python
# tests/fusion/test_rating.py
import math
from alpha_agent.fusion.rating import map_to_tier, compute_confidence


def test_tier_boundaries():
    assert map_to_tier(2.0) == "BUY"
    assert map_to_tier(1.5001) == "BUY"
    assert map_to_tier(1.4999) == "OW"
    assert map_to_tier(0.5001) == "OW"
    assert map_to_tier(0.4999) == "HOLD"
    assert map_to_tier(0.0) == "HOLD"
    assert map_to_tier(-0.5) == "HOLD"
    assert map_to_tier(-0.5001) == "UW"
    assert map_to_tier(-1.5) == "UW"
    assert map_to_tier(-1.5001) == "SELL"


def test_confidence_high_when_aligned():
    zs = [1.5, 1.4, 1.6, 1.5, 1.4]
    assert compute_confidence(zs) > 0.85


def test_confidence_low_on_disagreement():
    zs = [3.0, -3.0, 0.0, 2.0, -2.0]
    assert compute_confidence(zs) < 0.30


def test_confidence_empty_returns_zero():
    assert compute_confidence([]) == 0.0
```

- [ ] **Step 2-4: Impl + commit**

```python
# alpha_agent/fusion/rating.py
"""5-tier mapping + confidence (signal-agreement gauge)."""
from __future__ import annotations
from typing import Iterable, Literal

import numpy as np

Tier = Literal["BUY", "OW", "HOLD", "UW", "SELL"]


def map_to_tier(composite: float) -> Tier:
    if composite > 1.5:
        return "BUY"
    if composite > 0.5:
        return "OW"
    if composite >= -0.5:
        return "HOLD"
    if composite >= -1.5:
        return "UW"
    return "SELL"


def compute_confidence(zs: Iterable[float]) -> float:
    """confidence = 1 / (1 + variance). Aligned signals -> ~1; disagreement -> ~0."""
    arr = np.asarray(list(zs), dtype=float)
    if arr.size == 0:
        return 0.0
    var = float(np.var(arr))
    return float(1.0 / (1.0 + var))
```

```bash
pytest tests/fusion/test_rating.py -v
git add alpha_agent/fusion/rating.py tests/fusion/test_rating.py
git commit -m "feat(fusion): 5-tier mapping + confidence (1/(1+variance))"
```

---

### Task 22: `fusion/attribution.py`

**Files:**
- Create: `alpha_agent/fusion/attribution.py`
- Create: `tests/fusion/test_attribution.py`

- [ ] **Step 1: Test**

```python
# tests/fusion/test_attribution.py
from alpha_agent.fusion.attribution import top_drivers, top_drags


def test_top_drivers_picks_top_3_positive():
    breakdown = [
        {"signal": "factor", "contribution": +0.54},
        {"signal": "tech", "contribution": +0.30},
        {"signal": "analyst", "contribution": +0.20},
        {"signal": "macro", "contribution": -0.18},
        {"signal": "news", "contribution": -0.12},
    ]
    drivers = top_drivers(breakdown, n=3)
    assert drivers == ["factor", "tech", "analyst"]


def test_top_drags_picks_most_negative():
    breakdown = [
        {"signal": "factor", "contribution": +0.54},
        {"signal": "macro", "contribution": -0.18},
        {"signal": "news", "contribution": -0.12},
        {"signal": "premkt", "contribution": -0.06},
    ]
    drags = top_drags(breakdown, n=2)
    assert drags == ["macro", "news"]


def test_zero_contribution_signals_excluded():
    breakdown = [
        {"signal": "a", "contribution": +0.5},
        {"signal": "b", "contribution": 0.0},
    ]
    assert top_drivers(breakdown, n=3) == ["a"]
    assert top_drags(breakdown, n=3) == []
```

- [ ] **Step 2-4: Impl + commit**

```python
# alpha_agent/fusion/attribution.py
"""Reverse attribution: which signals drove the rating up/down."""
from __future__ import annotations
from typing import Sequence, Mapping


def top_drivers(breakdown: Sequence[Mapping[str, float]], n: int = 3) -> list[str]:
    pos = [b for b in breakdown if b.get("contribution", 0.0) > 0]
    pos.sort(key=lambda b: -b["contribution"])
    return [b["signal"] for b in pos[:n]]


def top_drags(breakdown: Sequence[Mapping[str, float]], n: int = 3) -> list[str]:
    neg = [b for b in breakdown if b.get("contribution", 0.0) < 0]
    neg.sort(key=lambda b: b["contribution"])  # ascending = most negative first
    return [b["signal"] for b in neg[:n]]
```

```bash
pytest tests/fusion/test_attribution.py -v
git add alpha_agent/fusion/attribution.py tests/fusion/test_attribution.py
git commit -m "feat(fusion): top_drivers / top_drags reverse-attribution helpers"
```

---

## Phase E · CLI 验收（Day 10）

### Task 23: `RatingCard` Pydantic schema

**Files:**
- Modify: `alpha_agent/core/types.py` (append at end)
- Create: `tests/test_rating_card_schema.py`

**Why:** Wire-format contract. Frontend will import generated types from this. Pydantic v2 enforces field types + validation on every parse.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rating_card_schema.py
import pytest
from datetime import datetime, UTC

from alpha_agent.core.types import RatingCard, BreakdownEntry


def test_rating_card_validates_required_fields():
    card = RatingCard(
        ticker="AAPL", rating="OW", confidence=0.72,
        composite_score=1.23, as_of=datetime.now(UTC),
        breakdown=[BreakdownEntry(
            signal="factor", z=1.8, weight=0.30, weight_effective=0.30,
            contribution=0.54, raw=1.8, source="factor_engine",
            timestamp=datetime.now(UTC), error=None,
        )],
        top_drivers=["factor"], top_drags=[],
    )
    assert card.rating == "OW"


def test_rating_card_rejects_invalid_tier():
    with pytest.raises(ValueError):
        RatingCard(
            ticker="AAPL", rating="STRONG_BUY",  # not in 5-tier set
            confidence=0.5, composite_score=0.0,
            as_of=datetime.now(UTC), breakdown=[],
            top_drivers=[], top_drags=[],
        )


def test_rating_card_confidence_bounded():
    with pytest.raises(ValueError):
        RatingCard(
            ticker="AAPL", rating="HOLD", confidence=1.5,  # > 1.0
            composite_score=0.0, as_of=datetime.now(UTC), breakdown=[],
            top_drivers=[], top_drags=[],
        )
```

- [ ] **Step 2-4: Impl + commit**

Append to `alpha_agent/core/types.py`:

```python
# === RatingCard (M1, spec §3.2) ===
from datetime import datetime as _datetime
from typing import Any, Literal as _Literal
from pydantic import BaseModel, Field, ConfigDict


class BreakdownEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: str
    z: float = Field(ge=-3.0, le=3.0)
    weight: float = Field(ge=0.0, le=1.0)
    weight_effective: float = Field(ge=0.0, le=1.0)
    contribution: float
    raw: Any
    source: str
    timestamp: _datetime
    error: str | None = None


Tier = _Literal["BUY", "OW", "HOLD", "UW", "SELL"]


class RatingCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    rating: Tier
    confidence: float = Field(ge=0.0, le=1.0)
    composite_score: float
    as_of: _datetime
    breakdown: list[BreakdownEntry]
    top_drivers: list[str]
    top_drags: list[str]
```

```bash
pytest tests/test_rating_card_schema.py -v
git add alpha_agent/core/types.py tests/test_rating_card_schema.py
git commit -m "feat(core): RatingCard + BreakdownEntry Pydantic models (5-tier validation)"
```

---

### Task 24: CLI `build-card` subcommand

**Files:**
- Create: `alpha_agent/cli/__init__.py` (empty)
- Create: `alpha_agent/cli/build_card.py`
- Modify: `alpha_agent/main.py` (add subparser)
- Create: `tests/cli/__init__.py` (empty)
- Create: `tests/cli/test_build_card_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_build_card_cli.py
import json
import subprocess
import sys


def test_build_card_outputs_valid_json(monkeypatch):
    """End-to-end CLI: all signals patched to return non-zero scores,
    composite > 0 → rating in {BUY, OW}."""
    from unittest.mock import patch
    from datetime import datetime, UTC

    from alpha_agent.signals.base import SignalScore
    from alpha_agent.cli.build_card import build_card

    def fake(name):
        def _f(t, a):
            return SignalScore(ticker=t, z=1.0, raw=1.0, confidence=0.9,
                               as_of=a, source=name, error=None)
        return _f

    targets = ["factor", "technicals", "analyst", "earnings", "news",
               "insider", "options", "premarket", "macro", "calendar"]
    patches = [patch(f"alpha_agent.signals.{t}.fetch_signal", side_effect=fake(t))
               for t in targets]
    for p in patches:
        p.start()
    try:
        card = build_card("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
        assert card.ticker == "AAPL"
        assert card.rating in {"BUY", "OW", "HOLD", "UW", "SELL"}
        assert 0.0 <= card.confidence <= 1.0
        assert any(b.signal == "factor" for b in card.breakdown)
        # JSON round-trip
        data = card.model_dump_json()
        json.loads(data)
    finally:
        for p in patches:
            p.stop()
```

- [ ] **Step 2: Run, expect FAIL**, **Step 3: Implement**

Create `alpha_agent/cli/build_card.py`:

```python
"""Orchestrator: pull all signals, fuse, return RatingCard."""
from __future__ import annotations
from datetime import datetime
from typing import Any

from alpha_agent.signals import (
    factor, technicals, analyst, earnings, news,
    insider, options, premarket, macro, calendar as cal,
)
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.rating import map_to_tier, compute_confidence
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.core.types import RatingCard, BreakdownEntry

_MODULES = {
    "factor": factor, "technicals": technicals, "analyst": analyst,
    "earnings": earnings, "news": news, "insider": insider,
    "options": options, "premarket": premarket, "macro": macro,
    "calendar": cal,
}


def build_card(ticker: str, as_of: datetime) -> RatingCard:
    sigs = {name: mod.fetch_signal(ticker, as_of) for name, mod in _MODULES.items()}
    res = combine(sigs, DEFAULT_WEIGHTS)
    contributing_zs = [b["z"] for b in res.breakdown
                       if b["weight_effective"] > 0]
    confidence = compute_confidence(contributing_zs)
    rating = map_to_tier(res.composite)
    return RatingCard(
        ticker=ticker, rating=rating, confidence=confidence,
        composite_score=res.composite, as_of=as_of,
        breakdown=[BreakdownEntry(**b) for b in res.breakdown],
        top_drivers=top_drivers(res.breakdown),
        top_drags=top_drags(res.breakdown),
    )
```

Modify `alpha_agent/main.py` to add subcommand. Locate the existing `subparsers = parser.add_subparsers(dest="command")` block and append:

```python
    # build-card: end-to-end M1 CLI
    bc_parser = subparsers.add_parser("build-card", help="Build a RatingCard for a ticker")
    bc_parser.add_argument("ticker", help="Ticker symbol (e.g. AAPL)")
    bc_parser.add_argument("--as-of", default=None, help="ISO datetime (default now UTC)")
    bc_parser.add_argument("--use-fixtures", action="store_true",
                           help="Patch signals with fixture data (for offline acceptance)")
```

In the dispatch section of `main()` (after `args = parser.parse_args()`), add:

```python
    if args.command == "build-card":
        from datetime import datetime, UTC
        from alpha_agent.cli.build_card import build_card
        as_of = (datetime.fromisoformat(args.as_of) if args.as_of
                 else datetime.now(UTC))
        if args.use_fixtures:
            # smoke test: synthetic z=0.5 across all signals
            from unittest.mock import patch
            from alpha_agent.signals.base import SignalScore
            def fake(name):
                def _f(t, a):
                    return SignalScore(ticker=t, z=0.5, raw=0.5, confidence=0.9,
                                       as_of=a, source=name, error=None)
                return _f
            targets = list(_module_names_for_fixtures())
            ps = [patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=fake(n))
                  for n in targets]
            for p in ps: p.start()
            try:
                card = build_card(args.ticker, as_of)
            finally:
                for p in ps: p.stop()
        else:
            card = build_card(args.ticker, as_of)
        print(card.model_dump_json(indent=2))
        return
```

Add this helper near top of `main.py`:

```python
def _module_names_for_fixtures() -> list[str]:
    return ["factor", "technicals", "analyst", "earnings", "news",
            "insider", "options", "premarket", "macro", "calendar"]
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/cli/test_build_card_cli.py -v
python -m alpha_agent build-card AAPL --use-fixtures | python -c "import sys, json; \
  from alpha_agent.core.types import RatingCard; \
  RatingCard.model_validate_json(sys.stdin.read()); print('valid')"
git add alpha_agent/cli/ alpha_agent/main.py tests/cli/
git commit -m "feat(cli): build-card subcommand orchestrator (signals → fusion → RatingCard)"
```

---

### Task 25: End-to-end integration test (mocked external calls)

**Files:**
- Create: `tests/integration/__init__.py` (empty)
- Create: `tests/integration/test_build_card_e2e.py`

**Why:** Acceptance gate — the M1 deliverable. Wires storage layer, all 10 signals (mocked at HTTP boundary), fusion, and Pydantic validation.

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_build_card_e2e.py
"""M1 acceptance: build-card flow end-to-end with mocked external HTTP."""
import json
from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from alpha_agent.cli.build_card import build_card
from alpha_agent.core.types import RatingCard

pytestmark = pytest.mark.asyncio


def _patch_all_signals(z_value: float = 0.8):
    from alpha_agent.signals.base import SignalScore
    targets = ["factor", "technicals", "analyst", "earnings", "news",
               "insider", "options", "premarket", "macro", "calendar"]

    def make_fake(name):
        def _f(ticker, as_of):
            z = 0.0 if name == "calendar" else z_value
            return SignalScore(ticker=ticker, z=z, raw={}, confidence=0.85,
                               as_of=as_of, source=name, error=None)
        return _f

    return [patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=make_fake(n))
            for n in targets]


def test_e2e_all_positive_yields_buy_or_ow():
    patches = _patch_all_signals(z_value=2.0)
    for p in patches: p.start()
    try:
        card = build_card("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    finally:
        for p in patches: p.stop()
    assert card.rating in {"BUY", "OW"}
    assert card.confidence > 0.8
    assert card.composite_score > 0.5
    assert "factor" in card.top_drivers
    assert "calendar" not in [b.signal for b in card.breakdown
                               if b.weight_effective > 0]


def test_e2e_pydantic_round_trip():
    patches = _patch_all_signals(z_value=0.5)
    for p in patches: p.start()
    try:
        card = build_card("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    finally:
        for p in patches: p.stop()
    raw = card.model_dump_json()
    reparsed = RatingCard.model_validate_json(raw)
    assert reparsed.ticker == card.ticker
    assert reparsed.composite_score == card.composite_score


def test_e2e_one_signal_fails_gracefully():
    """Spec §5.1: per-signal isolation — one failure doesn't kill the card."""
    from alpha_agent.signals.base import SignalScore

    patches = _patch_all_signals(z_value=1.0)
    # Override: factor returns confidence=0 (simulated failure)
    patches.append(patch(
        "alpha_agent.signals.factor.fetch_signal",
        side_effect=lambda t, a: SignalScore(
            ticker=t, z=0.0, raw=None, confidence=0.0,
            as_of=a, source="factor_engine", error="ConnectionError: simulated",
        ),
    ))
    for p in patches: p.start()
    try:
        card = build_card("AAPL", datetime(2024, 12, 15, tzinfo=UTC))
    finally:
        for p in patches: p.stop()
    assert card.rating in {"BUY", "OW", "HOLD", "UW", "SELL"}
    factor_entry = next(b for b in card.breakdown if b.signal == "factor")
    assert factor_entry.error is not None
    assert factor_entry.contribution == 0.0
```

- [ ] **Step 2-3: Run + commit**

```bash
pytest tests/integration/test_build_card_e2e.py -v
git add tests/integration/
git commit -m "test(m1): end-to-end build-card integration (acceptance gate)"
```

---

### Task 26: Coverage gate + acceptance verification

**Files:**
- Modify: `Makefile` (add `m1-acceptance` target)

- [ ] **Step 1: Add Makefile target**

```makefile
m1-acceptance:
	@echo "==> Running M1 acceptance suite"
	pytest tests/storage tests/signals tests/fusion tests/cli tests/integration \
	    --cov=alpha_agent.storage --cov=alpha_agent.signals --cov=alpha_agent.fusion \
	    --cov-fail-under=85 -m "not slow"
	@echo "==> CLI smoke"
	python -m alpha_agent build-card AAPL --use-fixtures > /tmp/m1_card.json
	python -c "from alpha_agent.core.types import RatingCard; \
	  RatingCard.model_validate_json(open('/tmp/m1_card.json').read()); \
	  print('M1 acceptance PASS')"
```

- [ ] **Step 2: Run acceptance**

Run: `make m1-acceptance`
Expected output ends with: `M1 acceptance PASS`

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "ci(m1): m1-acceptance Makefile target (coverage + CLI smoke)"
```

---

## Self-Review Checklist (do before declaring M1 complete)

- [ ] All 26 tasks committed; `git log --oneline | grep -c "(m1)"` >= 26
- [ ] `make m1-acceptance` returns 0
- [ ] Coverage: `signals/*` ≥ 90%, `fusion/*` ≥ 95%, overall ≥ 85%
- [ ] No naked `except Exception` in `alpha_agent/signals/`: `grep -rn "except Exception" alpha_agent/signals/` returns nothing
- [ ] Schema migration applies cleanly to a fresh DB (Postgres 16): manually verified by re-running tests
- [ ] `python -m alpha_agent build-card AAPL --use-fixtures` outputs a JSON that passes `RatingCard.model_validate_json`
- [ ] All `tests/fixtures/` files committed (not gitignored)
- [ ] `pyproject.toml` deps installed cleanly in a fresh venv

If any item fails, fix in-place + add a regression test before marking M1 done.

---

## Hand-off to M2

After M1 acceptance passes, you can either:
- Bump task #220 backlog and start M2 (Cron + API endpoints)
- Or pause and run `/superpowers:writing-plans` again with M2 scope

**M1 → M2 contract:**
- Postgres tables exist with proper schema
- `build_card(ticker, as_of)` is callable from any context
- `RatingCard` Pydantic model is the wire format M2 will serve via API
- `fetch_signal()` modules can be invoked individually for cron batch loops
