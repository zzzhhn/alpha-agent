# Alpha-Agent v4 · M4b · Alerts Feed + Rich BYOK LLM Brief · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dormant `alert_queue` table into a user-visible per-ticker timeline on `/alerts`, and ship the Rich brief — a user-paid-for, BYOK LLM-streamed bull/bear case on `/stock/[ticker]` — closing out Phase 1 §3.4 (Lean vs Rich) by giving users a real Rich mode.

**Architecture:** Two independent sub-features sharing the same backend + frontend boundaries used by M4a. **Alerts:** new read-only Postgres endpoint reading `alert_queue` directly, frontend timeline component replacing the current cron-history view. **Rich brief:** new SSE streaming endpoint that packs the rating-card breakdown into a system prompt, sends it to the user's chosen LLM via the existing LiteLLM client, and streams normalized JSON deltas back to the frontend. BYOK credentials never touch backend storage — they ride X-LLM-* request headers and the response body never echoes them. The frontend uses `fetch` + `ReadableStream` (not EventSource, which can't carry custom headers) so the BYOK key stays in the request header, not the URL.

**Tech Stack:** Python 3.12 + FastAPI `StreamingResponse` for SSE, LiteLLM (already in deps) for unified OpenAI/Anthropic/Kimi/Ollama streaming, asyncpg for Postgres. Frontend Next.js 14 App Router, TypeScript strict, Tailwind `tm-*` theme tokens, lucide-react icons (no emoji), native browser `fetch` + `TextDecoder` for SSE consumption.

**Spec reference:** `docs/superpowers/specs/2026-05-10-alpha-pivot-phase1-design.md` §3.4 (Lean vs Rich), §4.3 (timing — alerts fire from fast cron).

**Predecessor handoff (M4a F1 → M4b):**
- `alert_queue` table is already populated by `fast_intraday` cron (M2/M4a). Rows exist for every ticker with a rating change.
- `factor.raw.fundamentals`, `news.raw.headlines`, `earnings.raw.next_date` are populated (M4a). Use them as LLM prompt context.
- Frontend BYOK localStorage scaffold (`lib/byok.ts`) is M3 work; the Rich brief is its first real consumer.

---

## Scope

| In M4b | Out of scope |
|--------|--------------|
| `GET /api/alerts/recent?ticker=X&limit=20` — read alert_queue, return list | Playwright E2E test suite (defer to post-M4b) |
| `/alerts` page rewrite: per-ticker timeline + optional `?ticker=` query filter | Real LLM-backed news sentiment (M4a keyword rule suffices) |
| `POST /api/brief/{ticker}/stream` — SSE-streamed bull/bear/summary via LiteLLM | Multi-user auth / persisted watchlist (Phase 4) |
| `RichThesis` client component with "Generate" button + streaming render | Anthropic SDK as a direct dep (LiteLLM normalizes already) |
| Frontend fetch-stream client (`lib/api/streamBrief.ts`) handling POST + ReadableStream | yfinance "Earnings Average" → eps_estimate mapping (M4a tail backlog) |
| `make m4b-acceptance` (pytest + frontend build + curl smoke) | Cost-tracking dashboard for BYOK usage (later milestone) |

---

## File Structure

**New files:**

```
alpha_agent/api/routes/
└── alerts.py                                # A1 — GET /api/alerts/recent

alpha_agent/llm/
└── brief_streamer.py                        # C1 — LiteLLM streaming wrapper

tests/api/
├── test_alerts_recent.py                    # A1
└── test_brief_stream.py                     # C1

frontend/src/
├── lib/
│   └── api/
│       ├── alertsFeed.ts                    # B1a — typed client for /alerts/recent
│       └── streamBrief.ts                   # E1a — fetch-stream reader for SSE
├── components/
│   ├── alerts/
│   │   └── AlertTimeline.tsx                # B1b — per-ticker timeline
│   └── stock/
│       └── RichThesis.tsx                   # E1b — BYOK Rich brief consumer
```

**Modified files:**

```
alpha_agent/api/routes/
└── brief.py                                 # C1 — append /stream route to existing router

api/index.py                                 # A1 — register alerts_router

frontend/src/
├── app/(dashboard)/
│   ├── alerts/page.tsx                      # B1c — rewrite to use AlertTimeline
│   └── settings/page.tsx                    # D1 — surface "Rich brief available" hint when BYOK set
├── components/stock/
│   └── StockCardLayout.tsx                  # E2 — wire RichThesis below LeanThesis
├── lib/
│   └── i18n.ts                              # B1c + E1b + E2 — new zh/en keys
└── ...

Makefile                                     # F1 — m4b-acceptance target
```

Backend net change: +260 LOC (alerts route 60 + brief_streamer 110 + brief.py /stream route 50 + tests 110 + index register 10).
Frontend net change: +500 LOC (alertsFeed.ts 30 + streamBrief.ts 90 + AlertTimeline 110 + RichThesis 180 + alerts page rewrite 60 + StockCardLayout edit 5 + i18n 30 + settings nudge 15).

---

## Phase Order

```
Tier 1 — backend parallel-safe:  A1 (alerts route)  ||  C1 (brief SSE)
Tier 2 — frontend parallel-safe: B1 (alerts page)   ||  D1 (settings nudge)  ||  E1 (RichThesis component)
Tier 3 — integration:            E2 (wire RichThesis into StockCardLayout)
Tier 4 — acceptance:             F1 (m4b-acceptance + handoff)
```

Per subagent-driven-development rule "never parallel-dispatch implementers": tasks execute strictly sequentially in this plan: A1 → C1 → B1a → B1b → B1c → D1 → E1a → E1b → E2 → F1. Total 10 tasks.

---

## Phase A — Backend alerts feed

### Task A1: GET /api/alerts/recent

**Why:** `alert_queue` table already has rows from `fast_intraday` cron writes. Frontend has no way to read them. This route exposes the latest N rows, optionally filtered by ticker, sorted newest-first.

**Files:**
- Create: `alpha_agent/api/routes/alerts.py`
- Create: `tests/api/test_alerts_recent.py`
- Modify: `api/index.py` (register router)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_alerts_recent.py` with EXACTLY:

```python
# tests/api/test_alerts_recent.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _fake_row(ticker, type_, payload, dedup_bucket, created_at_iso):
    """Mirrors asyncpg.Record row shape via dict subscript access."""
    return {
        "id": 42,
        "ticker": ticker,
        "type": type_,
        "payload": payload,
        "dedup_bucket": dedup_bucket,
        "created_at": __import__("datetime").datetime.fromisoformat(created_at_iso),
    }


def test_alerts_recent_returns_latest_n(client, monkeypatch):
    rows = [
        _fake_row("AAPL", "rating_change", '{"from":"HOLD","to":"OW"}',
                  1715000000, "2026-05-14T10:00:00+00:00"),
        _fake_row("MSFT", "score_spike", '{"delta":0.45}',
                  1715000100, "2026-05-14T09:55:00+00:00"),
    ]
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert len(body["alerts"]) == 2
    assert body["alerts"][0]["ticker"] == "AAPL"
    assert body["alerts"][0]["type"] == "rating_change"
    assert body["alerts"][0]["payload"] == {"from": "HOLD", "to": "OW"}
    assert body["alerts"][0]["created_at"].startswith("2026-05-14T10:00:00")
    # SQL was called with limit but no ticker filter
    call_args = pool.fetch.call_args
    assert call_args.args[-1] == 20
    assert "WHERE ticker" not in call_args.args[0]


def test_alerts_recent_ticker_filter(client, monkeypatch):
    rows = [_fake_row("AAPL", "rating_change", '{}', 1, "2026-05-14T10:00:00+00:00")]
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent?ticker=AAPL&limit=5")
    assert r.status_code == 200
    assert len(r.json()["alerts"]) == 1
    call_args = pool.fetch.call_args
    assert "WHERE ticker" in call_args.args[0]
    assert call_args.args[1] == "AAPL"


def test_alerts_recent_empty_returns_empty_list(client, monkeypatch):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "alpha_agent.api.routes.alerts.get_db_pool",
        AsyncMock(return_value=pool),
    )
    r = client.get("/api/alerts/recent")
    assert r.status_code == 200
    assert r.json()["alerts"] == []


def test_alerts_recent_invalid_limit_rejected(client):
    r = client.get("/api/alerts/recent?limit=999")  # cap is 100
    assert r.status_code == 422
```

- [ ] **Step 2: Run test (expect failure)**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/api/test_alerts_recent.py -v
```

Expected: FAIL — module `alpha_agent.api.routes.alerts` doesn't exist; HTTP 404 on every test.

- [ ] **Step 3: Create alerts.py**

Create `alpha_agent/api/routes/alerts.py`:

```python
"""GET /api/alerts/recent — list latest alert_queue rows.

alert_queue is populated by the fast_intraday cron whenever a ticker's
rating or composite crosses a notable threshold. M2 wrote the rows; M4b
exposes them for the frontend timeline. Spec §4.3.

Always returns 200; an empty list is "no alerts yet", not an error.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class Alert(BaseModel):
    id: int
    ticker: str
    type: str
    payload: dict | list | None
    dedup_bucket: int
    created_at: str


class AlertsResponse(BaseModel):
    alerts: list[Alert]


def _parse_payload(raw):
    """asyncpg JSONB columns come back as already-decoded dict/list when
    the column registration includes JSON codec, but defensively handle
    str (when codec not registered) too."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


@router.get("/recent", response_model=AlertsResponse)
async def alerts_recent(
    ticker: str | None = Query(None, min_length=1, max_length=10),
    limit: int = Query(20, ge=1, le=100),
) -> AlertsResponse:
    """Latest `limit` alerts, newest first. `ticker` optionally narrows
    to a single symbol (uppercased server-side)."""
    pool = await get_db_pool()
    if ticker:
        sql = (
            "SELECT id, ticker, type, payload, dedup_bucket, created_at "
            "FROM alert_queue WHERE ticker = $1 "
            "ORDER BY created_at DESC LIMIT $2"
        )
        rows = await pool.fetch(sql, ticker.upper(), limit)
    else:
        sql = (
            "SELECT id, ticker, type, payload, dedup_bucket, created_at "
            "FROM alert_queue "
            "ORDER BY created_at DESC LIMIT $1"
        )
        rows = await pool.fetch(sql, limit)
    alerts = [
        Alert(
            id=r["id"],
            ticker=r["ticker"],
            type=r["type"],
            payload=_parse_payload(r["payload"]),
            dedup_bucket=r["dedup_bucket"],
            created_at=r["created_at"].isoformat()
            if isinstance(r["created_at"], datetime) else str(r["created_at"]),
        )
        for r in rows
    ]
    return AlertsResponse(alerts=alerts)
```

- [ ] **Step 4: Register router in api/index.py**

Open `api/index.py` and locate the `admin_router` registration block (around line 185). Append AFTER it (before the route definitions like `@app.get("/api/health")`):

```python
try:
    from alpha_agent.api.routes.alerts import router as alerts_router
    app.include_router(alerts_router)
    print(f"✓ alerts routes loaded", file=sys.stderr, flush=True)
except Exception as e:
    import traceback
    msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
    _m2_load_errors["alerts"] = msg
    print(f"✗ alerts routes: {msg}", file=sys.stderr, flush=True)
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/api/test_alerts_recent.py -v
```

Expected: 4/4 pass.

Full API suite no regressions:

```bash
pytest tests/api/ -v 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add alpha_agent/api/routes/alerts.py tests/api/test_alerts_recent.py api/index.py
git commit -m "feat(api): GET /api/alerts/recent (M4b A1)

Exposes the alert_queue table that fast_intraday cron has been writing to
since M2. Optional ?ticker= filter narrows to one symbol. Limit capped at
100 to prevent payload bloat. Always returns 200 with empty list when no
data; never raises 5xx (cron retry storms would amplify any failure mode)."
```

---

## Phase C — Backend Rich brief SSE

### Task C1: POST /api/brief/{ticker}/stream

**Why:** Lean brief (M2 route) only renders top_drivers + top_drags as one-line bullet templates. The user wants prose-form bull/bear cases with cited numbers. Rich brief = the user's own LLM key + the structured breakdown context = streamed bull/bear/summary. The streaming is mandatory; a 5-second blank wait on a 4-paragraph response is unacceptable UX.

**Files:**
- Create: `alpha_agent/llm/brief_streamer.py`
- Modify: `alpha_agent/api/routes/brief.py`
- Create: `tests/api/test_brief_stream.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_brief_stream.py` with EXACTLY:

```python
# tests/api/test_brief_stream.py
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _make_row(ticker="AAPL"):
    return {
        "ticker": ticker,
        "rating": "OW",
        "composite": 1.42,
        "breakdown": json.dumps({
            "breakdown": [
                {"signal": "factor", "z": 1.5,
                 "raw": {"z": 1.5,
                         "fundamentals": {"pe_trailing": 28.5, "market_cap": 3.2e12,
                                          "eps_ttm": 6.42, "beta": 1.21,
                                          "pe_forward": None, "dividend_yield": None,
                                          "profit_margin": None, "debt_to_equity": None}}},
                {"signal": "news", "z": 0.6,
                 "raw": {"n": 2, "mean_sent": 0.5,
                         "headlines": [
                             {"title": "Apple beats earnings", "publisher": "WSJ",
                              "published_at": "2026-05-14T09:00:00Z", "link": "x",
                              "sentiment": "pos"},
                         ]}},
                {"signal": "earnings", "z": 0.4,
                 "raw": {"surprise_pct": 12.0, "days_to_earnings": 5,
                         "next_date": "2026-07-31", "days_until": 78,
                         "eps_estimate": 1.45, "revenue_estimate": 120e9}},
            ],
        }),
        "fetched_at": __import__("datetime").datetime.fromisoformat("2026-05-14T10:00:00+00:00"),
    }


async def _fake_stream():
    """Mimics LiteLLM streaming chunk shape minimally."""
    for token in ["Apple", " is", " trading", " at", " 28.5x", "."]:
        yield token


def test_brief_stream_emits_sse_deltas(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_make_row())
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    # Patch the streamer so the test doesn't need a real LLM key
    async def fake_stream(*args, **kwargs):
        async for tok in _fake_stream():
            yield {"type": "summary", "delta": tok}
        yield {"type": "done"}
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.stream_brief", fake_stream,
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    with client.stream("POST", "/api/brief/AAPL/stream", json=body) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        chunks = b"".join(r.iter_bytes()).decode()
    lines = [ln for ln in chunks.splitlines() if ln.startswith("data: ")]
    parsed = [json.loads(ln[len("data: "):]) for ln in lines]
    assert parsed[0] == {"type": "summary", "delta": "Apple"}
    assert parsed[-1] == {"type": "done"}
    assert any(p.get("delta") == " 28.5x" for p in parsed)


def test_brief_stream_unknown_ticker_404(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    r = client.post("/api/brief/UNKN/stream", json=body)
    assert r.status_code == 404


def test_brief_stream_missing_key_400(client):
    """Body must include api_key. Pydantic rejects missing field."""
    r = client.post("/api/brief/AAPL/stream", json={"provider": "openai"})
    assert r.status_code == 422


def test_brief_stream_invalid_provider_400(client):
    body = {"provider": "ollama2", "api_key": "sk-test"}
    r = client.post("/api/brief/AAPL/stream", json=body)
    assert r.status_code == 422


def test_brief_stream_surfaces_llm_error_in_sse(client, monkeypatch):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_make_row())
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.get_db_pool",
        AsyncMock(return_value=pool),
    )
    async def boom_stream(*args, **kwargs):
        raise RuntimeError("upstream LLM 429 rate limit")
        yield  # makes it a generator
    monkeypatch.setattr(
        "alpha_agent.api.routes.brief.stream_brief", boom_stream,
    )
    body = {"provider": "openai", "api_key": "sk-test"}
    with client.stream("POST", "/api/brief/AAPL/stream", json=body) as r:
        chunks = b"".join(r.iter_bytes()).decode()
    err_lines = [ln for ln in chunks.splitlines() if "error" in ln]
    assert any("rate limit" in ln for ln in err_lines)
    assert any('"type": "error"' in ln or "'type': 'error'" in ln for ln in err_lines)
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest tests/api/test_brief_stream.py -v
```

Expected: all 5 FAIL — `/stream` route doesn't exist; `stream_brief` symbol absent.

- [ ] **Step 3: Create brief_streamer.py**

Create `alpha_agent/llm/brief_streamer.py`:

```python
"""LiteLLM-backed streaming generator for the Rich brief endpoint.

Wraps the existing `litellm.acompletion(stream=True, ...)` interface so the
FastAPI route can `async for` over normalized `{type, delta}` events without
caring which provider (OpenAI / Anthropic / Kimi / Ollama) the user picked.

Key handling: api_key is a request-only parameter. We pass it directly to
LiteLLM and never store, never log, never include in error payloads. The
exception path returns the type name + a sanitized message (no key prefix).
"""
from __future__ import annotations

from typing import AsyncIterator, Literal

import litellm

Provider = Literal["openai", "anthropic", "kimi", "ollama"]

_DEFAULT_MODEL: dict[Provider, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "kimi": "openai/kimi-for-coding",
    "ollama": "ollama/llama3.1",
}
_DEFAULT_BASE: dict[Provider, str | None] = {
    "openai": None,
    "anthropic": None,
    "kimi": "https://api.kimi.com/coding/v1",
    "ollama": "http://localhost:11434",
}

SYSTEM_PROMPT = """You are a sober equity research analyst writing a brief for a retail trader.

You will receive a JSON blob containing the latest signal breakdown for ONE ticker. Your job is to produce three sections in this exact order:

1. **SUMMARY** — one paragraph (3-5 sentences) stating the current rating, the strongest 1-2 drivers, the strongest 1-2 drags, and what specifically the trader should watch next.
2. **BULL** — 3 to 5 bullet points making the case to buy. Each bullet must cite a concrete number from the breakdown (e.g. "P/E trailing 28.5", "news sentiment +0.5 from 2 headlines", "earnings beat 12.0%").
3. **BEAR** — 3 to 5 bullet points making the case to avoid or short, with the same citation discipline.

Strict rules:
- If a field is null or missing in the breakdown, do NOT fabricate it. Say "data thin" or omit the bullet.
- Do NOT recommend specific trades, position sizes, or stops. Stick to thesis quality.
- Do NOT include any prefatory or closing commentary outside the three sections.
- Format each section header as `[SUMMARY]`, `[BULL]`, `[BEAR]` on its own line so the client can split sections deterministically."""


def _build_user_prompt(ticker: str, rating: str, composite: float, breakdown: list[dict]) -> str:
    import json
    return (
        f"Ticker: {ticker}\n"
        f"Rating: {rating}\n"
        f"Composite score: {composite:+.2f}\n\n"
        f"Signal breakdown (JSON):\n{json.dumps(breakdown, default=str, indent=2)}"
    )


async def stream_brief(
    *,
    provider: Provider,
    api_key: str,
    ticker: str,
    rating: str,
    composite: float,
    breakdown: list[dict],
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncIterator[dict]:
    """Async generator yielding {type, delta} dicts.

    Yields sections tagged by header markers in the LLM output: the streamer
    tracks the current section as the LLM emits `[SUMMARY]` / `[BULL]` /
    `[BEAR]` tokens. Final yield is `{type: "done"}`.

    Raises:
        RuntimeError on upstream failure (caller wraps into SSE error event).
    """
    chosen_model = model or _DEFAULT_MODEL[provider]
    chosen_base = base_url or _DEFAULT_BASE[provider]

    kwargs = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": _build_user_prompt(ticker, rating, composite, breakdown)},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
        "stream": True,
        "api_key": api_key,
    }
    if chosen_base:
        kwargs["api_base"] = chosen_base

    current = "summary"  # default until first header marker
    buffer = ""

    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        try:
            tok = chunk.choices[0].delta.content
        except (AttributeError, IndexError, TypeError):
            tok = None
        if not tok:
            continue
        buffer += tok
        # Header markers split sections. We only flush after a complete
        # marker so streaming doesn't render the marker itself.
        for marker, section in (
            ("[SUMMARY]", "summary"),
            ("[BULL]", "bull"),
            ("[BEAR]", "bear"),
        ):
            if marker in buffer:
                # Anything before the marker belongs to the prior section
                pre, _, rest = buffer.partition(marker)
                if pre:
                    yield {"type": current, "delta": pre}
                current = section
                buffer = rest
        # Drain buffer in small chunks so the client renders smoothly.
        if len(buffer) > 12:
            yield {"type": current, "delta": buffer}
            buffer = ""
    if buffer:
        yield {"type": current, "delta": buffer}
    yield {"type": "done"}
```

- [ ] **Step 4: Append /stream route to brief.py**

Open `alpha_agent/api/routes/brief.py`. At the END of the file (after the existing `post_brief` function), append:

```python
import asyncio

from fastapi.responses import StreamingResponse

from alpha_agent.llm.brief_streamer import stream_brief

# `Literal` and `Field` are already imported at the top of brief.py — do
# not add duplicate imports. `BaseModel` is also already imported.


class StreamBriefRequest(BaseModel):
    provider: Literal["openai", "anthropic", "kimi", "ollama"]
    api_key: str = Field(min_length=1, repr=False)
    model: str | None = None
    base_url: str | None = None


def _sse_format(event: dict) -> bytes:
    """Serialize one event as a single SSE `data:` line. Keep newline-
    delimited JSON inside the data field so the client parses
    deterministically."""
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")


@router.post("/{ticker}/stream")
async def post_brief_stream(
    payload: StreamBriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
) -> StreamingResponse:
    """SSE-streaming Rich brief. Client posts with BYOK key in body."""
    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT ticker, rating, composite, breakdown, fetched_at "
        "FROM daily_signals_fast WHERE ticker = $1 "
        "ORDER BY fetched_at DESC LIMIT 1",
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown: list[dict] = json.loads(row["breakdown"]).get("breakdown", [])
    composite = float(row["composite"]) if row["composite"] is not None else 0.0
    rating = row["rating"] or "HOLD"

    async def generator():
        try:
            async for event in stream_brief(
                provider=payload.provider,
                api_key=payload.api_key,
                ticker=ticker,
                rating=rating,
                composite=composite,
                breakdown=breakdown,
                model=payload.model,
                base_url=payload.base_url,
            ):
                yield _sse_format(event)
                # tiny await so the runtime flushes
                await asyncio.sleep(0)
        except Exception as e:
            # Sanitize: never echo the api_key. type(e).__name__ + str(e) is
            # enough for the client to act on (429, auth, etc.).
            yield _sse_format({
                "type": "error",
                "message": f"{type(e).__name__}: {str(e)[:200]}",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # nginx; harmless on Vercel
        },
    )
```

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/api/test_brief_stream.py -v
```

Expected: 5/5 pass.

- [ ] **Step 6: Commit**

```bash
git add alpha_agent/llm/brief_streamer.py alpha_agent/api/routes/brief.py tests/api/test_brief_stream.py
git commit -m "feat(api): POST /api/brief/{ticker}/stream Rich BYOK LLM brief (M4b C1)

LiteLLM-backed SSE streaming endpoint. Body carries provider + api_key
(transient, never stored). Backend packs the breakdown JSON into a
system-prompted user message asking the LLM to emit three sections
([SUMMARY], [BULL], [BEAR]) which the streamer splits into typed events.

Errors surface as {type:'error', message:'<class>: <text>'} inside the
SSE stream so the client doesn't need a separate error channel. api_key
is never logged, never echoed, never included in error messages."
```

---

## Phase B — Frontend alerts page

### Task B1a: alertsFeed.ts client

**Files:**
- Create: `frontend/src/lib/api/alertsFeed.ts`

- [ ] **Step 1: Create the client**

Create `frontend/src/lib/api/alertsFeed.ts`:

```typescript
// frontend/src/lib/api/alertsFeed.ts
//
// Typed client for the M4b /api/alerts/recent endpoint. Distinct file
// from the existing alerts.ts (which only knows cron-run history) so we
// can deprecate that one cleanly after B1c lands.
import { apiGet } from "./client";

export interface AlertRow {
  id: number;
  ticker: string;
  type: string;
  payload: Record<string, unknown> | unknown[] | null;
  dedup_bucket: number;
  created_at: string; // ISO 8601
}

export interface AlertsRecentResponse {
  alerts: AlertRow[];
}

export const fetchAlertsRecent = (opts: { ticker?: string; limit?: number } = {}) => {
  const params = new URLSearchParams();
  if (opts.ticker) params.set("ticker", opts.ticker.toUpperCase());
  if (opts.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return apiGet<AlertsRecentResponse>(
    `/api/alerts/recent${qs ? `?${qs}` : ""}`,
  );
};
```

- [ ] **Step 2: Verify tsc**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
```

Expected: silent.

- [ ] **Step 3: Commit**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
git add frontend/src/lib/api/alertsFeed.ts
git commit -m "feat(alerts): typed client for /api/alerts/recent (M4b B1a)"
```

---

### Task B1b: AlertTimeline component

**Files:**
- Create: `frontend/src/components/alerts/AlertTimeline.tsx`
- Modify: `frontend/src/lib/i18n.ts` (zh + en)

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, locate the `chart.error` key (from M4a E1). Add AFTER it in both zh and en blocks.

zh block additions:
```typescript
    "alerts.title": "提醒",
    "alerts.empty": "暂无提醒",
    "alerts.filter_placeholder": "按 ticker 筛选 (如 AAPL)",
    "alerts.col_time": "时间",
    "alerts.col_ticker": "标的",
    "alerts.col_type": "类型",
    "alerts.col_payload": "详情",
    "alerts.type_rating_change": "评级变化",
    "alerts.type_score_spike": "评分跳变",
```

en block additions:
```typescript
    "alerts.title": "Alerts",
    "alerts.empty": "No alerts yet",
    "alerts.filter_placeholder": "Filter by ticker (e.g. AAPL)",
    "alerts.col_time": "Time",
    "alerts.col_ticker": "Ticker",
    "alerts.col_type": "Type",
    "alerts.col_payload": "Detail",
    "alerts.type_rating_change": "Rating change",
    "alerts.type_score_spike": "Score spike",
```

- [ ] **Step 2: Create AlertTimeline.tsx**

Create `frontend/src/components/alerts/AlertTimeline.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Filter } from "lucide-react";
import { fetchAlertsRecent, type AlertRow } from "@/lib/api/alertsFeed";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function relativeTime(iso: string, locale: Locale): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return locale === "zh" ? "刚刚" : "just now";
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

function fmtPayload(payload: AlertRow["payload"]): string {
  if (payload == null) return "—";
  if (typeof payload === "object" && !Array.isArray(payload)) {
    const entries = Object.entries(payload);
    if (entries.length === 0) return "—";
    return entries.map(([k, v]) => `${k}: ${String(v)}`).join(" · ");
  }
  return JSON.stringify(payload);
}

function typeLabel(t_: string, locale: Locale): string {
  const key = `alerts.type_${t_}` as Parameters<typeof t>[1];
  // Fall back to the raw type when no translation exists.
  const translated = t(locale, key);
  return translated === key ? t_ : translated;
}

export default function AlertTimeline({ ticker }: { ticker?: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [filter, setFilter] = useState<string>(ticker ?? "");
  const [rows, setRows] = useState<AlertRow[] | null>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await fetchAlertsRecent({
        ticker: filter.trim() || undefined,
        limit: 50,
      });
      setRows(r.alerts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Filter aria-hidden className="w-4 h-4 text-tm-muted" strokeWidth={1.75} />
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t(locale, "alerts.filter_placeholder")}
          className="rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 text-sm text-tm-fg w-64"
        />
        <button
          type="button"
          onClick={load}
          className="text-xs text-tm-muted hover:text-tm-accent"
        >
          {locale === "zh" ? "刷新" : "Refresh"}
        </button>
      </div>

      {err ? (
        <div className="text-sm text-tm-neg">Error: {err}</div>
      ) : rows == null ? (
        <div className="text-sm text-tm-muted">{locale === "zh" ? "加载中…" : "Loading…"}</div>
      ) : rows.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-tm-muted">
          <Bell aria-hidden className="w-4 h-4" strokeWidth={1.75} />
          {t(locale, "alerts.empty")}
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-tm-fg-2 border-b border-tm-rule">
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_time")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_ticker")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_type")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_payload")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-tm-rule">
                <td className="px-2 py-1 text-tm-muted whitespace-nowrap">
                  {relativeTime(r.created_at, locale)}
                </td>
                <td className="px-2 py-1">
                  <Link href={`/stock/${r.ticker}`} className="text-tm-fg hover:text-tm-accent font-mono">
                    {r.ticker}
                  </Link>
                </td>
                <td className="px-2 py-1 text-tm-fg-2">{typeLabel(r.type, locale)}</td>
                <td className="px-2 py-1 text-tm-muted font-mono">{fmtPayload(r.payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify tsc + lint**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/alerts/AlertTimeline.tsx frontend/src/lib/i18n.ts
git commit -m "feat(alerts): AlertTimeline component (M4b B1b)

Per-ticker alert timeline replacing M3's cron-run-history view. Filter
input narrows by ticker, ticker cells link to /stock/[ticker]. Payload
rendered as 'k: v · k: v' for dict-shape, JSON.stringify fallback.
i18n keys added zh + en (9 new keys per locale)."
```

---

### Task B1c: /alerts page rewrite

**Files:**
- Modify: `frontend/src/app/(dashboard)/alerts/page.tsx`

- [ ] **Step 1: Replace page.tsx**

Replace `frontend/src/app/(dashboard)/alerts/page.tsx` with EXACTLY:

```tsx
import AlertTimeline from "@/components/alerts/AlertTimeline";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams?: { ticker?: string };
}

export default function AlertsPage({ searchParams }: PageProps) {
  const ticker = searchParams?.ticker?.toUpperCase();

  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="FEED" value="per-ticker timeline" />
        {ticker ? (
          <>
            <TmSubbarSep />
            <TmSubbarKV label="FILTER" value={ticker} />
          </>
        ) : null}
      </TmSubbar>

      <TmPane title="ALERTS" meta="alert_queue (M4b)">
        <AlertTimeline ticker={ticker} />
      </TmPane>
    </TmScreen>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build
```

Expected: all clean.

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/(dashboard)/alerts/page.tsx"
git commit -m "feat(alerts): /alerts page renders AlertTimeline (M4b B1c)

Replaces the M3 cron-run-history landing with the new per-ticker
alert feed. Optional ?ticker= query param pre-fills the filter input.
The old fetchCronHealth path stays in lib/api/alerts.ts for now -
cron health is its own concern surfaced elsewhere (M4a refresh button
on /picks already shows last-refresh timestamps)."
```

---

## Phase D — Settings BYOK nudge

### Task D1: Surface "Rich brief available" hint when BYOK set

**Why:** The /settings page already lets users paste a BYOK key. We don't need to refactor the BYOK store. The only UX gap: a user with a saved key has no signal that the Rich brief is unlocked. A single sentence on the settings page closes that loop.

**Files:**
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, append AFTER the `alerts.*` block from B1b.

zh block:
```typescript
    "settings.byok.rich_brief_unlocked": "Rich brief 已解锁 — /stock 页可生成 LLM 分析",
    "settings.byok.rich_brief_locked": "保存 API key 后可在 /stock 页生成 Rich brief",
```

en block:
```typescript
    "settings.byok.rich_brief_unlocked": "Rich brief unlocked — generate LLM analysis on any /stock page",
    "settings.byok.rich_brief_locked": "Save an API key to enable Rich brief on /stock pages",
```

- [ ] **Step 2: Surface the hint in settings/page.tsx**

Locate the settings page. We need to find a stable insertion point. Run:

```bash
grep -n "PROVIDER_PRESETS\|hasByok\|loadByok" /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend/src/app/\(dashboard\)/settings/page.tsx | head -10
```

Note the line where the BYOK save button or status is rendered. Insert ONE NEW JSX block immediately above the save button (or below the provider chip row) that reads:

```tsx
{/* M4b D1: nudge that Rich brief is now consumable. The actual button */}
{/* lives on /stock/[ticker] — RichThesis component. */}
<div className="text-xs text-tm-muted">
  {hasByok()
    ? t(locale, "settings.byok.rich_brief_unlocked")
    : t(locale, "settings.byok.rich_brief_locked")}
</div>
```

Ensure `hasByok` is imported from `@/lib/byok` and `t`, `locale` are already in scope (they are, per the existing BYOK form).

If you can't find a clean insertion point because the page uses a different state model than expected, REPORT BACK as NEEDS_CONTEXT with a snippet of the surrounding code; do not invent a new section.

- [ ] **Step 3: Verify tsc + lint**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/app/(dashboard)/settings/page.tsx" frontend/src/lib/i18n.ts
git commit -m "feat(settings): nudge that Rich brief is unlocked when BYOK set (M4b D1)

One-line status under the BYOK form so users know the saved key has a
consumer (RichThesis on /stock). i18n added in both locales."
```

---

## Phase E — Frontend RichThesis

### Task E1a: streamBrief.ts fetch-stream client

**Why:** The native browser `EventSource` only does GET requests and can't carry custom headers — yet we need to POST the BYOK key without putting it in the URL. So we use `fetch` + `ReadableStream` reader and parse the `text/event-stream` body manually. This file is the sole reusable helper; the component just consumes its async generator.

**Files:**
- Create: `frontend/src/lib/api/streamBrief.ts`

- [ ] **Step 1: Create the file**

Create `frontend/src/lib/api/streamBrief.ts`:

```typescript
// frontend/src/lib/api/streamBrief.ts
//
// SSE-via-fetch reader. EventSource is GET-only + no headers, so we POST
// + read the ReadableStream + parse 'data: ' lines manually. Returns an
// async generator yielding decoded events; caller `for await`s over it.
import type { LLMProvider } from "@/lib/byok";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "https://alpha-agent.vercel.app";

export type BriefEvent =
  | { type: "summary" | "bull" | "bear"; delta: string }
  | { type: "done" }
  | { type: "error"; message: string };

export interface StreamBriefBody {
  provider: LLMProvider;
  api_key: string;
  model?: string;
  base_url?: string;
}

export async function* streamBrief(
  ticker: string,
  body: StreamBriefBody,
  signal?: AbortSignal,
): AsyncGenerator<BriefEvent, void, void> {
  const r = await fetch(`${API_BASE}/api/brief/${ticker.toUpperCase()}/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!r.ok || !r.body) {
    let msg = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      msg = `${msg}: ${j.detail ?? JSON.stringify(j)}`;
    } catch {
      // body might not be JSON (e.g. 502 from edge)
    }
    yield { type: "error", message: msg };
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE events are separated by blank lines. A complete event ends
      // with "\n\n". Process all complete events in the buffer.
      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        for (const line of event.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice("data: ".length);
          try {
            yield JSON.parse(data) as BriefEvent;
          } catch {
            // Skip malformed event; continue with the next.
          }
        }
      }
    }
    // Flush any trailing event without separator (rare with FastAPI).
    if (buffer.trim().startsWith("data: ")) {
      try {
        yield JSON.parse(buffer.slice("data: ".length).trim()) as BriefEvent;
      } catch {
        /* ignore */
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 2: Verify tsc**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit
```

Expected: silent.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/streamBrief.ts
git commit -m "feat(brief): fetch-stream client for /api/brief/{ticker}/stream (M4b E1a)

Native EventSource can't carry custom headers and forces GET. We POST
+ read ReadableStream + parse 'data: ' lines manually. Caller consumes
via for-await loop; AbortSignal supported for tab navigation."
```

---

### Task E1b: RichThesis component

**Files:**
- Create: `frontend/src/components/stock/RichThesis.tsx`
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, append AFTER `settings.byok.rich_brief_locked` from D1.

zh block:
```typescript
    "rich.title": "Rich Brief (LLM)",
    "rich.generate_button": "生成 Rich brief",
    "rich.regenerate_button": "重新生成",
    "rich.no_key_hint": "需在 /settings 配置 BYOK key",
    "rich.section_summary": "概要",
    "rich.section_bull": "看多理由",
    "rich.section_bear": "看空理由",
    "rich.streaming": "正在生成…",
    "rich.error_label": "失败：",
    "rich.aborted": "已取消",
```

en block:
```typescript
    "rich.title": "Rich Brief (LLM)",
    "rich.generate_button": "Generate Rich brief",
    "rich.regenerate_button": "Regenerate",
    "rich.no_key_hint": "Configure a BYOK key in /settings",
    "rich.section_summary": "Summary",
    "rich.section_bull": "Bull case",
    "rich.section_bear": "Bear case",
    "rich.streaming": "Streaming…",
    "rich.error_label": "Failed: ",
    "rich.aborted": "Aborted",
```

- [ ] **Step 2: Create RichThesis.tsx**

Create `frontend/src/components/stock/RichThesis.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Square, AlertTriangle } from "lucide-react";
import { loadByok, hasByok } from "@/lib/byok";
import { streamBrief, type BriefEvent } from "@/lib/api/streamBrief";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

type Status = "idle" | "streaming" | "done" | "error" | "aborted";

interface Sections {
  summary: string;
  bull: string;
  bear: string;
}

const EMPTY_SECTIONS: Sections = { summary: "", bull: "", bear: "" };

export default function RichThesis({ ticker }: { ticker: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [keyPresent, setKeyPresent] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [sections, setSections] = useState<Sections>(EMPTY_SECTIONS);
  const [errMsg, setErrMsg] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setLocale(getLocaleFromStorage());
    setKeyPresent(hasByok());
  }, []);

  const onGenerate = useCallback(async () => {
    const creds = loadByok();
    if (!creds) {
      setKeyPresent(false);
      return;
    }
    setStatus("streaming");
    setSections(EMPTY_SECTIONS);
    setErrMsg("");
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      for await (const ev of streamBrief(
        ticker,
        {
          provider: creds.provider,
          api_key: creds.apiKey,
          model: creds.model,
          base_url: creds.baseUrl,
        },
        ac.signal,
      )) {
        if (ev.type === "done") {
          setStatus("done");
          break;
        }
        if (ev.type === "error") {
          setErrMsg(ev.message);
          setStatus("error");
          break;
        }
        // Accumulate delta into the current section.
        setSections((prev) => ({
          ...prev,
          [ev.type]: prev[ev.type] + ev.delta,
        }));
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        setStatus("aborted");
      } else {
        setErrMsg(e instanceof Error ? e.message : String(e));
        setStatus("error");
      }
    }
  }, [ticker]);

  const onAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Re-read key presence whenever a storage event fires (multi-tab edit).
  useEffect(() => {
    const handler = () => setKeyPresent(hasByok());
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, []);

  const hasContent =
    sections.summary || sections.bull || sections.bear;

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-tm-fg flex items-center gap-2">
          <Sparkles aria-hidden className="w-4 h-4 text-tm-accent" strokeWidth={1.75} />
          {t(locale, "rich.title")}
        </h2>
        {keyPresent ? (
          <div className="flex items-center gap-2">
            {status === "streaming" ? (
              <button
                type="button"
                onClick={onAbort}
                className="inline-flex items-center gap-1 rounded border border-tm-rule px-2 py-1 text-xs text-tm-fg hover:border-tm-neg"
              >
                <Square aria-hidden className="w-3 h-3" strokeWidth={1.75} />
                Stop
              </button>
            ) : (
              <button
                type="button"
                onClick={onGenerate}
                className="rounded border border-tm-rule bg-tm-bg px-3 py-1 text-xs text-tm-fg hover:border-tm-accent"
              >
                {hasContent
                  ? t(locale, "rich.regenerate_button")
                  : t(locale, "rich.generate_button")}
              </button>
            )}
          </div>
        ) : (
          <Link
            href="/settings"
            className="text-xs text-tm-accent hover:underline"
          >
            {t(locale, "rich.no_key_hint")}
          </Link>
        )}
      </div>

      {status === "streaming" ? (
        <div className="text-xs text-tm-muted">{t(locale, "rich.streaming")}</div>
      ) : null}
      {status === "aborted" ? (
        <div className="text-xs text-tm-warn">{t(locale, "rich.aborted")}</div>
      ) : null}
      {status === "error" ? (
        <div className="text-xs text-tm-neg flex items-start gap-1">
          <AlertTriangle aria-hidden className="w-3 h-3 mt-0.5" strokeWidth={1.75} />
          <span>
            {t(locale, "rich.error_label")}
            {errMsg}
          </span>
        </div>
      ) : null}

      {hasContent ? (
        <div className="space-y-3 text-sm text-tm-fg-2">
          {sections.summary ? (
            <div>
              <div className="text-xs text-tm-muted uppercase tracking-wide mb-1">
                {t(locale, "rich.section_summary")}
              </div>
              <p className="whitespace-pre-wrap">{sections.summary}</p>
            </div>
          ) : null}
          {sections.bull ? (
            <div>
              <div className="text-xs text-tm-pos uppercase tracking-wide mb-1">
                {t(locale, "rich.section_bull")}
              </div>
              <p className="whitespace-pre-wrap">{sections.bull}</p>
            </div>
          ) : null}
          {sections.bear ? (
            <div>
              <div className="text-xs text-tm-neg uppercase tracking-wide mb-1">
                {t(locale, "rich.section_bear")}
              </div>
              <p className="whitespace-pre-wrap">{sections.bear}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 3: Verify tsc + lint**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stock/RichThesis.tsx frontend/src/lib/i18n.ts
git commit -m "feat(stock): RichThesis BYOK LLM client component (M4b E1b)

Reads BYOK key from localStorage, opens fetch-stream to backend
/api/brief/{ticker}/stream on button click. Accumulates summary/bull/
bear deltas into separate sections rendered progressively. Abort
button cancels mid-stream; storage event listener picks up multi-tab
key changes. i18n keys added zh + en (10 new keys per locale)."
```

---

### Task E2: Wire RichThesis into StockCardLayout

**Files:**
- Modify: `frontend/src/components/stock/StockCardLayout.tsx`

- [ ] **Step 1: Add import + JSX**

Open `frontend/src/components/stock/StockCardLayout.tsx`. Add import after the existing `LeanThesis` import:

```tsx
import RichThesis from "./RichThesis";
```

Locate the existing `<LeanThesis card={card} />` line. Insert `<RichThesis ticker={card.ticker} />` IMMEDIATELY AFTER it so the render order is `Lean → Rich → Attribution → Price → ...`.

- [ ] **Step 2: Verify tsc + lint + build**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
npx tsc --noEmit && npx next lint && npx next build
```

Expected: all clean. `next build` MUST succeed because the new component is dynamically reached from /stock/[ticker].

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stock/StockCardLayout.tsx
git commit -m "feat(stock): wire RichThesis below LeanThesis (M4b E2)

LeanThesis remains the always-on fallback; RichThesis sits directly
below it with its own Generate button (BYOK = user pays, no auto-fire).
Render order: Lean -> Rich -> Attribution -> Price -> Fundamentals ->
Catalysts -> News -> Sources."
```

---

## Phase F — Acceptance

### Task F1: m4b-acceptance Makefile + smoke + handoff

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append the new target**

Add to the END of `Makefile` (after `m4a-acceptance`):

```makefile

m4b-acceptance:
	@echo "==> Running M4b acceptance suite"
	# Backend: alerts + brief stream endpoint tests
	pytest tests/api/test_alerts_recent.py tests/api/test_brief_stream.py -v
	# Frontend: deps clean, types clean, lint clean, builds
	cd frontend && npm ci
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: hit the deployed alerts endpoint
	@echo "==> Smoke: /api/alerts/recent?limit=5 (deployed)"
	@curl -sS --max-time 15 "https://alpha.bobbyzhong.com/api/alerts/recent?limit=5" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  alerts={len(d[\"alerts\"])}')" \
	  || (echo 'alerts smoke FAILED' && exit 1)
	# Smoke: confirm /api/brief/AAPL/stream rejects missing key with 422
	@echo "==> Smoke: /api/brief/AAPL/stream rejects malformed body"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  -X POST -H 'content-type: application/json' \
	  -d '{"provider":"openai"}' \
	  "https://alpha.bobbyzhong.com/api/brief/AAPL/stream"); \
	  if [ "$$code" != "422" ]; then echo "expected 422 got $$code"; exit 1; fi
	@echo "M4b acceptance PASS"
```

- [ ] **Step 2: Run pytest portion locally**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/api/test_alerts_recent.py tests/api/test_brief_stream.py -v 2>&1 | tail -10
```

Expected: 9 tests pass (4 alerts + 5 brief stream).

- [ ] **Step 3: Deploy the frontend manually**

Backend auto-deploys on git push. Frontend project has `rootDirectory=None` so does NOT auto-deploy from git — must be CLI-pushed:

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
VTOK=$(python3 -c "import json; print(json.load(open('/Users/a22309/Library/Application Support/com.vercel.cli/auth.json'))['token'])")
vercel --prod --yes --token "$VTOK" --scope team_F2QuyPNaBdqEtaQ1LmBrASKG 2>&1 | grep -E "Production:|Aliased:|readyState|Error" | head -8
```

Expected: Production URL printed, "Aliased: https://alpha.bobbyzhong.com", readyState=READY.

- [ ] **Step 4: Wait for backend deploy to settle (~30s) then run the full Makefile target**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
make m4b-acceptance 2>&1 | tail -15
```

Expected: ends with `M4b acceptance PASS`.

- [ ] **Step 5: Manual UAT (not automatable)**

In a browser:

1. Open `https://alpha.bobbyzhong.com/alerts` — expect the per-ticker timeline (NOT the old cron-history view). If empty, that just means the latest `fast_intraday` cron didn't produce rating changes — open `/alerts?ticker=AAPL` and confirm filter input populates.
2. Open `https://alpha.bobbyzhong.com/settings` — paste a real OpenAI key into the BYOK form, save. Confirm the "Rich brief unlocked" hint appears.
3. Open `https://alpha.bobbyzhong.com/stock/AAPL` — locate the new "Rich Brief (LLM)" section directly below the Lean thesis. Click "Generate Rich brief".
4. Confirm: text streams in token-by-token, splits into Summary / Bull case / Bear case sections, headlines and metrics from the M4a breakdown are cited (e.g. "P/E 36.4", "next earnings 2026-07-30"), no errors in the browser console.
5. Click "Stop" mid-stream — confirm UI shows "Aborted" and no further tokens arrive.
6. Toggle light/dark theme + zh/en locale — confirm RichThesis renders correctly in both.
7. Open `/stock/AAPL` in a fresh incognito window with NO BYOK key — confirm RichThesis shows "Configure a BYOK key in /settings" link instead of the Generate button.

Capture one screenshot each: zh + en + dark + light. Store under `docs/superpowers/screenshots/m4b-*.png`.

- [ ] **Step 6: Commit + handoff note**

```bash
mkdir -p docs/superpowers/screenshots
# Drop captured screenshots here
git add Makefile docs/superpowers/screenshots/
git commit -m "ci(m4b): m4b-acceptance Makefile + UAT screenshots

Encodes pytest (alerts + brief stream) + frontend tsc/lint/build +
two curl smokes (alerts list + malformed-body 422 on /brief/stream).

Acceptance reproducible by 'make m4b-acceptance'. Manual UAT
screenshots document the visual deliverable for the audit trail.

M4b SHIPS. Phase 1 closes with Lean + Rich brief modes both live,
alerts feed exposed, and BYOK pipeline end-to-end functional."
git push origin main
```

---

## Hand-off

**After M4b acceptance + visual approval — Phase 1 is COMPLETE.** The remaining items are post-Phase-1 backlog:

- Playwright E2E covering picks load + ticker drill-down + back + refresh + alerts + settings BYOK + zh/en + dark/light + Rich brief streaming
- yfinance calendar "Earnings Average" → eps_estimate mapping (M4a cosmetic tail)
- Cost-tracking dashboard for BYOK LLM usage (count tokens per provider)
- Phase 2: watchlist persistence + real-time alert push (Telegram / email)
- Phase 3: LLM-backed news sentiment (replaces M4a keyword classifier)
- Phase 4: multi-user auth

**M4b → Phase 2 contract:**

| M4b output | Phase 2 consumer |
|------------|------------------|
| `/api/alerts/recent` | Push dispatcher (Telegram bot) reads same row shape, marks `dispatched=true` |
| `RichThesis` component | Email digest renderer reuses the same prompt + LLM client |
| `streamBrief.ts` fetch-stream pattern | Any future SSE feature (live cron progress, multi-ticker batch brief, etc.) |
| BYOK localStorage scaffold | Phase 4 server-side encrypted key store deprecates this — but only after auth lands |

---

## Risk Matrix

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| LiteLLM streaming chunk shape varies by provider | Medium | The `try/except (AttributeError, IndexError, TypeError)` around `chunk.choices[0].delta.content` lets unknown shapes drop quietly; section headers in the prompt still steer the section split deterministically |
| BYOK key leaks into logs via uncaught exception | Medium-High | `stream_brief` raises only `RuntimeError` and the route's outer try/except prints only `type(e).__name__ + str(e)[:200]` — `str(e)` from LiteLLM never includes the api_key prefix. Test `test_brief_stream_surfaces_llm_error_in_sse` covers this path |
| Vercel SSE response gets buffered by some edge POP | Medium | `Cache-Control: no-store` + `X-Accel-Buffering: no` header set; `await asyncio.sleep(0)` between yields prompts the runtime to flush; if streaming still buffers on a specific deploy, fall back to chunked transfer with explicit `\n\n` separators (already used) |
| `fetch` ReadableStream doesn't deliver partial chunks on Safari | Low | Modern Safari (16+) supports it; if a user reports issue, add a `@microsoft/fetch-event-source` dep as fallback |
| Section header markers `[BULL]` etc. appear in the model's prose (LLM ignores instructions) | Low-Medium | The prompt instructs the model to emit markers on their own lines; the streamer's `partition` only splits on exact match. Worst case: a bullet contains `[BULL]` as text and the streamer triggers a section switch mid-output. The user would see content shuffled but no data loss |
| Frontend `rootDirectory` misconfig means git push doesn't redeploy frontend | High (known) | F1 Step 3 explicitly runs `vercel --prod` from `frontend/`. Same workaround used for M3 + M4a |
| Alert payloads stored as text in JSONB column on some asyncpg connections | Medium | `_parse_payload` handles both already-decoded dict/list AND raw string |
| Empty `alert_queue` table makes /alerts page look broken | Medium | AlertTimeline shows "No alerts yet" with a Bell icon — clearly intentional empty state, not a crash |

---

## Total LOC estimate

- **Backend:** ~260 LOC (alerts route 60 + brief_streamer 110 + brief.py /stream route 50 + tests 110 - shared structure 70 net = ~260)
- **Frontend:** ~500 LOC (alertsFeed 30 + streamBrief 90 + AlertTimeline 110 + RichThesis 180 + alerts page 60 + StockCardLayout edit 5 + i18n 30 + settings nudge 15)
- **Plan total: ~760 LOC of new+modified code across 10 tasks**

---

## Execution Tip

Per `superpowers:subagent-driven-development` constraints, dispatch one implementer at a time. The plan's "Tier 1/2/3" annotations indicate which tasks have no shared file dependencies and could be parallelized in a future relaxation of that constraint — for now they just inform commit ordering.

Sequential execution order: **A1 → C1 → B1a → B1b → B1c → D1 → E1a → E1b → E2 → F1**. Estimated wall time per task: 8-15 min for backend tasks (including spec + quality review), 5-10 min for frontend type-only tasks (A2-like scope), 12-20 min for the chunky tasks (C1 streamer + E1b RichThesis). Total: ~2-3 hours subagent execution + manual UAT.
