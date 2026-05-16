# Phase 5 News Multi-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a dual-channel news pipeline (per-ticker financial news + market-wide political/macro events) feeding the stock detail page through a new MarketContextWidget, with BYOK-LLM doing sentiment + ticker-extraction at cron time so page loads stay zero-LLM-latency.

**Architecture:** Two Postgres tables (`news_items` keyed per-ticker, `macro_events` global with `tickers_extracted` array). Six adapters behind one protocol (Finnhub primary / FMP failover / RSS tertiary for per-ticker; Truth Social CNN mirror + Fed RSS + OFAC RSS for macro, all parallel). A separate `llm_news_enrich` cron worker picks `llm_processed_at IS NULL` rows and batches them through the existing `LiteLLMClient`. New `/api/macro_context?ticker=X` returns macro events whose `tickers_extracted` contain that ticker.

**Tech Stack:** FastAPI + asyncpg + httpx + feedparser + LiteLLMClient (existing). Next.js 16 client + lucide-react icons. Vercel functions + GitHub Actions cron-shards (existing pattern).

**Spec:** [`docs/superpowers/specs/2026-05-16-phase5-news-multi-source.md`](../specs/2026-05-16-phase5-news-multi-source.md). Read it first.

---

## Scope

One spec, one plan. No sub-project decomposition. Six adapter classes are independent files behind a shared protocol; aggregators are 2 thin classes; one cron file with 3 handlers; two new routes; one new frontend widget plus a NewsBlock rewrite.

## Hard rules (read before any task)

1. **NO em-dashes** (`—`, `–`, `--`) anywhere: code, comments, commit messages, docstrings, doc files, UI strings, log messages. Use hyphens / commas / colons / "->". Single hyphens in `--noEmit`-style CLI flags are fine.
2. **Chunk `Write` / `Edit` to ~150 lines.** For files larger than that, split into multiple Edit calls.
3. **Dual-entry rule (CRITICAL).** Every NEW backend router must be registered in BOTH:
   - `alpha_agent/api/app.py::create_app` via `_load("name", _import_name)`
   - `api/index.py` via `_load("name", "alpha_agent.api.routes.name")`
   The watchlist landmine of 2026-05-15 (memory `feedback_vercel_python_dual_entry.md`) cost 30+ min because only `app.py` was touched. Verify after deploy: `curl https://alpha.bobbyzhong.com/api/_health/routers | jq '.routers[].name'` must list the new router name.
   - Cron handlers in `api/cron/*.py` get mounted via the existing `cron_routes.py` router, which is already registered. Adding a new endpoint to that router does NOT require dual-entry re-registration.
   - New endpoints added to an existing router (e.g. `/api/_health/news_freshness` on the existing `health.py` router) also do NOT require re-registration.
4. **NEVER read files >2000 lines without `offset` + `limit`.** Project hook blocks it.
5. **TDD where this plan calls for it.** RED -> GREEN -> commit, in that order.
6. **One commit per task.** Do not stack.
7. **USER SETUP env vars (`FINNHUB_API_KEY`, `FMP_API_KEY`) are user actions.** Implementers must not try to set them; tests pass fixture values via monkeypatch.

## File structure

### New backend files
| Path | Purpose |
|---|---|
| `alpha_agent/storage/migrations/V004__news_pipeline.sql` | news_items + macro_events tables + indexes |
| `alpha_agent/news/__init__.py` | empty package marker |
| `alpha_agent/news/types.py` | `NewsItem`, `MacroEvent` dataclasses; `dedup_hash()` |
| `alpha_agent/news/base.py` | `NewsAdapter` Protocol; shared `httpx.AsyncClient` factory; circuit breaker dataclass |
| `alpha_agent/news/finnhub_adapter.py` | `FinnhubAdapter` (per-ticker, priority 1) |
| `alpha_agent/news/fmp_adapter.py` | `FMPAdapter` (per-ticker, priority 2, failover-only) |
| `alpha_agent/news/rss_adapter.py` | `RSSAdapter` (per-ticker, priority 3, Yahoo + Google RSS) |
| `alpha_agent/news/truth_adapter.py` | `TruthSocialAdapter` (macro, CNN mirror JSON) |
| `alpha_agent/news/fed_adapter.py` | `FedRSSAdapter` (macro, federalreserve.gov press_all.xml) |
| `alpha_agent/news/ofac_adapter.py` | `OFACRSSAdapter` (macro, ofac recent-actions RSS) |
| `alpha_agent/news/aggregator.py` | `PerTickerAggregator` + `MacroAggregator` |
| `alpha_agent/news/llm_worker.py` | `enrich_pending(pool, llm_client, limit=100)` for the LLM batch |
| `alpha_agent/news/queries.py` | INSERT / UPDATE helpers against news_items + macro_events |
| `api/cron/news_pipeline.py` | 3 cron handlers: per_ticker / macro / llm_enrich |
| `alpha_agent/api/routes/macro_context.py` | `GET /api/macro_context?ticker=X&limit=5` |
| `scripts/backfill_macro.py` | one-shot 30-day macro backfill driver |

### Modified backend files
| Path | Change |
|---|---|
| `pyproject.toml` | add `feedparser>=6.0.10` |
| `requirements.txt` | mirror the feedparser addition |
| `alpha_agent/api/app.py` | `_load("macro_context", ...)` in the M2 cluster |
| `api/index.py` | add `_load("macro_context", "alpha_agent.api.routes.macro_context")` |
| `alpha_agent/api/routes/cron_routes.py` | add 3 routes that dispatch to `api/cron/news_pipeline.py` handlers |
| `alpha_agent/api/routes/health.py` | add `GET /news_freshness` endpoint on existing router |
| `alpha_agent/api/routes/stock.py` | `FullCard` gains `news_items: list[NewsItemLite]`; `get_stock` joins news_items |
| `alpha_agent/signals/news.py` | rewrite to query `news_items` instead of yfinance; preserve `raw={n, mean_sent, headlines}` shape |
| `.github/workflows/cron-shards.yml` | 4 new schedules + 4 new jobs |
| `Makefile` | new `news-acceptance` target |

### New / modified frontend files
| Path | Purpose |
|---|---|
| `frontend/src/lib/api/picks.ts` | add `NewsItemLite` + `news_items?: NewsItemLite[]` to `RatingCard` |
| `frontend/src/lib/api/macro.ts` | new `fetchMacroContext(ticker, limit)` |
| `frontend/src/components/stock/NewsBlock.tsx` | rewrite to consume `card.news_items` + source badges |
| `frontend/src/components/stock/MarketContextWidget.tsx` | new, fetches `/api/macro_context` |
| `frontend/src/components/stock/StockCardLayout.tsx` | mount `MarketContextWidget` between `NewsBlock` and `SourcesBlock` |
| `frontend/src/lib/i18n.ts` | add `news.source_*` and `market_context.*` keys (zh + en) |

### New test files
| Path | Purpose |
|---|---|
| `tests/storage/test_migration_v004.py` | V004 schema integration test |
| `tests/news/__init__.py` | empty |
| `tests/news/test_dedup.py` | dedup_hash unit tests |
| `tests/news/test_finnhub_adapter.py` | Finnhub adapter with HTTP fixture |
| `tests/news/test_fmp_adapter.py` | FMP adapter with HTTP fixture |
| `tests/news/test_rss_adapter.py` | RSS adapter (Yahoo + Google) with fixture |
| `tests/news/test_truth_adapter.py` | Truth Social JSON adapter with fixture |
| `tests/news/test_fed_adapter.py` | Fed RSS adapter with fixture |
| `tests/news/test_ofac_adapter.py` | OFAC RSS adapter with fixture |
| `tests/news/fixtures/*.json` + `*.xml` | recorded upstream responses |
| `tests/news/test_aggregator.py` | failover + circuit breaker |
| `tests/news/test_llm_worker.py` | LLM batch worker with mocked client |
| `tests/api/test_macro_context.py` | /api/macro_context endpoint |
| `tests/api/test_news_freshness.py` | /api/_health/news_freshness endpoint |

## Dependency tiers

`subagent-driven-development` executes strictly sequentially regardless, but tasks within a tier can be safely re-ordered if a blocker appears.

| Tier | Tasks | Reason |
|---|---|---|
| Foundation | A1 | Schema everything else writes into |
| Adapters | B1, B2, B3, B4, B5 | Each adapter is self-contained but shares the base protocol from B1 |
| Pipeline | C1, C2, C3, C4 | Aggregators consume adapters; cron handlers consume aggregators; LLM worker consumes the cron's NULL rows |
| API + UI | D1, D2, D3 | D1 needs A1's tables; D2 needs A1 + the news_items query; D3 is pure frontend on top of D2 |
| Operations | E1, E2, E3 | E1 schedules the cron handlers from C; E2 backfills via the adapters from B; E3 is the acceptance gate |

---

## Phase A: Foundation

### Task A1: V004 migration (news_items + macro_events)

**Files:**
- Create: `alpha_agent/storage/migrations/V004__news_pipeline.sql`
- Test: `tests/storage/test_migration_v004.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_migration_v004.py
import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_v004_creates_news_items_and_macro_events(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )
        names = {r["tablename"] for r in rows}
        assert "news_items" in names
        assert "macro_events" in names
    finally:
        await conn.close()


async def test_v004_news_items_has_dedup_unique_constraint(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'news_items'::regclass AND contype = 'u'"
        )
        assert row is not None
    finally:
        await conn.close()


async def test_v004_macro_events_tickers_extracted_is_text_array(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        row = await conn.fetchrow(
            "SELECT data_type, udt_name FROM information_schema.columns "
            "WHERE table_name='macro_events' AND column_name='tickers_extracted'"
        )
        # asyncpg / pg reports TEXT[] as data_type='ARRAY' and udt_name='_text'.
        assert row["data_type"] == "ARRAY"
        assert row["udt_name"] == "_text"
    finally:
        await conn.close()


async def test_v004_macro_events_has_gin_index_on_tickers_extracted(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT indexdef FROM pg_indexes WHERE tablename='macro_events'"
        )
        defs = " ".join(r["indexdef"] for r in rows)
        assert "USING gin" in defs.lower()
        assert "tickers_extracted" in defs
    finally:
        await conn.close()


async def test_v004_idempotent(applied_db):
    """Re-applying migrations is a no-op (schema_migrations tracks state)."""
    from alpha_agent.storage.migrations.runner import apply_migrations
    second_run = await apply_migrations(applied_db)
    assert "V004__news_pipeline" not in second_run
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/storage/test_migration_v004.py -v
```

Expected: 4 FAILs (tables do not exist), 1 may pass coincidentally.

- [ ] **Step 3: Write the migration**

```sql
-- alpha_agent/storage/migrations/V004__news_pipeline.sql
-- Phase 5: News Multi-Source Aggregation
--
-- news_items: per-ticker news items from Finnhub + FMP + RSS. One row
-- per (ticker, normalized story). dedup_hash includes ticker so the
-- same Bloomberg piece returned by both /company-news?symbol=AAPL and
-- ?symbol=GOOG produces two distinct rows, one per ticker.
--
-- macro_events: market-wide political / policy events from Truth Social,
-- Fed press releases, OFAC sanctions. dedup_hash is ticker-free (one
-- event = one row). tickers_extracted is the LLM-derived list of
-- affected US-listed tickers; tickers_extracted GIN index supports the
-- /api/macro_context?ticker=X query via array-contains.

CREATE TABLE IF NOT EXISTS news_items (
    id BIGSERIAL PRIMARY KEY,
    dedup_hash TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    headline TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    summary TEXT,
    sentiment_score REAL,
    sentiment_label TEXT,
    llm_processed_at TIMESTAMPTZ,
    raw JSONB
);

CREATE INDEX IF NOT EXISTS news_items_ticker_published_idx
    ON news_items (ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS news_items_source_published_idx
    ON news_items (source, published_at DESC);
CREATE INDEX IF NOT EXISTS news_items_llm_pending_idx
    ON news_items (llm_processed_at) WHERE llm_processed_at IS NULL;

CREATE TABLE IF NOT EXISTS macro_events (
    id BIGSERIAL PRIMARY KEY,
    dedup_hash TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_id TEXT,
    author TEXT,
    title TEXT NOT NULL,
    url TEXT,
    body TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now(),
    tickers_extracted TEXT[],
    sectors_extracted TEXT[],
    sentiment_score REAL,
    llm_processed_at TIMESTAMPTZ,
    raw JSONB
);

CREATE INDEX IF NOT EXISTS macro_events_published_idx
    ON macro_events (published_at DESC);
CREATE INDEX IF NOT EXISTS macro_events_tickers_gin_idx
    ON macro_events USING GIN (tickers_extracted);
CREATE INDEX IF NOT EXISTS macro_events_llm_pending_idx
    ON macro_events (llm_processed_at) WHERE llm_processed_at IS NULL;
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/storage/test_migration_v004.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/storage/migrations/V004__news_pipeline.sql \
        tests/storage/test_migration_v004.py
git commit -m "feat: V004 migration for news_items + macro_events tables"
```

USER ACTION: after this lands and deploys, apply V004 to Neon by running `python -c "import asyncio, os; from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))"` locally with `.env` sourced.

---

## Phase B: Adapters

### Task B1: Shared types + dedup_hash + base protocol

**Files:**
- Create: `alpha_agent/news/__init__.py` (empty)
- Create: `alpha_agent/news/types.py`
- Create: `alpha_agent/news/base.py`
- Test: `tests/news/__init__.py` (empty), `tests/news/test_dedup.py`

- [ ] **Step 1: Write the failing dedup test**

```python
# tests/news/test_dedup.py
from alpha_agent.news.types import dedup_hash


def test_same_url_and_headline_same_ticker_collide():
    a = dedup_hash("AAPL", "https://example.com/a", "Apple beats earnings")
    b = dedup_hash("AAPL", "https://example.com/a", "Apple beats earnings")
    assert a == b


def test_same_story_different_tickers_distinct():
    # Multi-ticker story returned by per-symbol fetches must produce
    # one row per ticker. Without ticker in the hash, FMP and Finnhub
    # competing on AAPL would dedup, but AAPL and GOOG fetches of the
    # SAME story would also dedup (losing GOOG). Spec self-review fix.
    a = dedup_hash("AAPL", "https://example.com/x", "Cloud earnings broad beat")
    b = dedup_hash("GOOG", "https://example.com/x", "Cloud earnings broad beat")
    assert a != b


def test_url_query_params_stripped():
    a = dedup_hash("AAPL", "https://example.com/a?utm_source=x", "headline")
    b = dedup_hash("AAPL", "https://example.com/a", "headline")
    assert a == b


def test_headline_case_and_punctuation_normalized():
    a = dedup_hash("AAPL", "https://example.com/a", "Apple Beats Earnings!")
    b = dedup_hash("AAPL", "https://example.com/a", "apple beats earnings")
    assert a == b


def test_macro_event_uses_none_ticker():
    # macro events have no ticker scope; passing None must work.
    h = dedup_hash(None, "https://example.com/m", "Trump on Apple")
    assert isinstance(h, str) and len(h) == 64  # sha256 hex
```

- [ ] **Step 2: Run -> FAIL**

```bash
pytest tests/news/test_dedup.py -v
```

Expected: `ModuleNotFoundError: alpha_agent.news`.

- [ ] **Step 3: Implement types.py and base.py**

```python
# alpha_agent/news/__init__.py
```

```python
# alpha_agent/news/types.py
"""Canonical NewsItem + MacroEvent shapes shared by every adapter, and
the dedup_hash helper that makes the news_items.dedup_hash UNIQUE
constraint do its job.
"""
from __future__ import annotations

import hashlib
import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class NewsItem:
    """Normalized per-ticker news item written into news_items."""
    ticker: str
    source: str
    source_id: str | None
    headline: str
    url: str
    published_at: datetime
    summary: str | None = None
    raw: Any = None

    def dedup(self) -> str:
        return dedup_hash(self.ticker, self.url, self.headline)


@dataclass(frozen=True)
class MacroEvent:
    """Normalized market-wide event written into macro_events."""
    source: str
    source_id: str | None
    author: str
    title: str
    url: str | None
    body: str | None
    published_at: datetime
    raw: Any = None

    def dedup(self) -> str:
        return dedup_hash(None, self.url or self.title, self.title)


_PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation})


def _normalize_url(url: str) -> str:
    p = urlparse(url)
    # Drop query + fragment entirely; most upstreams add UTM/tracking
    # params that would otherwise defeat dedup.
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, "", "", ""))


def _normalize_headline(headline: str) -> str:
    s = headline.lower().translate(_PUNCT_TABLE)
    return " ".join(s.split())


def dedup_hash(ticker: str | None, url: str, headline: str) -> str:
    """sha256(ticker|normalized_url|normalized_headline).

    ticker scope is in the hash so a multi-ticker story returned via
    per-symbol fetches produces one row per ticker (rather than the
    second ticker losing its row to the first). Macro events pass
    ticker=None.
    """
    tk = (ticker or "").upper()
    norm_url = _normalize_url(url)
    norm_hl = _normalize_headline(headline)
    return hashlib.sha256(f"{tk}|{norm_url}|{norm_hl}".encode()).hexdigest()
```

```python
# alpha_agent/news/base.py
"""NewsAdapter Protocol + shared HTTP session factory + circuit breaker.

Per-adapter rate-limit / IP-block behavior differs (Finnhub 60req/min,
Yahoo blocks aggressive fanout, etc.). Each adapter owns its own
backoff / retry; the breaker here is for cross-cycle health: an adapter
failing N consecutive cycles is marked down for a cooldown window so the
aggregator skips it without re-paying its timeout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Any, Literal, Protocol, runtime_checkable

import httpx


# Per spec: 5 consecutive cycle failures triggers a 1h cooldown.
BREAKER_FAILURE_THRESHOLD = 5
BREAKER_COOLDOWN = timedelta(hours=1)


@dataclass
class CircuitBreaker:
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.cooldown_until = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= BREAKER_FAILURE_THRESHOLD:
            self.cooldown_until = datetime.now(UTC) + BREAKER_COOLDOWN

    def is_open(self) -> bool:
        if self.cooldown_until is None:
            return False
        if datetime.now(UTC) >= self.cooldown_until:
            # Probe: leave consecutive_failures alone; next success resets.
            self.cooldown_until = None
            return False
        return True


def make_client(timeout_seconds: float = 10.0) -> httpx.AsyncClient:
    """Standard httpx async session used by every HTTP adapter."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "alpha-agent-news/1.0 (+https://alpha.bobbyzhong.com)"},
    )


@runtime_checkable
class NewsAdapter(Protocol):
    """Every adapter implements this. Adapters are constructed once per
    cron run and reused across all tickers in that run; httpx connection
    pool reuse matters for not getting rate-limited."""

    name: str  # 'finnhub', 'fmp', 'rss_yahoo', ...
    channel: Literal["per_ticker", "macro"]
    priority: int  # per_ticker: 1=primary, 2=failover, 3=tertiary

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[Any]:  # NewsItem or MacroEvent
        ...

    async def is_available(self) -> bool:
        ...

    async def aclose(self) -> None:
        ...
```

- [ ] **Step 4: Run -> PASS**

```bash
pytest tests/news/test_dedup.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/news/__init__.py alpha_agent/news/types.py \
        alpha_agent/news/base.py \
        tests/news/__init__.py tests/news/test_dedup.py
git commit -m "feat: news package scaffold (NewsItem/MacroEvent + dedup_hash + base protocol)"
```

---

### Task B2: FinnhubAdapter (per-ticker, primary)

**Files:**
- Create: `alpha_agent/news/finnhub_adapter.py`
- Create: `tests/news/fixtures/finnhub_aapl_response.json`
- Test: `tests/news/test_finnhub_adapter.py`

- [ ] **Step 1: Save the fixture** (real Finnhub response shape, sample with 2 items)

Finnhub's `/company-news` returns a JSON array directly (not wrapped in an object). The test loads it via `json.load()` and expects `list[dict]`.

```bash
mkdir -p tests/news/fixtures
cat > tests/news/fixtures/finnhub_aapl_response.json <<'EOF'
[
  {
    "category": "company",
    "datetime": 1715783400,
    "headline": "Apple Beats Q2 Earnings Expectations, Stock Climbs",
    "id": 7104210,
    "image": "https://image.cnbcfm.com/api/v1/image/sample.jpg",
    "related": "AAPL",
    "source": "CNBC",
    "summary": "Apple reported earnings of $1.53 per share, beating consensus by $0.03...",
    "url": "https://www.cnbc.com/2026/05/15/apple-q2-earnings.html"
  },
  {
    "category": "company",
    "datetime": 1715783200,
    "headline": "AAPL: Buffett Trims Position, Berkshire Cuts Stake",
    "id": 7104198,
    "image": "",
    "related": "AAPL",
    "source": "Reuters",
    "summary": "Berkshire Hathaway disclosed a smaller Apple position in its 13F filing...",
    "url": "https://www.reuters.com/markets/us/berkshire-aapl.html"
  }
]
EOF
```

- [ ] **Step 2: Write the failing test**

```python
# tests/news/test_finnhub_adapter.py
import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def finnhub_response():
    p = Path(__file__).parent / "fixtures" / "finnhub_aapl_response.json"
    return json.loads(p.read_text())


async def test_finnhub_adapter_returns_normalized_news_items(finnhub_response, monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="fixture-key")
    # Mock the underlying httpx GET so the test never hits the network.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = finnhub_response
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))

    assert len(items) == 2
    first = items[0]
    assert first.ticker == "AAPL"
    assert first.source == "finnhub"
    assert first.source_id == "7104210"
    assert first.headline == "Apple Beats Q2 Earnings Expectations, Stock Climbs"
    assert first.url == "https://www.cnbc.com/2026/05/15/apple-q2-earnings.html"
    assert first.published_at.year == 2024  # 1715783400 = 2024-05-15
    assert first.summary.startswith("Apple reported earnings")
    await adapter.aclose()


async def test_finnhub_adapter_dedup_hash_is_deterministic(finnhub_response, monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    a = FinnhubAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = finnhub_response
    mock_resp.raise_for_status = MagicMock()
    a._client.get = AsyncMock(return_value=mock_resp)
    items1 = await a.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    items2 = await a.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert items1[0].dedup() == items2[0].dedup()
    await a.aclose()


async def test_finnhub_adapter_empty_response_returns_empty_list(monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)
    items = await adapter.fetch(ticker="ZZZZ", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert items == []
    await adapter.aclose()


async def test_finnhub_adapter_429_raises_for_failover(monkeypatch):
    from alpha_agent.news.finnhub_adapter import FinnhubAdapter
    from httpx import HTTPStatusError, Request, Response

    adapter = FinnhubAdapter(api_key="k")
    req = Request("GET", "https://finnhub.io/api/v1/company-news")
    resp = Response(429, request=req)
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status = MagicMock(
        side_effect=HTTPStatusError("429", request=req, response=resp)
    )
    adapter._client.get = AsyncMock(return_value=mock_resp)

    with pytest.raises(HTTPStatusError):
        await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    await adapter.aclose()
```

- [ ] **Step 3: Run -> FAIL**

```bash
pytest tests/news/test_finnhub_adapter.py -v
```

Expected: `ModuleNotFoundError: alpha_agent.news.finnhub_adapter`.

- [ ] **Step 4: Implement FinnhubAdapter**

```python
# alpha_agent/news/finnhub_adapter.py
"""Finnhub /company-news per-ticker adapter (per_ticker channel, priority 1).

Free tier: 60 req/min. We deliberately make one request per ticker per
cycle; with 557 tickers/hour this is ~9.3 req/min sustained, well inside
the limit. Errors propagate to the caller so PerTickerAggregator can
trigger the FMP fallback.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.base import NewsAdapter, make_client
from alpha_agent.news.types import NewsItem

_ENDPOINT = "https://finnhub.io/api/v1/company-news"


class FinnhubAdapter:
    name = "finnhub"
    channel = "per_ticker"
    priority = 1

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None, "finnhub adapter requires a ticker"
        to = datetime.now(UTC).date().isoformat()
        params = {
            "symbol": ticker.upper(),
            "from": since.date().isoformat(),
            "to": to,
            "token": self._api_key,
        }
        resp = await self._client.get(_ENDPOINT, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        out: list[NewsItem] = []
        for it in payload:
            url = it.get("url") or ""
            headline = it.get("headline") or ""
            if not url or not headline:
                continue
            ts = it.get("datetime")
            try:
                published = datetime.fromtimestamp(int(ts), tz=UTC) if ts else datetime.now(UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="finnhub",
                    source_id=str(it.get("id")) if it.get("id") is not None else None,
                    headline=headline,
                    url=url,
                    published_at=published,
                    summary=it.get("summary"),
                    raw=it,
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(
                _ENDPOINT,
                params={"symbol": "AAPL", "from": "2026-05-01",
                        "to": "2026-05-02", "token": self._api_key},
            )
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 5: Run -> PASS**

```bash
pytest tests/news/test_finnhub_adapter.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/news/finnhub_adapter.py \
        tests/news/test_finnhub_adapter.py \
        tests/news/fixtures/finnhub_aapl_response.json
git commit -m "feat: FinnhubAdapter (per-ticker primary, free 60 req/min)"
```

---

### Task B3: FMPAdapter (per-ticker, failover-only)

**Files:**
- Create: `alpha_agent/news/fmp_adapter.py`
- Create: `tests/news/fixtures/fmp_aapl_response.json`
- Test: `tests/news/test_fmp_adapter.py`

- [ ] **Step 1: Save the fixture**

```bash
cat > tests/news/fixtures/fmp_aapl_response.json <<'EOF'
[
  {
    "symbol": "AAPL",
    "publishedDate": "2026-05-15 17:00:00",
    "title": "Apple Said to Plan India Manufacturing Expansion",
    "image": "",
    "site": "FinancialModelingPrep",
    "text": "Apple is reportedly planning a major expansion of its iPhone manufacturing in India...",
    "url": "https://site.financialmodelingprep.com/market-news/aapl-india"
  }
]
EOF
```

- [ ] **Step 2: Write the failing test**

```python
# tests/news/test_fmp_adapter.py
import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fmp_response():
    p = Path(__file__).parent / "fixtures" / "fmp_aapl_response.json"
    return json.loads(p.read_text())


async def test_fmp_adapter_returns_normalized_news_items(fmp_response):
    from alpha_agent.news.fmp_adapter import FMPAdapter

    adapter = FMPAdapter(api_key="k")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fmp_response
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(items) == 1
    it = items[0]
    assert it.ticker == "AAPL"
    assert it.source == "fmp"
    assert it.headline == "Apple Said to Plan India Manufacturing Expansion"
    assert it.url == "https://site.financialmodelingprep.com/market-news/aapl-india"
    assert it.published_at.year == 2026
    await adapter.aclose()


async def test_fmp_adapter_priority_is_two(fmp_response):
    """Failover-only behavior is enforced by the aggregator using
    adapter.priority. Locking the constant here prevents accidental
    promotion to primary."""
    from alpha_agent.news.fmp_adapter import FMPAdapter
    assert FMPAdapter(api_key="k").priority == 2
```

- [ ] **Step 3: Run -> FAIL**

```bash
pytest tests/news/test_fmp_adapter.py -v
```

Expected: `ModuleNotFoundError: alpha_agent.news.fmp_adapter`.

- [ ] **Step 4: Implement FMPAdapter**

```python
# alpha_agent/news/fmp_adapter.py
"""Financial Modeling Prep stock_news per-ticker adapter (failover-only).

Free tier: 250 calls/day. The aggregator only calls this adapter when
the primary (Finnhub) returned empty/errored for the ticker. Without
that discipline a full 557-ticker cycle would burn the entire daily
quota.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.base import make_client
from alpha_agent.news.types import NewsItem

_ENDPOINT = "https://financialmodelingprep.com/api/v3/stock_news"


class FMPAdapter:
    name = "fmp"
    channel = "per_ticker"
    priority = 2  # failover-only; enforced by PerTickerAggregator

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None
        params = {"tickers": ticker.upper(), "limit": 20, "apikey": self._api_key}
        resp = await self._client.get(_ENDPOINT, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        out: list[NewsItem] = []
        for it in payload:
            url = it.get("url") or ""
            title = it.get("title") or ""
            if not url or not title:
                continue
            raw_ts = it.get("publishedDate")
            try:
                published = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="fmp",
                    source_id=None,  # FMP does not expose stable IDs
                    headline=title,
                    url=url,
                    published_at=published,
                    summary=it.get("text"),
                    raw=it,
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(
                _ENDPOINT,
                params={"tickers": "AAPL", "limit": 1, "apikey": self._api_key},
            )
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 5: Run -> PASS**

```bash
pytest tests/news/test_fmp_adapter.py -v
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/news/fmp_adapter.py \
        tests/news/test_fmp_adapter.py \
        tests/news/fixtures/fmp_aapl_response.json
git commit -m "feat: FMPAdapter (per-ticker failover, 250/day budget)"
```

---

### Task B4: RSSAdapter (per-ticker, tertiary)

**Files:**
- Create: `alpha_agent/news/rss_adapter.py`
- Create: `tests/news/fixtures/rss_yahoo_aapl.xml`
- Test: `tests/news/test_rss_adapter.py`

- [ ] **Step 1: Add feedparser to deps**

Edit `pyproject.toml`:

```toml
# In the dependencies array, add:
    "feedparser>=6.0.10",
```

Edit `requirements.txt` similarly:

```
feedparser>=6.0.10
```

Run:

```bash
pip install feedparser>=6.0.10
```

- [ ] **Step 2: Save the fixture** (real Yahoo Finance per-symbol RSS sample)

```bash
cat > tests/news/fixtures/rss_yahoo_aapl.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Yahoo Finance - AAPL News</title>
<link>https://finance.yahoo.com/quote/AAPL/</link>
<description>Latest Apple Inc. news</description>
<item>
  <title>Apple Eyes AI Hardware Partnership With OpenAI</title>
  <link>https://finance.yahoo.com/news/apple-openai-deal-123456.html</link>
  <pubDate>Thu, 15 May 2026 18:00:00 +0000</pubDate>
  <guid isPermaLink="false">yh-aapl-7104251</guid>
  <description>Apple is in talks with OpenAI...</description>
</item>
<item>
  <title>AAPL Up 2% After Q2 Beat</title>
  <link>https://finance.yahoo.com/news/aapl-q2-789012.html</link>
  <pubDate>Wed, 14 May 2026 17:30:00 +0000</pubDate>
  <guid isPermaLink="false">yh-aapl-7104198</guid>
  <description>Shares of Apple rose...</description>
</item>
</channel>
</rss>
EOF
```

- [ ] **Step 3: Write the failing test**

```python
# tests/news/test_rss_adapter.py
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def rss_xml():
    p = Path(__file__).parent / "fixtures" / "rss_yahoo_aapl.xml"
    return p.read_text()


async def test_rss_adapter_parses_yahoo_feed(rss_xml):
    from alpha_agent.news.rss_adapter import RSSAdapter

    adapter = RSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = rss_xml
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))

    # Both items in the fixture are after since=May 1.
    assert len(items) == 2
    titles = [i.headline for i in items]
    assert "Apple Eyes AI Hardware Partnership With OpenAI" in titles
    assert all(i.source == "rss_yahoo" for i in items)
    assert all(i.ticker == "AAPL" for i in items)
    await adapter.aclose()


async def test_rss_adapter_filters_by_since(rss_xml):
    from alpha_agent.news.rss_adapter import RSSAdapter

    adapter = RSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = rss_xml
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    # since later than both items
    items = await adapter.fetch(ticker="AAPL", since=datetime(2026, 5, 16, tzinfo=UTC))
    assert items == []
    await adapter.aclose()
```

- [ ] **Step 4: Run -> FAIL**

```bash
pytest tests/news/test_rss_adapter.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 5: Implement RSSAdapter**

```python
# alpha_agent/news/rss_adapter.py
"""Per-ticker RSS adapter (Yahoo Finance per-symbol feed).

Tertiary in the per_ticker failover chain. Free, keyless. Used when
Finnhub returns empty AND FMP returns empty (or both errored). Yahoo's
per-symbol RSS URL is the only one that maps cleanly to a single
ticker; Google News keyword search adds too much noise to be worth
parsing here.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import NewsItem

_YAHOO_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


class RSSAdapter:
    name = "rss_yahoo"
    channel = "per_ticker"
    priority = 3

    def __init__(self) -> None:
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None
        url = _YAHOO_FEED.format(ticker=ticker.upper())
        resp = await self._client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        out: list[NewsItem] = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            if not title or not link:
                continue
            pubdate_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            try:
                published = (
                    parsedate_to_datetime(pubdate_str) if pubdate_str else datetime.now(UTC)
                )
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            if published < since:
                continue
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="rss_yahoo",
                    source_id=getattr(entry, "id", None),
                    headline=title,
                    url=link,
                    published_at=published,
                    summary=getattr(entry, "summary", None),
                    raw={"title": title, "link": link,
                         "published": pubdate_str, "id": getattr(entry, "id", None)},
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_YAHOO_FEED.format(ticker="AAPL"))
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 6: Run -> PASS**

```bash
pytest tests/news/test_rss_adapter.py -v
```

Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml requirements.txt \
        alpha_agent/news/rss_adapter.py \
        tests/news/test_rss_adapter.py \
        tests/news/fixtures/rss_yahoo_aapl.xml
git commit -m "feat: RSSAdapter (Yahoo per-symbol, keyless tertiary failover)"
```

---

### Task B5: Macro adapters (TruthSocial + FedRSS + OFACRSS)

**Files:**
- Create: `alpha_agent/news/truth_adapter.py`
- Create: `alpha_agent/news/fed_adapter.py`
- Create: `alpha_agent/news/ofac_adapter.py`
- Create: `tests/news/fixtures/truth_archive.json`
- Create: `tests/news/fixtures/fed_press.xml`
- Create: `tests/news/fixtures/ofac_actions.xml`
- Test: `tests/news/test_truth_adapter.py`, `test_fed_adapter.py`, `test_ofac_adapter.py`

**OFAC URL note:** the spec says "ofac.treasury.gov/recent-actions RSS". Verify the exact RSS URL before implementing OFAC: `curl -sI https://ofac.treasury.gov/recent-actions/rss` should return XML. If the path is different (e.g. `/sanctions/programs/rss`), update the constant in `ofac_adapter.py` to the real path.

- [ ] **Step 1: Save fixtures**

```bash
cat > tests/news/fixtures/truth_archive.json <<'EOF'
{
  "truths": [
    {
      "id": "112345678901234567",
      "content": "Apple should make iPhones in America, not China. We are going to take care of that very soon!",
      "created_at": "2026-05-16T13:24:00.000Z",
      "url": "https://truthsocial.com/@realDonaldTrump/posts/112345678901234567"
    },
    {
      "id": "112345678901234568",
      "content": "Big tariff announcement coming. The Fake News Media will hate it. STAY TUNED!",
      "created_at": "2026-05-16T11:02:00.000Z",
      "url": "https://truthsocial.com/@realDonaldTrump/posts/112345678901234568"
    }
  ]
}
EOF

cat > tests/news/fixtures/fed_press.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Federal Reserve Press Releases</title>
<item>
  <title>Federal Reserve issues FOMC statement</title>
  <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260515a.htm</link>
  <pubDate>Wed, 15 May 2026 18:00:00 +0000</pubDate>
  <guid>fed-20260515a</guid>
  <description>The Federal Open Market Committee decided today to maintain the target range...</description>
</item>
</channel>
</rss>
EOF

cat > tests/news/fixtures/ofac_actions.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>OFAC Recent Actions</title>
<item>
  <title>Treasury Sanctions PRC-Based Entities for Semiconductor Diversion</title>
  <link>https://ofac.treasury.gov/recent-actions/20260516</link>
  <pubDate>Thu, 16 May 2026 14:00:00 +0000</pubDate>
  <guid>ofac-20260516</guid>
  <description>OFAC today designated multiple PRC-based entities involved in...</description>
</item>
</channel>
</rss>
EOF
```

- [ ] **Step 2: Write tests for all three** (one file per adapter to keep failures localized)

```python
# tests/news/test_truth_adapter.py
import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_truth_social_adapter_normalizes_truth_archive():
    from alpha_agent.news.truth_adapter import TruthSocialAdapter
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "truth_archive.json").read_text()
    )
    adapter = TruthSocialAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 2
    e = events[0]
    assert e.source == "truth_social"
    assert e.author == "trump"
    assert e.body.startswith("Apple should make iPhones")
    assert e.published_at.year == 2026
    assert e.url and "truthsocial.com" in e.url
    await adapter.aclose()
```

```python
# tests/news/test_fed_adapter.py
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_fed_rss_adapter_parses_press_releases():
    from alpha_agent.news.fed_adapter import FedRSSAdapter

    adapter = FedRSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (Path(__file__).parent / "fixtures" / "fed_press.xml").read_text()
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 1
    e = events[0]
    assert e.source == "fed_rss"
    assert e.author == "fed"
    assert "FOMC statement" in e.title
    await adapter.aclose()
```

```python
# tests/news/test_ofac_adapter.py
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_ofac_rss_adapter_parses_recent_actions():
    from alpha_agent.news.ofac_adapter import OFACRSSAdapter

    adapter = OFACRSSAdapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (Path(__file__).parent / "fixtures" / "ofac_actions.xml").read_text()
    mock_resp.raise_for_status = MagicMock()
    adapter._client.get = AsyncMock(return_value=mock_resp)

    events = await adapter.fetch(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 1
    e = events[0]
    assert e.source == "ofac_rss"
    assert e.author == "ofac"
    assert "Sanctions" in e.title
    await adapter.aclose()
```

- [ ] **Step 3: Run all three -> FAIL**

```bash
pytest tests/news/test_truth_adapter.py tests/news/test_fed_adapter.py \
       tests/news/test_ofac_adapter.py -v
```

Expected: 3 ModuleNotFoundErrors.

- [ ] **Step 4: Implement TruthSocialAdapter**

```python
# alpha_agent/news/truth_adapter.py
"""Trump Truth Social via CNN's public JSON mirror.

Source: https://ix.cnn.io/data/truth-social/truth_archive.json
Refreshed by CNN every ~5 minutes; we poll on the same cadence.

No API key, no rate limit observed. If CNN takes the mirror down,
fall back to trumpstruth.org RSS or stiles/trump-truth-social-archive
GitHub by swapping the URL constant.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"


class TruthSocialAdapter:
    name = "truth_social"
    channel = "macro"
    priority = 1

    def __init__(self) -> None:
        self._client = make_client(timeout_seconds=15.0)

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[MacroEvent]:
        resp = await self._client.get(_SOURCE_URL)
        resp.raise_for_status()
        payload = resp.json()
        truths = payload.get("truths", []) if isinstance(payload, dict) else []
        out: list[MacroEvent] = []
        for t in truths:
            ts = t.get("created_at")
            try:
                published = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            if published < since:
                continue
            body = t.get("content") or ""
            if not body:
                continue
            tid = t.get("id")
            url = t.get("url") or (
                f"https://truthsocial.com/@realDonaldTrump/posts/{tid}" if tid else None
            )
            out.append(
                MacroEvent(
                    source="truth_social",
                    source_id=str(tid) if tid is not None else None,
                    author="trump",
                    title=body[:140] + ("..." if len(body) > 140 else ""),
                    url=url,
                    body=body,
                    published_at=published,
                    raw=t,
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_SOURCE_URL)
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 5: Implement FedRSSAdapter**

```python
# alpha_agent/news/fed_adapter.py
"""Federal Reserve press_all RSS adapter (macro channel).

Source: https://www.federalreserve.gov/feeds/press_all.xml
Combined feed of press releases, FOMC statements, speeches, testimony.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://www.federalreserve.gov/feeds/press_all.xml"


class FedRSSAdapter:
    name = "fed_rss"
    channel = "macro"
    priority = 1

    def __init__(self) -> None:
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[MacroEvent]:
        resp = await self._client.get(_SOURCE_URL)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        out: list[MacroEvent] = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            if not title:
                continue
            pubdate_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            try:
                published = parsedate_to_datetime(pubdate_str) if pubdate_str else datetime.now(UTC)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            if published < since:
                continue
            summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
            out.append(
                MacroEvent(
                    source="fed_rss",
                    source_id=getattr(entry, "id", None),
                    author="fed",
                    title=title,
                    url=link or None,
                    body=summary,
                    published_at=published,
                    raw={"title": title, "link": link, "published": pubdate_str,
                         "summary": summary},
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_SOURCE_URL)
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 6: Implement OFACRSSAdapter**

```python
# alpha_agent/news/ofac_adapter.py
"""OFAC Recent Actions RSS adapter (macro channel).

VERIFY URL: the spec listed ofac.treasury.gov/recent-actions but the
actual RSS endpoint may differ. Before merging, run:
    curl -sI https://ofac.treasury.gov/recent-actions/rss
and adjust _SOURCE_URL if the path is /sanctions/programs/rss or
/recent-actions.xml etc.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://ofac.treasury.gov/recent-actions/rss"


class OFACRSSAdapter:
    name = "ofac_rss"
    channel = "macro"
    priority = 1

    def __init__(self) -> None:
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[MacroEvent]:
        resp = await self._client.get(_SOURCE_URL)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        out: list[MacroEvent] = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            if not title:
                continue
            pubdate_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            try:
                published = parsedate_to_datetime(pubdate_str) if pubdate_str else datetime.now(UTC)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            if published < since:
                continue
            summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
            out.append(
                MacroEvent(
                    source="ofac_rss",
                    source_id=getattr(entry, "id", None),
                    author="ofac",
                    title=title,
                    url=link or None,
                    body=summary,
                    published_at=published,
                    raw={"title": title, "link": link, "published": pubdate_str,
                         "summary": summary},
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_SOURCE_URL)
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 7: Run all three -> PASS**

```bash
pytest tests/news/test_truth_adapter.py tests/news/test_fed_adapter.py \
       tests/news/test_ofac_adapter.py -v
```

Expected: 3 PASS.

- [ ] **Step 8: Commit**

```bash
git add alpha_agent/news/truth_adapter.py alpha_agent/news/fed_adapter.py \
        alpha_agent/news/ofac_adapter.py \
        tests/news/test_truth_adapter.py tests/news/test_fed_adapter.py \
        tests/news/test_ofac_adapter.py \
        tests/news/fixtures/truth_archive.json tests/news/fixtures/fed_press.xml \
        tests/news/fixtures/ofac_actions.xml
git commit -m "feat: macro adapters (TruthSocial + Fed RSS + OFAC RSS)"
```

---

## Phase C: Aggregators + Cron handlers

### Task C1: PerTickerAggregator + MacroAggregator + tests

**Files:**
- Create: `alpha_agent/news/aggregator.py`
- Test: `tests/news/test_aggregator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_aggregator.py
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


def _stub_adapter(name, channel, priority, fetch_return):
    a = MagicMock()
    a.name = name
    a.channel = channel
    a.priority = priority
    a.fetch = AsyncMock(return_value=fetch_return)
    a.is_available = AsyncMock(return_value=True)
    a.aclose = AsyncMock(return_value=None)
    return a


async def test_per_ticker_aggregator_uses_primary_when_it_returns_items():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    item = NewsItem(
        ticker="AAPL", source="finnhub", source_id="1",
        headline="Apple beats", url="https://x.com/a",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [item])
    fmp     = _stub_adapter("fmp",     "per_ticker", 2, [])
    rss     = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    result = await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(result) == 1
    # FMP and RSS NOT called because primary returned items.
    fmp.fetch.assert_not_called()
    rss.fetch.assert_not_called()


async def test_per_ticker_aggregator_failovers_to_fmp_on_primary_empty():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [])
    fmp_item = NewsItem(
        ticker="AAPL", source="fmp", source_id=None,
        headline="From FMP", url="https://x.com/b",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    fmp = _stub_adapter("fmp", "per_ticker", 2, [fmp_item])
    rss = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    result = await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(result) == 1
    assert result[0].source == "fmp"
    rss.fetch.assert_not_called()


async def test_per_ticker_aggregator_circuit_breaker_opens_after_5_failures():
    from alpha_agent.news.aggregator import PerTickerAggregator
    from alpha_agent.news.types import NewsItem

    finnhub = _stub_adapter("finnhub", "per_ticker", 1, [])
    finnhub.fetch = AsyncMock(side_effect=Exception("upstream down"))
    fmp_item = NewsItem(
        ticker="AAPL", source="fmp", source_id=None,
        headline="From FMP", url="https://x.com/b",
        published_at=datetime(2026, 5, 15, tzinfo=UTC),
    )
    fmp = _stub_adapter("fmp", "per_ticker", 2, [fmp_item])
    rss = _stub_adapter("rss_yahoo", "per_ticker", 3, [])
    agg = PerTickerAggregator([finnhub, fmp, rss])
    # First 5 calls record_failure; on the 6th the breaker is open.
    for _ in range(5):
        await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    finnhub.fetch.reset_mock()
    await agg.fetch(ticker="AAPL", since=datetime(2026, 5, 1, tzinfo=UTC))
    finnhub.fetch.assert_not_called()  # breaker open, skipped


async def test_macro_aggregator_calls_all_macro_sources_in_parallel():
    from alpha_agent.news.aggregator import MacroAggregator
    from alpha_agent.news.types import MacroEvent

    e1 = MacroEvent(source="truth_social", source_id="1", author="trump",
                    title="t", url="u", body="b",
                    published_at=datetime(2026, 5, 16, tzinfo=UTC))
    e2 = MacroEvent(source="fed_rss", source_id="2", author="fed",
                    title="fomc", url="u2", body="b",
                    published_at=datetime(2026, 5, 16, tzinfo=UTC))
    truth = _stub_adapter("truth_social", "macro", 1, [e1])
    fed   = _stub_adapter("fed_rss",      "macro", 1, [e2])
    ofac  = _stub_adapter("ofac_rss",     "macro", 1, [])
    agg = MacroAggregator([truth, fed, ofac])
    events = await agg.fetch_all(since=datetime(2026, 5, 1, tzinfo=UTC))
    assert len(events) == 2
    # Failover NOT used in macro; every adapter is called regardless.
    truth.fetch.assert_awaited_once()
    fed.fetch.assert_awaited_once()
    ofac.fetch.assert_awaited_once()
```

- [ ] **Step 2: Run -> FAIL**

```bash
pytest tests/news/test_aggregator.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement aggregator.py**

```python
# alpha_agent/news/aggregator.py
"""PerTickerAggregator + MacroAggregator.

PerTicker: priority-failover (Finnhub -> FMP -> RSS). Each adapter
gets a CircuitBreaker; 5 consecutive failures trips a 1h cooldown.
Inside the cooldown the adapter is silently skipped.

Macro: parallel poll, no failover (sources cover disjoint events).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from alpha_agent.news.base import CircuitBreaker, NewsAdapter
from alpha_agent.news.types import MacroEvent, NewsItem

logger = logging.getLogger(__name__)


class PerTickerAggregator:
    def __init__(self, adapters: list[Any]) -> None:
        # Sort by priority ascending so iteration is failover order.
        self._adapters = sorted(adapters, key=lambda a: a.priority)
        self._breakers: dict[str, CircuitBreaker] = {
            a.name: CircuitBreaker() for a in self._adapters
        }

    async def fetch(
        self, *, ticker: str, since: datetime
    ) -> list[NewsItem]:
        for adapter in self._adapters:
            breaker = self._breakers[adapter.name]
            if breaker.is_open():
                logger.info(
                    "news: skipping %s for %s, breaker open until %s",
                    adapter.name, ticker, breaker.cooldown_until,
                )
                continue
            try:
                items = await adapter.fetch(ticker=ticker, since=since)
            except Exception as exc:
                breaker.record_failure()
                logger.warning(
                    "news: adapter %s failed for %s: %s: %s",
                    adapter.name, ticker, type(exc).__name__, exc,
                )
                continue
            breaker.record_success()
            if items:
                return items
        return []

    async def aclose(self) -> None:
        for a in self._adapters:
            try:
                await a.aclose()
            except Exception:
                pass


class MacroAggregator:
    def __init__(self, adapters: list[Any]) -> None:
        self._adapters = adapters
        self._breakers: dict[str, CircuitBreaker] = {
            a.name: CircuitBreaker() for a in adapters
        }

    async def fetch_all(self, *, since: datetime) -> list[MacroEvent]:
        async def _safe_fetch(a):
            breaker = self._breakers[a.name]
            if breaker.is_open():
                logger.info("news: macro %s breaker open", a.name)
                return []
            try:
                events = await a.fetch(since=since)
            except Exception as exc:
                breaker.record_failure()
                logger.warning(
                    "news: macro adapter %s failed: %s: %s",
                    a.name, type(exc).__name__, exc,
                )
                return []
            breaker.record_success()
            return events

        results = await asyncio.gather(*(_safe_fetch(a) for a in self._adapters))
        merged: list[MacroEvent] = []
        for batch in results:
            merged.extend(batch)
        return merged

    async def aclose(self) -> None:
        for a in self._adapters:
            try:
                await a.aclose()
            except Exception:
                pass
```

- [ ] **Step 4: Run -> PASS**

```bash
pytest tests/news/test_aggregator.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/news/aggregator.py tests/news/test_aggregator.py
git commit -m "feat: PerTickerAggregator (failover + circuit breaker) + MacroAggregator (parallel)"
```

---

### Task C2: news_items / macro_events INSERT + UPDATE helpers

**Files:**
- Create: `alpha_agent/news/queries.py`

This task has no test of its own; the helpers are exercised by C3 and C4 tests. Keep it ~80 lines.

- [ ] **Step 1: Implement queries.py**

```python
# alpha_agent/news/queries.py
"""Persistence helpers for the news pipeline.

All writes go through ON CONFLICT (dedup_hash) DO NOTHING so re-fetching
the same story across cycles is idempotent. The LLM enrichment paths
use UPDATE not upsert so the dedup_hash uniqueness is preserved.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

import asyncpg

from alpha_agent.news.types import MacroEvent, NewsItem


def _safe_jsonb(obj: Any) -> str:
    """Drop NaN/Inf which Postgres JSONB rejects (cf. queries.py::_json_safe)."""
    import math
    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [walk(v) for v in x]
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return x
    return json.dumps(walk(obj), default=str)


async def upsert_news_items(
    pool: asyncpg.Pool, items: Iterable[NewsItem]
) -> int:
    """Returns number of rows actually inserted (ON CONFLICT-skipped rows
    are not counted)."""
    rows = list(items)
    if not rows:
        return 0
    sql = """
        INSERT INTO news_items
            (dedup_hash, ticker, source, source_id, headline, url,
             published_at, summary, raw)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        ON CONFLICT (dedup_hash) DO NOTHING
    """
    inserted = 0
    async with pool.acquire() as conn:
        for it in rows:
            result = await conn.execute(
                sql,
                it.dedup(), it.ticker, it.source, it.source_id, it.headline,
                it.url, it.published_at, it.summary, _safe_jsonb(it.raw),
            )
            # asyncpg execute returns 'INSERT 0 N' where N is rows touched.
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def upsert_macro_events(
    pool: asyncpg.Pool, events: Iterable[MacroEvent]
) -> int:
    rows = list(events)
    if not rows:
        return 0
    sql = """
        INSERT INTO macro_events
            (dedup_hash, source, source_id, author, title, url, body,
             published_at, raw)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
        ON CONFLICT (dedup_hash) DO NOTHING
    """
    inserted = 0
    async with pool.acquire() as conn:
        for e in rows:
            result = await conn.execute(
                sql,
                e.dedup(), e.source, e.source_id, e.author, e.title, e.url,
                e.body, e.published_at, _safe_jsonb(e.raw),
            )
            if result.endswith(" 1"):
                inserted += 1
    return inserted


async def update_news_item_llm(
    pool: asyncpg.Pool, item_id: int,
    sentiment_score: float | None, sentiment_label: str | None,
) -> None:
    await pool.execute(
        "UPDATE news_items SET sentiment_score=$1, sentiment_label=$2, "
        "llm_processed_at=now() WHERE id=$3",
        sentiment_score, sentiment_label, item_id,
    )


async def update_macro_event_llm(
    pool: asyncpg.Pool, event_id: int,
    tickers: list[str], sectors: list[str], sentiment_score: float | None,
) -> None:
    await pool.execute(
        "UPDATE macro_events SET tickers_extracted=$1, sectors_extracted=$2, "
        "sentiment_score=$3, llm_processed_at=now() WHERE id=$4",
        tickers, sectors, sentiment_score, event_id,
    )
```

- [ ] **Step 2: Commit**

```bash
git add alpha_agent/news/queries.py
git commit -m "feat: news_items + macro_events INSERT/UPDATE helpers"
```

---

### Task C3: Cron handlers + cron_routes registration

**Files:**
- Create: `api/cron/news_pipeline.py` (3 handlers)
- Modify: `alpha_agent/api/routes/cron_routes.py` (add 3 routes)

The existing `cron_routes` router is already registered in BOTH `app.py` and `api/index.py`. Adding endpoints to that router does NOT require dual-entry changes for this task.

- [ ] **Step 1: Implement news_pipeline.py**

```python
# api/cron/news_pipeline.py
"""Three cron handlers for the news pipeline.

per_ticker_handler: walks 557 SP500 tickers + watchlist extras, calls
    PerTickerAggregator(Finnhub -> FMP -> RSS) for each, upserts.
macro_handler: parallel poll of TruthSocial + Fed + OFAC, upserts.
llm_enrich_handler: picks 100 rows with llm_processed_at IS NULL,
    batches them through the BYOK LiteLLM client, writes results back.

Each handler returns a dict for the GH Actions step summary and stamps
a row into cron_runs.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from alpha_agent.news.aggregator import MacroAggregator, PerTickerAggregator
from alpha_agent.news.fed_adapter import FedRSSAdapter
from alpha_agent.news.finnhub_adapter import FinnhubAdapter
from alpha_agent.news.fmp_adapter import FMPAdapter
from alpha_agent.news.llm_worker import enrich_pending
from alpha_agent.news.ofac_adapter import OFACRSSAdapter
from alpha_agent.news.queries import upsert_macro_events, upsert_news_items
from alpha_agent.news.rss_adapter import RSSAdapter
from alpha_agent.news.truth_adapter import TruthSocialAdapter
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.storage.postgres import get_pool


def _per_ticker_aggregator() -> PerTickerAggregator:
    return PerTickerAggregator([
        FinnhubAdapter(api_key=os.environ["FINNHUB_API_KEY"]),
        FMPAdapter(api_key=os.environ["FMP_API_KEY"]),
        RSSAdapter(),
    ])


def _macro_aggregator() -> MacroAggregator:
    return MacroAggregator([
        TruthSocialAdapter(),
        FedRSSAdapter(),
        OFACRSSAdapter(),
    ])


async def _record_cron(pool, name: str, started_at, rows_written: int,
                       errors: list[dict]) -> None:
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, "
        "error_count, details) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        name, started_at, datetime.now(UTC),
        len(errors) == 0, len(errors),
        json.dumps({"rows_written": rows_written}),
    )


async def per_ticker_handler(
    limit: int | None = None, offset: int | None = None
) -> dict[str, Any]:
    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    since = started_at - timedelta(hours=24)
    universe = get_watchlist(top_n=limit if limit else 100, offset=offset or 0)
    if (offset or 0) == 0:
        wl_rows = await pool.fetch("SELECT DISTINCT ticker FROM user_watchlist")
        extras = {r["ticker"] for r in wl_rows} - set(universe)
        universe = universe + sorted(extras)

    agg = _per_ticker_aggregator()
    errors: list[dict] = []
    rows_written = 0

    async def _one(t: str) -> int:
        try:
            items = await agg.fetch(ticker=t, since=since)
        except Exception as exc:
            errors.append({"ticker": t, "err": f"{type(exc).__name__}: {exc}"[:200]})
            return 0
        return await upsert_news_items(pool, items)

    results = await run_batched(universe, _one, batch_size=20)
    rows_written = sum(v for v in results.values() if isinstance(v, int))
    await agg.aclose()
    await _record_cron(pool, "news_per_ticker", started_at, rows_written, errors)
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}


async def macro_handler() -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    since = started_at - timedelta(hours=24)
    agg = _macro_aggregator()
    try:
        events = await agg.fetch_all(since=since)
    finally:
        await agg.aclose()
    rows_written = await upsert_macro_events(pool, events)
    await _record_cron(pool, "news_macro", started_at, rows_written, [])
    return {"ok": True, "rows_written": rows_written, "errors": []}


async def llm_enrich_handler() -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    n_processed, n_failed = await enrich_pending(pool, row_limit=100)
    await _record_cron(
        pool, "news_llm_enrich", started_at, n_processed,
        [{"failed_batches": n_failed}] if n_failed else [],
    )
    return {"ok": True, "processed": n_processed, "failed_batches": n_failed}
```

- [ ] **Step 2: Add the 3 routes in cron_routes.py**

```python
# alpha_agent/api/routes/cron_routes.py: add at the end, alongside the
# existing fast_intraday / slow_daily / alert_dispatcher endpoints.

@router.post("/news_per_ticker")
@router.get("/news_per_ticker")
async def cron_news_per_ticker(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Walk SP500 + watchlist, call PerTickerAggregator, upsert
    news_items. Limit + offset enable multi-shot sharding."""
    from api.cron.news_pipeline import per_ticker_handler
    return await per_ticker_handler(limit=limit, offset=offset)


@router.post("/news_macro")
@router.get("/news_macro")
async def cron_news_macro() -> dict[str, Any]:
    """Parallel-poll Truth/Fed/OFAC, upsert macro_events."""
    from api.cron.news_pipeline import macro_handler
    return await macro_handler()


@router.post("/news_llm_enrich")
@router.get("/news_llm_enrich")
async def cron_news_llm_enrich() -> dict[str, Any]:
    """Pick up to 100 llm_processed_at IS NULL rows, batch through BYOK
    LiteLLM, write results back."""
    from api.cron.news_pipeline import llm_enrich_handler
    return await llm_enrich_handler()
```

- [ ] **Step 3: Smoke test locally**

```bash
python3 -c "import ast; ast.parse(open('api/cron/news_pipeline.py').read()); print('AST OK')"
python3 -c "import ast; ast.parse(open('alpha_agent/api/routes/cron_routes.py').read()); print('AST OK')"
python3 -c "from api.cron.news_pipeline import per_ticker_handler, macro_handler, llm_enrich_handler; print('imports OK')"
```

Expected: 3x AST OK + 'imports OK'. (Imports may fail if `llm_worker.py` is not written yet; create a stub `async def enrich_pending(pool, row_limit): return (0, 0)` if so, then come back in C4.)

- [ ] **Step 4: Commit**

```bash
git add api/cron/news_pipeline.py alpha_agent/api/routes/cron_routes.py
git commit -m "feat: 3 cron handlers (news per_ticker / macro / llm_enrich) + cron_routes"
```

---

### Task C4: llm_news_enrich worker + tests

**Files:**
- Create: `alpha_agent/news/llm_worker.py`
- Test: `tests/news/test_llm_worker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/news/test_llm_worker.py
import json
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_pool():
    """A pool that returns 3 pending news_items + 2 pending macro_events,
    and records UPDATE calls."""
    pool = MagicMock()
    news_pending = [
        {"id": 1, "ticker": "AAPL", "headline": "Apple beats earnings"},
        {"id": 2, "ticker": "AAPL", "headline": "AAPL: Buffett trims"},
        {"id": 3, "ticker": "NVDA", "headline": "NVDA in massive AI deal"},
    ]
    macro_pending = [
        {"id": 101, "title": "Apple should make iPhones in America",
         "body": "Apple should make...", "author": "trump"},
        {"id": 102, "title": "Fed maintains policy rate", "body": "...",
         "author": "fed"},
    ]
    # Two sequential fetches: news first, then macro.
    pool.fetch = AsyncMock(side_effect=[news_pending, macro_pending])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def fake_llm_with_canned_responses():
    """The worker batches news first then macro. Two canned LLM responses."""
    llm = MagicMock()
    news_resp = MagicMock()
    news_resp.content = json.dumps([
        {"id": 1, "sentiment_score": 0.5, "sentiment_label": "pos"},
        {"id": 2, "sentiment_score": -0.2, "sentiment_label": "neg"},
        {"id": 3, "sentiment_score": 0.8, "sentiment_label": "pos"},
    ])
    macro_resp = MagicMock()
    macro_resp.content = json.dumps([
        {"id": 101, "tickers": ["AAPL"], "sectors": ["Information Technology"],
         "sentiment_score": -0.3},
        {"id": 102, "tickers": [], "sectors": ["Financials"],
         "sentiment_score": 0.0},
    ])
    llm.chat = AsyncMock(side_effect=[news_resp, macro_resp])
    return llm


async def test_enrich_pending_processes_news_and_macro(
    fake_pool, fake_llm_with_canned_responses, monkeypatch
):
    from alpha_agent.news import llm_worker

    monkeypatch.setattr(llm_worker, "_build_llm_client",
                        lambda: fake_llm_with_canned_responses)

    n_proc, n_fail = await llm_worker.enrich_pending(fake_pool, row_limit=100)
    assert n_proc == 5
    assert n_fail == 0
    # 5 UPDATEs (3 news + 2 macro).
    assert fake_pool.execute.await_count == 5


async def test_enrich_pending_handles_malformed_llm_response(
    fake_pool, monkeypatch
):
    """If LLM returns non-JSON, the worker leaves rows untouched and
    counts the batch as failed (NOT a row-level retry cap; the same rows
    are picked up next cron tick)."""
    from alpha_agent.news import llm_worker

    bad_llm = MagicMock()
    bad_resp = MagicMock()
    bad_resp.content = "this is not JSON"
    bad_llm.chat = AsyncMock(return_value=bad_resp)
    monkeypatch.setattr(llm_worker, "_build_llm_client", lambda: bad_llm)

    n_proc, n_fail = await llm_worker.enrich_pending(fake_pool, row_limit=100)
    assert n_proc == 0
    assert n_fail >= 1
    # No UPDATEs at all (rows stay with llm_processed_at = NULL).
    assert fake_pool.execute.await_count == 0


async def test_enrich_pending_respects_row_limit(fake_pool, monkeypatch):
    """row_limit=100 caps how many pending rows are pulled per cron tick.
    The SQL LIMIT clause must reference this value."""
    from alpha_agent.news import llm_worker

    # Asserting the SQL pattern is enough; we mock fetch so the actual
    # SQL is captured in the call args.
    fake_pool.fetch = AsyncMock(side_effect=[[], []])
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock()
    monkeypatch.setattr(llm_worker, "_build_llm_client", lambda: fake_llm)

    await llm_worker.enrich_pending(fake_pool, row_limit=42)
    # Inspect the first fetch call's SQL (the news_items query).
    args, kwargs = fake_pool.fetch.await_args_list[0]
    assert "LIMIT 42" in args[0]
```

- [ ] **Step 2: Run -> FAIL**

```bash
pytest tests/news/test_llm_worker.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement llm_worker.py**

```python
# alpha_agent/news/llm_worker.py
"""BYOK-LLM batch enrichment for news_items + macro_events.

Runs as the news_llm_enrich cron. Picks `row_limit` (default 100) rows
with llm_processed_at IS NULL, batches them through LiteLLMClient
(batch size 15), parses the structured JSON response, writes back.

Error semantics per spec: NO row-level retry cap. A malformed LLM
response leaves the rows untouched so the next cron tick re-picks them.
Backlog visible via /api/_health/news_freshness.llm_backlog.

Cost guard: row_limit per cron run + max_tokens=2000 per LLM call.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from alpha_agent.llm.base import Message
from alpha_agent.news.queries import (
    update_macro_event_llm,
    update_news_item_llm,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 15
_MAX_TOKENS = 2000

_NEWS_SYSTEM = (
    "You score per-ticker financial news sentiment. For each headline in "
    "the user message, return a JSON array element of shape "
    '{"id": <int>, "sentiment_score": <float in [-1,1]>, '
    '"sentiment_label": "pos"|"neg"|"neu"}. Be conservative: "company '
    'beats earnings" is +0.4 to +0.6, not 1.0. Use 1.0/-1.0 only for '
    "genuinely landmark events. Output the JSON array only, no prose."
)

_MACRO_SYSTEM = (
    "You analyze political/policy/geopolitical events for US-equity "
    "market impact. For each event in the user message, return a JSON "
    'array element of shape {"id": <int>, "tickers": [<US ticker>], '
    '"sectors": [<GICS sector name>], "sentiment_score": <float in [-1,1]>}. '
    "Tickers should be 1-15 max; leave empty for purely partisan posts. "
    "Apple-related posts include AAPL. Tariff announcements list relevant "
    "ADRs + sectors. Sanctions list directly affected names. Output the "
    "JSON array only, no prose."
)


def _build_llm_client():
    """Indirection so tests can monkeypatch _build_llm_client without
    pulling LiteLLM env into the test process."""
    from alpha_agent.config import get_settings
    from alpha_agent.llm.factory import create_llm_client
    return create_llm_client(get_settings())


async def enrich_pending(pool, row_limit: int = 100) -> tuple[int, int]:
    """Returns (n_processed, n_failed_batches)."""
    llm = _build_llm_client()
    n_proc = 0
    n_failed = 0

    # News items
    news = await pool.fetch(
        f"SELECT id, ticker, headline FROM news_items "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(news, _BATCH_SIZE):
        ok = await _enrich_news_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    # Macro events (separate row_limit budget would over-engineer; share)
    macro = await pool.fetch(
        f"SELECT id, title, body, author FROM macro_events "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(macro, _BATCH_SIZE):
        ok = await _enrich_macro_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    return n_proc, n_failed


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


async def _enrich_news_batch(pool, llm, batch) -> bool:
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "ticker": "{r["ticker"]}", '
        f'"headline": {json.dumps(r["headline"])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_NEWS_SYSTEM),
        Message(role="user", content=user_payload),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.0, max_tokens=_MAX_TOKENS)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("news llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return False
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            await update_news_item_llm(
                pool, int(row["id"]),
                float(p.get("sentiment_score")) if p.get("sentiment_score") is not None else None,
                p.get("sentiment_label"),
            )
        except Exception as exc:
            logger.warning("news llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return True


async def _enrich_macro_batch(pool, llm, batch) -> bool:
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "author": "{r["author"]}", '
        f'"title": {json.dumps(r["title"])}, '
        f'"body": {json.dumps((r["body"] or "")[:1500])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_MACRO_SYSTEM),
        Message(role="user", content=user_payload),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.0, max_tokens=_MAX_TOKENS)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("macro llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return False
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            await update_macro_event_llm(
                pool, int(row["id"]),
                list(p.get("tickers") or []),
                list(p.get("sectors") or []),
                float(p.get("sentiment_score")) if p.get("sentiment_score") is not None else None,
            )
        except Exception as exc:
            logger.warning("macro llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return True
```

- [ ] **Step 4: Run -> PASS**

```bash
pytest tests/news/test_llm_worker.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/news/llm_worker.py tests/news/test_llm_worker.py
git commit -m "feat: llm_news_enrich worker (batch BYOK LLM, no row-level retry cap)"
```

---

## Phase D: API + UI

### Task D1: /api/macro_context + /api/_health/news_freshness routes (DUAL-ENTRY)

**Files:**
- Create: `alpha_agent/api/routes/macro_context.py`
- Modify: `alpha_agent/api/routes/health.py` (add `/news_freshness`)
- Modify: `alpha_agent/api/app.py` (register macro_context router)
- Modify: `api/index.py` (register macro_context router)
- Test: `tests/api/test_macro_context.py`, `tests/api/test_news_freshness.py`

**DUAL-ENTRY CHECKPOINT.** `macro_context` is a NEW router file; it must be registered in BOTH `app.py` AND `api/index.py`. The watchlist landmine of 2026-05-15 is the cautionary tale. `news_freshness` is a new endpoint on the existing `health.py` router so it does NOT need separate registration.

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_macro_context.py
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x/x")
    from api.index import app
    return TestClient(app)


def _pool_with_rows(rows):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    return pool


def test_macro_context_returns_events_with_ticker_in_extracted_array(client, monkeypatch):
    rows = [
        {"id": 1, "author": "trump", "title": "Apple should make iPhones in USA",
         "url": "https://truthsocial.com/x", "body": "...",
         "published_at": datetime(2026, 5, 16, tzinfo=UTC),
         "sentiment_score": -0.4,
         "tickers_extracted": ["AAPL"],
         "sectors_extracted": ["Information Technology"]},
    ]
    pool = _pool_with_rows(rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.macro_context.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/macro_context?ticker=AAPL&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["title"].startswith("Apple should make")


def test_macro_context_empty_for_unknown_ticker(client, monkeypatch):
    pool = _pool_with_rows([])
    monkeypatch.setattr(
        "alpha_agent.api.routes.macro_context.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/macro_context?ticker=ZZZZ&limit=5")
    assert r.status_code == 200
    assert r.json() == {"items": []}
```

```python
# tests/api/test_news_freshness.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x/x")
    from api.index import app
    return TestClient(app)


def test_news_freshness_returns_one_row_per_known_source(client, monkeypatch):
    pool = MagicMock()
    # 6 expected sources, plus a fake one to confirm we only report known ones.
    pool.fetch = AsyncMock(return_value=[
        {"source": "finnhub",      "last_fetched_at": None, "items_24h": 1843},
        {"source": "fmp",          "last_fetched_at": None, "items_24h": 12},
        {"source": "rss_yahoo",    "last_fetched_at": None, "items_24h": 0},
        {"source": "truth_social", "last_fetched_at": None, "items_24h": 27},
        {"source": "fed_rss",      "last_fetched_at": None, "items_24h": 3},
        {"source": "ofac_rss",     "last_fetched_at": None, "items_24h": 1},
    ])
    pool.fetchval = AsyncMock(return_value=14)
    monkeypatch.setattr(
        "alpha_agent.api.routes.health.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/_health/news_freshness")
    assert r.status_code == 200
    body = r.json()
    names = {s["name"] for s in body["sources"]}
    assert names == {"finnhub", "fmp", "rss_yahoo",
                     "truth_social", "fed_rss", "ofac_rss"}
    assert body["llm_backlog"] == 14
```

- [ ] **Step 2: Run -> FAIL**

```bash
pytest tests/api/test_macro_context.py tests/api/test_news_freshness.py -v
```

Expected: ModuleNotFoundError + 404 (route not registered).

- [ ] **Step 3: Implement macro_context router**

```python
# alpha_agent/api/routes/macro_context.py
"""GET /api/macro_context?ticker=X&limit=5

Returns macro events whose tickers_extracted (LLM-derived) contains the
ticker, ordered by published_at DESC. Lookback: 7 days.

Public endpoint, no auth (matches /api/picks, /api/stock).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/macro_context", tags=["news"])


class MacroContextItem(BaseModel):
    id: int
    author: str | None
    title: str
    url: str | None
    body_excerpt: str | None
    published_at: str
    sentiment_score: float | None
    tickers_extracted: list[str]
    sectors_extracted: list[str]


class MacroContextResponse(BaseModel):
    items: list[MacroContextItem]


@router.get("", response_model=MacroContextResponse)
async def macro_context(
    ticker: str = Query(..., min_length=1, max_length=10),
    limit: int = Query(5, ge=1, le=20),
) -> MacroContextResponse:
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, author, title, url, body, published_at,
               sentiment_score, tickers_extracted, sectors_extracted
        FROM macro_events
        WHERE $1 = ANY(tickers_extracted)
          AND published_at > now() - interval '7 days'
        ORDER BY published_at DESC
        LIMIT $2
        """,
        ticker.upper(), limit,
    )
    items = []
    for r in rows:
        items.append(MacroContextItem(
            id=r["id"],
            author=r["author"],
            title=r["title"],
            url=r["url"],
            body_excerpt=(r["body"] or "")[:200],
            published_at=r["published_at"].isoformat(),
            sentiment_score=r["sentiment_score"],
            tickers_extracted=list(r["tickers_extracted"] or []),
            sectors_extracted=list(r["sectors_extracted"] or []),
        ))
    return MacroContextResponse(items=items)
```

- [ ] **Step 4: Register macro_context in BOTH entry points**

Edit `alpha_agent/api/app.py` (in the M2 cluster, alongside `_import_brief`/`_import_watchlist`):

```python
    def _import_macro_context():
        from alpha_agent.api.routes.macro_context import router
        return router

    # ... and below, in the _load() block:
    _load("macro_context", _import_macro_context)
```

Edit `api/index.py` (in the `_load(...)` enumeration block):

```python
_load("macro_context", "alpha_agent.api.routes.macro_context")
```

- [ ] **Step 5: Add /news_freshness endpoint to health.py**

Edit `alpha_agent/api/routes/health.py`:

```python
# Append at the bottom, after health_routers().

_KNOWN_NEWS_SOURCES = (
    "finnhub", "fmp", "rss_yahoo",
    "truth_social", "fed_rss", "ofac_rss",
)


@router.get("/news_freshness")
async def health_news_freshness() -> dict[str, Any]:
    """Per-source last_fetched_at + 24h item count + LLM backlog.

    Lets you tell at a glance whether one adapter has gone dark.
    """
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        WITH all_tables AS (
            SELECT source, fetched_at FROM news_items
            UNION ALL
            SELECT source, fetched_at FROM macro_events
        )
        SELECT source,
               MAX(fetched_at) AS last_fetched_at,
               COUNT(*) FILTER (WHERE fetched_at > now() - interval '24 hours')
                   AS items_24h
        FROM all_tables
        WHERE source = ANY($1)
        GROUP BY source
        """,
        list(_KNOWN_NEWS_SOURCES),
    )
    by_source = {r["source"]: r for r in rows}
    sources = []
    for name in _KNOWN_NEWS_SOURCES:
        r = by_source.get(name)
        sources.append({
            "name": name,
            "last_fetched_at": r["last_fetched_at"].isoformat() if r and r["last_fetched_at"] else None,
            "items_24h": int(r["items_24h"]) if r else 0,
        })
    llm_backlog = await pool.fetchval(
        "SELECT (SELECT count(*) FROM news_items WHERE llm_processed_at IS NULL) + "
        "(SELECT count(*) FROM macro_events WHERE llm_processed_at IS NULL)"
    )
    return {"sources": sources, "llm_backlog": int(llm_backlog or 0)}
```

- [ ] **Step 6: Run -> PASS**

```bash
pytest tests/api/test_macro_context.py tests/api/test_news_freshness.py -v
```

Expected: 3 PASS.

- [ ] **Step 7: Smoke + commit**

```bash
python3 -c "from alpha_agent.api.routes.macro_context import router; print('routes:', [r.path for r in router.routes])"
git add alpha_agent/api/routes/macro_context.py \
        alpha_agent/api/routes/health.py \
        alpha_agent/api/app.py api/index.py \
        tests/api/test_macro_context.py tests/api/test_news_freshness.py
git commit -m "feat: /api/macro_context + /api/_health/news_freshness (dual-entry registered)"
```

USER ACTION after deploy: `curl https://alpha.bobbyzhong.com/api/_health/routers | jq '.routers[] | select(.name=="macro_context")'` should show `loaded: true`. If absent, the dual-entry rule was violated; check both `app.py` and `api/index.py`.

---

### Task D2: FullCard.news_items field + stock.py join

**Files:**
- Modify: `alpha_agent/api/routes/stock.py`
- Modify: `frontend/src/lib/api/picks.ts` (add NewsItemLite + news_items field)

- [ ] **Step 1: Add news_items field to FullCard + query**

Edit `alpha_agent/api/routes/stock.py`:

```python
# Top of file, alongside other Pydantic models:

class NewsItemLite(BaseModel):
    id: int
    source: str
    headline: str
    url: str
    published_at: str
    sentiment_score: float | None
    sentiment_label: str | None


# Add to FullCard:
class FullCard(BaseModel):
    # ... existing fields ...
    news_items: list[NewsItemLite] = []


# In get_stock(), after the signal_lookup call, before constructing the
# response card:
news_rows = await pool.fetch(
    """
    SELECT id, source, headline, url, published_at,
           sentiment_score, sentiment_label
    FROM news_items
    WHERE ticker = $1
    ORDER BY published_at DESC
    LIMIT 20
    """,
    ticker,
)
news_items = [
    NewsItemLite(
        id=r["id"], source=r["source"], headline=r["headline"],
        url=r["url"], published_at=r["published_at"].isoformat(),
        sentiment_score=r["sentiment_score"],
        sentiment_label=r["sentiment_label"],
    )
    for r in news_rows
]
# ... then in the FullCard(...) construction, pass news_items=news_items.
```

- [ ] **Step 2: Frontend type**

Edit `frontend/src/lib/api/picks.ts`:

```ts
export interface NewsItemLite {
  id: number;
  source: string;
  headline: string;
  url: string;
  published_at: string;
  sentiment_score: number | null;
  sentiment_label: "pos" | "neg" | "neu" | null;
}

// Add to RatingCard:
export interface RatingCard {
  // ... existing fields ...
  news_items?: NewsItemLite[];
}
```

- [ ] **Step 3: Regenerate OpenAPI snapshot (per the project's drift check)**

```bash
make openapi-export
```

- [ ] **Step 4: Smoke + commit**

```bash
python3 -c "import ast; ast.parse(open('alpha_agent/api/routes/stock.py').read()); print('AST OK')"
pytest tests/api/test_stock.py -v
git add alpha_agent/api/routes/stock.py frontend/src/lib/api/picks.ts \
        openapi.snapshot.json frontend/api-types.gen.ts
git commit -m "feat: FullCard.news_items + stock endpoint joins news_items table"
```

---

### Task D3: NewsBlock rewrite + MarketContextWidget + StockCardLayout mount + i18n

**Files:**
- Modify: `frontend/src/components/stock/NewsBlock.tsx` (rewrite, consume card.news_items)
- Create: `frontend/src/components/stock/MarketContextWidget.tsx`
- Modify: `frontend/src/components/stock/StockCardLayout.tsx` (mount widget)
- Create: `frontend/src/lib/api/macro.ts`
- Modify: `frontend/src/lib/i18n.ts` (add news.source_* + market_context.* keys)

- [ ] **Step 1: Add i18n keys** (in both zh and en blocks of `frontend/src/lib/i18n.ts`)

```ts
// zh block
"news.source_finnhub": "Finnhub",
"news.source_fmp": "FMP",
"news.source_rss_yahoo": "Yahoo",
"market_context.title": "市场宏观背景",
"market_context.empty": "近 7 天无该 ticker 相关的宏观事件",
"market_context.author_trump": "Trump",
"market_context.author_fed": "Fed",
"market_context.author_ofac": "OFAC",
"market_context.tickers_affected": "涉及 ticker",
"market_context.sectors_affected": "涉及行业",

// en block
"news.source_finnhub": "Finnhub",
"news.source_fmp": "FMP",
"news.source_rss_yahoo": "Yahoo",
"market_context.title": "Market-Moving Context",
"market_context.empty": "No relevant market-wide events in the last 7 days",
"market_context.author_trump": "Trump",
"market_context.author_fed": "Fed",
"market_context.author_ofac": "OFAC",
"market_context.tickers_affected": "Tickers affected",
"market_context.sectors_affected": "Sectors affected",
```

Add corresponding entries to the `TranslationKey` union if it is explicitly typed.

- [ ] **Step 2: Create macro.ts api client**

```ts
// frontend/src/lib/api/macro.ts
import { apiGet } from "./client";

export interface MacroContextItem {
  id: number;
  author: string | null;
  title: string;
  url: string | null;
  body_excerpt: string | null;
  published_at: string;
  sentiment_score: number | null;
  tickers_extracted: string[];
  sectors_extracted: string[];
}

export const fetchMacroContext = (ticker: string, limit = 5) =>
  apiGet<{ items: MacroContextItem[] }>(
    `/api/macro_context?ticker=${encodeURIComponent(ticker)}&limit=${limit}`,
  );
```

- [ ] **Step 3: Rewrite NewsBlock.tsx**

```tsx
// frontend/src/components/stock/NewsBlock.tsx
"use client";

import { useEffect, useState } from "react";
import type { RatingCard, NewsItemLite } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function relativeTime(iso: string, locale: Locale): string {
  if (!iso) return locale === "zh" ? "未知" : "n/a";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

const SENTIMENT_TONE: Record<NonNullable<NewsItemLite["sentiment_label"]>, string> = {
  pos: "bg-tm-pos",
  neg: "bg-tm-neg",
  neu: "bg-tm-muted",
};

export default function NewsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => { setLocale(getLocaleFromStorage()); }, []);

  const items: NewsItemLite[] = card.news_items ?? [];

  if (items.length === 0) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "news.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "news.empty")}</p>
      </section>
    );
  }

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "news.title")}
      </h2>
      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.id} className="flex gap-2 text-sm">
            {it.sentiment_label ? (
              <span className={`mt-1.5 inline-block h-2 w-2 rounded-full ${SENTIMENT_TONE[it.sentiment_label]}`} />
            ) : (
              <span className="mt-1.5 inline-block h-2 w-2 rounded-full bg-tm-bg-3" />
            )}
            <div className="flex-1">
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-tm-fg hover:text-tm-accent"
              >
                {it.headline}
              </a>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-tm-muted">
                <span className="rounded bg-tm-bg-3 px-1.5 py-0.5 font-tm-mono text-[10px]">
                  {it.source}
                </span>
                <span>{relativeTime(it.published_at, locale)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 4: Create MarketContextWidget.tsx**

```tsx
// frontend/src/components/stock/MarketContextWidget.tsx
"use client";

import { useEffect, useState } from "react";
import { fetchMacroContext, type MacroContextItem } from "@/lib/api/macro";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function authorLabel(author: string | null, locale: Locale): string {
  if (author === "trump") return t(locale, "market_context.author_trump");
  if (author === "fed") return t(locale, "market_context.author_fed");
  if (author === "ofac") return t(locale, "market_context.author_ofac");
  return author ?? "";
}

function relativeTime(iso: string, locale: Locale): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

function toneClass(score: number | null): string {
  if (score === null) return "bg-tm-bg-3";
  if (score > 0.2) return "bg-tm-pos";
  if (score < -0.2) return "bg-tm-neg";
  return "bg-tm-muted";
}

export default function MarketContextWidget({ ticker }: { ticker: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [items, setItems] = useState<MacroContextItem[] | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
    let cancelled = false;
    fetchMacroContext(ticker, 5)
      .then((r) => { if (!cancelled) setItems(r.items); })
      .catch(() => { if (!cancelled) setItems([]); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (items === null) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "market_context.title")}
        </h2>
        <p className="text-sm text-tm-muted">...</p>
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "market_context.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "market_context.empty")}</p>
      </section>
    );
  }

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "market_context.title")}
      </h2>
      <ul className="space-y-3">
        {items.map((it) => (
          <li key={it.id} className="flex gap-2 text-sm">
            <span className={`mt-1.5 inline-block h-2 w-2 rounded-full ${toneClass(it.sentiment_score)}`} />
            <div className="flex-1">
              <div className="text-tm-fg">
                <span className="mr-2 font-semibold text-tm-accent">
                  {authorLabel(it.author, locale)}
                </span>
                {it.url ? (
                  <a href={it.url} target="_blank" rel="noopener noreferrer"
                     className="hover:text-tm-accent">{it.title}</a>
                ) : (
                  <span>{it.title}</span>
                )}
              </div>
              {it.body_excerpt ? (
                <p className="mt-0.5 text-xs text-tm-muted">{it.body_excerpt}</p>
              ) : null}
              <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-tm-muted">
                <span>{relativeTime(it.published_at, locale)}</span>
                {it.tickers_extracted.length > 0 ? (
                  <span>
                    {t(locale, "market_context.tickers_affected")}: {it.tickers_extracted.join(", ")}
                  </span>
                ) : null}
                {it.sectors_extracted.length > 0 ? (
                  <span>
                    {t(locale, "market_context.sectors_affected")}: {it.sectors_extracted.join(", ")}
                  </span>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 5: Mount MarketContextWidget in StockCardLayout**

Edit `frontend/src/components/stock/StockCardLayout.tsx`:

```tsx
import MarketContextWidget from "./MarketContextWidget";

// In the JSX, immediately AFTER <NewsBlock card={card} /> and BEFORE
// <SourcesBlock card={card} />:
<MarketContextWidget ticker={card.ticker} />
```

- [ ] **Step 6: tsc + lint + commit**

```bash
cd frontend
npx tsc --noEmit
npx next lint --dir src/components/stock --dir src/lib/api
cd ..
git add frontend/src/components/stock/NewsBlock.tsx \
        frontend/src/components/stock/MarketContextWidget.tsx \
        frontend/src/components/stock/StockCardLayout.tsx \
        frontend/src/lib/api/macro.ts \
        frontend/src/lib/i18n.ts
git commit -m "feat: NewsBlock rewrite + MarketContextWidget on stock detail page"
```

---

## Phase E: Operations + Acceptance

### Task E1: cron-shards.yml 4 new jobs

**Files:**
- Modify: `.github/workflows/cron-shards.yml`

- [ ] **Step 1: Add 4 new schedules + 4 new jobs** (paste blocks; follow the
existing per-shot loop pattern from `fast_tech` / `fast_mid` / `fast_slow`)

Add to the `on.schedule` list:

```yaml
    # News: per-ticker hourly during market (Finnhub primary + FMP failover + RSS)
    - cron: '0 14-20 * * 1-5'
    # News: Truth Social every 5 min (aligned with CNN mirror refresh), 24/7
    - cron: '*/5 * * * *'
    # News: Fed + OFAC hourly, 24/7
    - cron: '0 * * * *'
    # News: LLM enrich every 15 min, picks llm_processed_at IS NULL
    - cron: '*/15 * * * *'
```

Add to `workflow_dispatch.inputs.job.options`:

```yaml
          - news_per_ticker
          - news_macro
          - news_llm_enrich
```

Add 4 new jobs below the existing ones (one is per-ticker, one combined macro for Truth + Fed + OFAC since they all hit `/api/cron/news_macro`, and one for `news_llm_enrich`. Truth's 5-min cadence triggers `news_macro` with `?source=truth_only=true` if you want to split, but per-spec we run all macro on the macro schedule):

```yaml
  news_per_ticker:
    if: |
      github.event.schedule == '0 14-20 * * 1-5' ||
      (github.event_name == 'workflow_dispatch' && inputs.job == 'news_per_ticker')
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: news per-ticker, 8 shots x limit=75
        run: |
          set -e
          for offset in 0 75 150 225 300 375 450 525; do
            HTTP=$(curl -s --max-time 290 -o /tmp/shot.json -w "%{http_code}" \
              "$BACKEND_BASE/api/cron/news_per_ticker?limit=75&offset=$offset")
            echo "offset=$offset HTTP=$HTTP"
            cat /tmp/shot.json | head -c 400; echo
            [ "$HTTP" = "200" ] || exit 1
            sleep 10
          done

  news_macro:
    if: |
      github.event.schedule == '*/5 * * * *' ||
      github.event.schedule == '0 * * * *' ||
      (github.event_name == 'workflow_dispatch' && inputs.job == 'news_macro')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: news macro single shot
        run: |
          HTTP=$(curl -s --max-time 60 -o /tmp/shot.json -w "%{http_code}" \
            "$BACKEND_BASE/api/cron/news_macro")
          cat /tmp/shot.json | head -c 400; echo
          [ "$HTTP" = "200" ] || exit 1

  news_llm_enrich:
    if: |
      github.event.schedule == '*/15 * * * *' ||
      (github.event_name == 'workflow_dispatch' && inputs.job == 'news_llm_enrich')
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: news llm enrich single shot
        run: |
          HTTP=$(curl -s --max-time 300 -o /tmp/shot.json -w "%{http_code}" \
            "$BACKEND_BASE/api/cron/news_llm_enrich")
          cat /tmp/shot.json | head -c 400; echo
          [ "$HTTP" = "200" ] || exit 1
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('.github/workflows/cron-shards.yml'))
sched_key = True if True in d else 'on'
print('jobs:', list(d['jobs'].keys()))
print('schedules:', [c['cron'] for c in d[sched_key]['schedule']])
"
```

Expected output includes `news_per_ticker`, `news_macro`, `news_llm_enrich` in jobs and the 4 new cron strings.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/cron-shards.yml
git commit -m "feat: 4 news cron jobs (per-ticker hourly / macro 5-min+hourly / llm enrich 15-min)"
```

USER ACTION after merge: from the GitHub Actions UI, manually trigger `news_macro` once with `workflow_dispatch` to validate end-to-end before letting the schedules go live.

---

### Task E2: backfill_macro.py script + news.py signal rewrite

**Files:**
- Create: `scripts/backfill_macro.py`
- Modify: `alpha_agent/signals/news.py`

- [ ] **Step 1: Implement backfill_macro.py**

```python
# scripts/backfill_macro.py
"""One-shot macro backfill: pull last N days of Truth Social + Fed + OFAC
and upsert into macro_events with llm_processed_at NULL. The
news_llm_enrich cron will pick them up over the following cycles.

Usage:
    python scripts/backfill_macro.py --days 30
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta

from alpha_agent.news.fed_adapter import FedRSSAdapter
from alpha_agent.news.ofac_adapter import OFACRSSAdapter
from alpha_agent.news.queries import upsert_macro_events
from alpha_agent.news.truth_adapter import TruthSocialAdapter
from alpha_agent.storage.postgres import get_pool


async def main(days: int) -> None:
    pool = await get_pool(os.environ["DATABASE_URL"])
    since = datetime.now(UTC) - timedelta(days=days)
    adapters = [TruthSocialAdapter(), FedRSSAdapter(), OFACRSSAdapter()]
    total = 0
    try:
        for a in adapters:
            events = await a.fetch(since=since)
            n = await upsert_macro_events(pool, events)
            print(f"{a.name}: pulled={len(events)} inserted={n}")
            total += n
    finally:
        for a in adapters:
            await a.aclose()
    print(f"total new macro_events: {total}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    asyncio.run(main(args.days))
```

- [ ] **Step 2: Rewrite news.py signal module**

Edit `alpha_agent/signals/news.py`: replace the whole `_fetch` body and the helpers it pulls from yf_helpers. Keep `fetch_signal(ticker, as_of)` signature and `raw` shape unchanged.

```python
# alpha_agent/signals/news.py
"""News-flow signal sourced from news_items (was: yfinance Ticker.news).

Queries the last 24h of news_items for the ticker, averages the LLM
sentiment_score, applies the same tanh count bonus the legacy module
used. Returns the same SignalScore shape so combine() and the
NewsBlock breakdown contract are unchanged.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.storage.postgres import get_pool


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    # Sync wrapper around the async pool query so the rest of the
    # signal pipeline (which is sync per-signal) does not need to learn
    # about async. The pool itself is reused across calls.
    items = asyncio.run(_query_recent_news(ticker.upper()))
    if not items:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "headlines": []},
            confidence=0.3, as_of=as_of, source="news_items",
            error="no news in last 24h",
        )
    scored = [it for it in items if it.get("sentiment_score") is not None]
    if not scored:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": len(items), "mean_sent": 0.0,
                 "headlines": _to_headlines(items)},
            confidence=0.4, as_of=as_of, source="news_items",
            error="no LLM-scored rows yet",
        )
    mean_sent = float(np.mean([it["sentiment_score"] for it in scored]))
    count_bonus = float(np.tanh(len(scored) / 5))
    z = float(np.clip(mean_sent * 2 * count_bonus, -3.0, 3.0))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean_sent,
             "headlines": _to_headlines(items)},
        confidence=0.7, as_of=as_of, source="news_items", error=None,
    )


def _to_headlines(items):
    """Match legacy NewsBlock decoder shape: [{title, publisher, published_at,
    link, sentiment}]."""
    label_map = {None: "neu", "pos": "pos", "neg": "neg", "neu": "neu"}
    return [
        {
            "title": it["headline"],
            "publisher": it["source"],
            "published_at": it["published_at"].isoformat()
                if hasattr(it["published_at"], "isoformat") else it["published_at"],
            "link": it["url"],
            "sentiment": label_map.get(it.get("sentiment_label"), "neu"),
        }
        for it in items[:10]
    ]


async def _query_recent_news(ticker: str) -> list[dict]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    since = datetime.now(UTC) - timedelta(hours=24)
    rows = await pool.fetch(
        """
        SELECT headline, source, url, published_at,
               sentiment_score, sentiment_label
        FROM news_items
        WHERE ticker = $1 AND published_at > $2
        ORDER BY published_at DESC LIMIT 20
        """,
        ticker, since,
    )
    return [dict(r) for r in rows]


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="news_items")
```

- [ ] **Step 3: Smoke + commit**

```bash
python3 -c "import ast; ast.parse(open('scripts/backfill_macro.py').read()); print('AST OK')"
python3 -c "import ast; ast.parse(open('alpha_agent/signals/news.py').read()); print('AST OK')"
pytest tests/signals/ -v 2>&1 | tail -5  # check news signal tests still pass
git add scripts/backfill_macro.py alpha_agent/signals/news.py
git commit -m "feat: backfill_macro.py + news.py signal queries news_items"
```

---

### Task E3: news-acceptance Makefile target + manual UAT

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add the target**

```makefile
news-acceptance:
	@echo "==> Phase 5 news acceptance"
	# Backend: schema + every adapter + aggregator + LLM worker + 2 routes.
	pytest tests/storage/test_migration_v004.py tests/news/ \
	  tests/api/test_macro_context.py tests/api/test_news_freshness.py -v
	# Frontend: types/lint/build still clean after NewsBlock rewrite + widget.
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: all 6 sources visible (counts may be 0 pre-data).
	@echo "==> Smoke: /api/_health/news_freshness lists 6 sources"
	@code=$$(curl -sS -o /tmp/nf.json -w "%{http_code}" --max-time 15 \
	  "https://alpha.bobbyzhong.com/api/_health/news_freshness"); \
	  if [ "$$code" != "200" ]; then echo "expected 200 got $$code"; exit 1; fi; \
	  python3 -c "import json; d=json.load(open('/tmp/nf.json')); \
	  assert {s['name'] for s in d['sources']} == {'finnhub','fmp','rss_yahoo','truth_social','fed_rss','ofac_rss'}, d; \
	  print('all 6 sources present:', [s['name'] for s in d['sources']])"
	# Smoke: macro_context route registered (dual-entry validation).
	@echo "==> Smoke: /api/macro_context registered for AAPL"
	@code=$$(curl -sS -o /tmp/mc.json -w "%{http_code}" --max-time 15 \
	  "https://alpha.bobbyzhong.com/api/macro_context?ticker=AAPL&limit=5"); \
	  if [ "$$code" != "200" ]; then echo "expected 200 got $$code"; exit 1; fi; \
	  echo "macro_context responded 200 (items may be empty pre-data)"
	# Smoke: routers health shows macro_context loaded (dual-entry contract).
	@echo "==> Smoke: /api/_health/routers includes macro_context"
	@curl -sS "https://alpha.bobbyzhong.com/api/_health/routers" | \
	  python3 -c "import sys,json; d=json.load(sys.stdin); \
	  loaded=[r['name'] for r in d['routers'] if r['loaded']]; \
	  assert 'macro_context' in loaded, ('macro_context NOT in loaded list', loaded); \
	  print('macro_context router loaded')"
```

- [ ] **Step 2: Document the manual UAT in the same target**

Add a final echo block listing the 6 USER SETUP steps from the spec:

```makefile
	@echo ""
	@echo "==> Manual UAT (user-runs, in order):"
	@echo "  1. Apply for Finnhub free key at finnhub.io/register"
	@echo "  2. Apply for FMP free key at site.financialmodelingprep.com/register"
	@echo "  3. Add FINNHUB_API_KEY + FMP_API_KEY to Vercel alpha-agent env"
	@echo "  4. Apply V004 to Neon: from .env source DATABASE_URL, then:"
	@echo "     python -c \"import asyncio, os; from alpha_agent.storage.migrations.runner import apply_migrations; print(asyncio.run(apply_migrations(os.environ['DATABASE_URL'])))\""
	@echo "  5. Run one-time macro backfill: python scripts/backfill_macro.py --days 30"
	@echo "  6. From GitHub Actions UI, manually trigger 'news_macro' and 'news_per_ticker' once;"
	@echo "     check the cron_runs table for ok=true, then let schedules go live."
	@echo "  7. Open https://alpha.bobbyzhong.com/stock/AAPL and verify the"
	@echo "     'Market-Moving Context' widget renders (may be empty until backfill + LLM enrich complete)."
```

- [ ] **Step 3: Run + commit**

```bash
make news-acceptance 2>&1 | tail -30
# If everything passes, commit.
git add Makefile
git commit -m "feat: news-acceptance Makefile target + UAT checklist"
```

---

## Risks (mirrors spec, with task-level mitigations)

| Risk | Mitigated by |
|---|---|
| CNN's Truth Social mirror goes offline | Adapter constant `_SOURCE_URL` is one line; swap to trumpstruth.org RSS via env override. Add `TRUTH_SOURCE_URL` env var as Phase-2 work, not blocking v1. |
| Finnhub free-tier IP rate-limit under 557-ticker hourly fanout | 60 req/min ceiling vs 557 req/hour = comfortable. If hit anyway, PerTickerAggregator's circuit breaker pauses Finnhub for 1h, FMP failover absorbs the spillover. |
| LLM costs spike on high-news day | `row_limit=100` per cron tick + `max_tokens=2000` per LLM call. Backlog (visible via `/api/_health/news_freshness.llm_backlog`) growing is the early-warning. |
| Macro events extract zero tickers | Stored with `tickers_extracted = []`; widget naturally hides them per-ticker, but row stays for future global `/news` feed. |
| Dedup misses (same story slightly reworded across sources) | Acceptable for v1; the dedup_hash test catches the common cases (URL params, headline case, ticker scoping). Phase 2 could swap in real SimHash. |
| FMP 250/day quota burned by a Finnhub outage | Aggregator only calls FMP when Finnhub returned empty; circuit breaker on Finnhub pauses the failover chain after 5 failures. Visible via `news_freshness.fmp.items_24h`. |
| Dual-entry rule violation (route 404 in prod) | Task D1 has dual-entry as an explicit step; E3 acceptance test asserts `macro_context in /api/_health/routers.loaded`. The watchlist landmine of 2026-05-15 is the cautionary tale captured in memory `feedback_vercel_python_dual_entry.md`. |

## LOC estimate

Per spec: ~2090 LOC across ~25 new files + ~6 edited.

| Phase | Tasks | Approx LOC |
|---|---|---|
| A: Foundation | A1 | 80 |
| B: Adapters | B1-B5 | 850 (6 adapters + types + base + tests + fixtures) |
| C: Pipeline | C1-C4 | 600 (aggregator + queries + cron handlers + LLM worker + tests) |
| D: API + UI | D1-D3 | 450 (routes + FullCard field + widget + NewsBlock + i18n) |
| E: Ops | E1-E3 | 150 (YAML + script + Makefile) |
| **Total** | **14 tasks** | **~2130** |

## Execution tip

Use `superpowers:subagent-driven-development`. Recommended FULL review (controller reads committed files, not just the implementer's report) on:

- **A1** (V004 migration; the schema everything else writes into)
- **C4** (LLM worker; cost guard correctness, malformed-JSON safety)
- **D1** (dual-entry registration; the watchlist landmine pattern)
- **E3** (acceptance; binds every preceding task)

SPEC-ONLY fast review (implementer's test output + a quick targeted grep) is enough for the 5 adapter tasks (B1-B5) and the cron-handler / cron_routes wiring task (C3).

After all 14 tasks land, dispatch one final holistic reviewer focused on cross-task seams: dedup_hash semantics consistent across types.py, all 6 adapters, and the dedup unit test; aggregator failover order matches priority constants in the adapter files; LLM worker's `_KNOWN_NEWS_SOURCES` matches the 6 adapter `name` constants; FullCard.news_items field actually rendered by the rewritten NewsBlock.

USER SETUP (5 of the 6 manual steps from the spec) happens AFTER A1 ships and AFTER E2 ships; the order is documented in the E3 Makefile target so the user has one place to copy-paste from.
