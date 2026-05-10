# Alpha-Agent v4 · M2 Cron + API · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the M1 backend foundation (CLI-callable `build_card(ticker, as_of)`) and expose it through Vercel-deployed HTTP endpoints + scheduled cron writes so a deployed preview can serve `GET /api/picks/lean` returning a real list of `RatingCard` objects from Postgres.

**Architecture:** Three Vercel crons populate Postgres on different cadences (slow daily / fast every 15min / alert dispatcher every 5min). Four read endpoints serve already-computed data from Postgres (no synchronous build_card on the request path — sub-500ms p95). Three health endpoints expose cron + signal + DB status independently of business routes (CLAUDE.md 部署地面真相三板斧 compliance).

**Tech Stack:** FastAPI + Vercel Functions/Cron, Pydantic v2 (RatingCard from M1), asyncpg pool from `alpha_agent/storage/postgres.py` M1, openapi-typescript for FE/BE schema sync, pytest-postgresql for integration.

**Spec reference:** `docs/superpowers/specs/2026-05-10-alpha-pivot-phase1-design.md` Sections 4 (data flow), 5.7 (health endpoints), 7.2 (API contract).

**M1 prerequisites (already merged on main at `ac077ea`):** Storage layer, 10 signal modules, fusion engine, RatingCard schema, `build_card()` orchestrator.

---

## Scope

| In M2 | Out of scope (later) |
|-------|----------------------|
| 3 cron handlers (slow / fast / alert dispatcher) | Frontend UI (M3) |
| 4 business API endpoints (lean/stock/brief stub) | Rich BYOK LLM brief (M3) |
| 3 health endpoints | Real news signal API integration (M3 backlog) |
| API contract test (openapi-typescript drift gate) | E2E Playwright (M4) |
| Vercel deploy + 三板斧 acceptance | Real EDGAR Form 4 parsing (M3 backlog) |
| `make m2-acceptance` Makefile target | Multi-tenant auth (Phase 4) |

---

## File Structure

**New files:**

```
api/
├── cron/
│   ├── __init__.py
│   ├── slow_daily.py          # Vercel function: orchestrate slow signals → DB
│   ├── fast_intraday.py       # Vercel function: orchestrate fast signals + alerts
│   └── alert_dispatcher.py    # Vercel function: drain alert_queue
└── (existing index.py untouched aside from router registration)

alpha_agent/
├── api/
│   ├── routes/
│   │   ├── picks.py           # GET /api/picks/lean
│   │   ├── stock.py           # GET /api/stock/{ticker}
│   │   ├── brief.py           # POST /api/brief/{ticker}  (Lean stub for M2)
│   │   └── health.py          # GET /api/_health{,_signals,_cron}
│   └── (existing app.py / dependencies extended for new routers)
├── orchestrator/
│   ├── __init__.py
│   ├── batch_runner.py        # Universe iteration + asyncio.gather batching
│   └── alert_detector.py      # Alert trigger conditions
└── universe.py                # Universe definitions (SP500 list, watchlist source)

tests/
├── api/
│   ├── __init__.py
│   ├── conftest.py            # FastAPI TestClient + applied_db
│   ├── test_picks.py
│   ├── test_stock.py
│   ├── test_brief.py
│   ├── test_health.py
│   └── test_openapi_drift.py  # CI gate
├── orchestrator/
│   ├── test_batch_runner.py
│   └── test_alert_detector.py
└── cron/
    ├── test_slow_daily.py
    ├── test_fast_intraday.py
    └── test_alert_dispatcher.py
```

**Modified files:**

- `vercel.json` — add `crons` array + bump function timeout to 300s
- `alpha_agent/api/app.py` (or wherever routers are wired in) — register 4 new routers
- `Makefile` — add `m2-acceptance` target; `deploy.sh` smoke check
- `pyproject.toml` — add `fastapi[all]>=0.115` if not already in core, `python-multipart` (for FastAPI), `freezegun` (for cron time-travel tests)

---

## Acceptance Criteria

```bash
# 1. All M2 tests pass with ≥85% coverage on new code
pytest tests/api tests/orchestrator tests/cron \
    --cov=alpha_agent.api.routes --cov=alpha_agent.orchestrator \
    --cov-fail-under=85 -m "not slow"

# 2. OpenAPI schema drift check (CI gate)
make openapi-check  # exits 0 if frontend/api-types.gen.ts matches backend

# 3. Deploy preview + 三板斧
vercel --prod=false  # deploy preview
PREVIEW_URL=$(vercel inspect --json | jq -r .url)
curl -fI "$PREVIEW_URL/api/_health" | grep -q "Content-Type: application/json"
curl -s "$PREVIEW_URL/api/openapi.json" | jq -e '.paths | keys | length >= 7'
curl -fs "$PREVIEW_URL/api/picks/lean?limit=5" | jq -e '.picks | length >= 0'

# 4. Cron smoke (manually trigger one)
curl -X POST "$PREVIEW_URL/api/cron/slow_daily" \
    -H "Authorization: Bearer $CRON_SECRET" \
    | jq -e '.ok == true'
```

---

## Phase A · Universe + Orchestrator（Day 11 morning）

### Task 1: `alpha_agent/universe.py` — universe definition

**Files:**
- Create: `alpha_agent/universe.py`
- Create: `tests/test_universe.py`

**Why:** Both slow and fast crons need to know which tickers to process. Single source of truth.

- [ ] **Step 1: Failing test**

```python
# tests/test_universe.py
from alpha_agent.universe import SP500_UNIVERSE, get_watchlist


def test_sp500_universe_is_nonempty_string_list():
    assert isinstance(SP500_UNIVERSE, list)
    assert len(SP500_UNIVERSE) >= 100  # Phase 1 panel has ~99 tickers
    assert all(isinstance(t, str) for t in SP500_UNIVERSE)
    assert all(t.isupper() for t in SP500_UNIVERSE)


def test_get_watchlist_default_returns_top_n():
    wl = get_watchlist(top_n=20)
    assert isinstance(wl, list)
    assert len(wl) <= 20
    assert all(isinstance(t, str) for t in wl)
```

- [ ] **Step 2: Run → expect FAIL**

`pytest tests/test_universe.py -v`

- [ ] **Step 3: Implement**

```python
# alpha_agent/universe.py
"""Universe definitions for cron orchestration.

SP500_UNIVERSE: source of truth for "which tickers does the slow cron iterate".
Bootstrapped from the v3 panel parquet manifest; can be replaced by a Postgres
table later (M3+).

get_watchlist: returns the user's tracked tickers (Phase 1 reads from a static
file; M3+ reads from Postgres user table).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_PANEL_PATH = Path(__file__).parent / "data" / "factor_universe_sp500_v3.parquet"


def _load_sp500() -> list[str]:
    if not _PANEL_PATH.exists():
        # Fallback for environments without the parquet (CI / fresh installs)
        return ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA",
                "BRK.B", "JPM", "JNJ", "V", "WMT", "PG", "MA", "UNH",
                "HD", "DIS", "BAC", "XOM", "PFE"] + [f"T{i:03d}" for i in range(80)]
    df = pd.read_parquet(_PANEL_PATH, columns=["ticker"])
    return sorted(df["ticker"].unique().tolist())


SP500_UNIVERSE: list[str] = _load_sp500()


def get_watchlist(top_n: int = 100) -> list[str]:
    """Stub: returns first top_n from SP500. M3+ reads user-specific list from Postgres."""
    return SP500_UNIVERSE[:top_n]
```

- [ ] **Step 4: Run → expect PASS**

`pytest tests/test_universe.py -v`

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/universe.py tests/test_universe.py
git commit -m "feat(universe): SP500_UNIVERSE + get_watchlist stub for cron orchestration"
```

---

### Task 2: `alpha_agent/orchestrator/batch_runner.py`

**Files:**
- Create: `alpha_agent/orchestrator/__init__.py` (empty)
- Create: `alpha_agent/orchestrator/batch_runner.py`
- Create: `tests/orchestrator/__init__.py` (empty)
- Create: `tests/orchestrator/test_batch_runner.py`

**Why:** Spec §4.1 mandates `asyncio.gather batch_size=20` for 500-ticker iteration to fit Vercel 300s timeout. Pulling out the batch logic keeps cron handlers thin.

- [ ] **Step 1: Failing test**

```python
# tests/orchestrator/test_batch_runner.py
import asyncio
import pytest

from alpha_agent.orchestrator.batch_runner import run_batched

pytestmark = pytest.mark.asyncio


async def test_run_batched_returns_all_results():
    async def square(t):
        await asyncio.sleep(0.001)
        return int(t) ** 2

    results = await run_batched(["1", "2", "3", "4", "5"], square, batch_size=2)
    assert sorted(results.values()) == [1, 4, 9, 16, 25]
    assert set(results.keys()) == {"1", "2", "3", "4", "5"}


async def test_run_batched_isolates_per_ticker_failure():
    async def maybe_fail(t):
        if t == "BAD":
            raise RuntimeError("oops")
        return f"ok:{t}"

    results = await run_batched(["A", "BAD", "C"], maybe_fail, batch_size=2)
    assert results["A"] == "ok:A"
    assert results["C"] == "ok:C"
    assert isinstance(results["BAD"], Exception)
    assert "oops" in str(results["BAD"])


async def test_run_batched_respects_concurrency_cap():
    """At most batch_size coroutines should be live at once."""
    in_flight = 0
    peak = 0

    async def track(t):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.005)
        in_flight -= 1
        return t

    await run_batched([str(i) for i in range(20)], track, batch_size=4)
    assert peak <= 4
```

- [ ] **Step 2-4: Implement**

```python
# alpha_agent/orchestrator/batch_runner.py
"""Bounded-concurrency runner for ticker iteration.

Cron handlers wrap their per-ticker work in a coroutine and pass a list of
tickers + batch_size; we gather with bounded concurrency so a 500-ticker
slow cron takes ~10min instead of either 500min (serial) or hammering the
yfinance/EDGAR rate limits (unbounded gather).
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


async def run_batched(
    items: list[str],
    fn: Callable[[str], Awaitable[T]],
    *,
    batch_size: int = 20,
) -> dict[str, T | Exception]:
    """Run fn(item) for each item with at most batch_size in flight.

    Per-item exceptions are captured (not raised) so one bad ticker does NOT
    abort the batch. Caller inspects results dict for Exception instances.
    """
    sem = asyncio.Semaphore(batch_size)

    async def _bounded(item: str) -> tuple[str, T | Exception]:
        async with sem:
            try:
                return item, await fn(item)
            except Exception as e:  # noqa: BLE001 — intentional aggregation
                return item, e

    pairs = await asyncio.gather(*[_bounded(t) for t in items])
    return dict(pairs)
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/orchestrator/ tests/orchestrator/__init__.py tests/orchestrator/test_batch_runner.py
git commit -m "feat(orchestrator): bounded-concurrency batch runner for ticker iteration"
```

---

### Task 3: `alpha_agent/orchestrator/alert_detector.py`

**Files:**
- Create: `alpha_agent/orchestrator/alert_detector.py`
- Create: `tests/orchestrator/test_alert_detector.py`

**Why:** Spec §4.1 lists 4 alert triggers (rating cross, gap >3σ, IV percentile >90, news velocity spike). Centralizing detection logic keeps fast cron handler readable.

- [ ] **Step 1: Failing test**

```python
# tests/orchestrator/test_alert_detector.py
from alpha_agent.orchestrator.alert_detector import detect_alerts


def _card(rating="HOLD", composite=0.0, breakdown=None):
    return {"ticker": "AAPL", "rating": rating, "composite_score": composite,
            "breakdown": breakdown or []}


def test_rating_change_triggers_alert():
    prev = _card(rating="HOLD", composite=0.3)
    curr = _card(rating="OW", composite=0.6)
    alerts = detect_alerts(prev, curr)
    assert any(a["type"] == "rating_change" for a in alerts)


def test_no_rating_change_no_alert():
    prev = _card(rating="OW", composite=1.0)
    curr = _card(rating="OW", composite=1.1)
    alerts = detect_alerts(prev, curr)
    assert not any(a["type"] == "rating_change" for a in alerts)


def test_gap_3sigma_triggers_alert():
    curr = _card(breakdown=[
        {"signal": "premarket", "z": 3.5, "raw": {"gap_sigma": 3.5}}
    ])
    alerts = detect_alerts(None, curr)
    assert any(a["type"] == "gap_3sigma" for a in alerts)


def test_iv_spike_triggers_alert():
    curr = _card(breakdown=[
        {"signal": "options", "z": 0.5, "raw": {"iv_percentile": 95}}
    ])
    alerts = detect_alerts(None, curr)
    assert any(a["type"] == "iv_spike" for a in alerts)


def test_first_observation_emits_no_alerts_except_thresholds():
    """If prev is None (first time we see this ticker), only threshold-based
    alerts fire (gap_3sigma, iv_spike, news_velocity); rating_change does not."""
    curr = _card(rating="BUY", composite=2.0)
    alerts = detect_alerts(None, curr)
    assert not any(a["type"] == "rating_change" for a in alerts)
```

- [ ] **Step 2-4: Implement**

```python
# alpha_agent/orchestrator/alert_detector.py
"""Alert trigger detection. Pure function: given prev + curr RatingCard
dicts, returns a list of alert dicts (type, payload). The cron handler
enqueues these to alert_queue with the appropriate dedup_bucket."""
from __future__ import annotations

from typing import Any


def _find_signal(card: dict, name: str) -> dict | None:
    for b in card.get("breakdown", []):
        if b.get("signal") == name:
            return b
    return None


def detect_alerts(
    prev: dict | None,
    curr: dict,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    # 1. rating_change
    if prev is not None and prev.get("rating") != curr.get("rating"):
        alerts.append({
            "type": "rating_change",
            "payload": {
                "from": prev["rating"], "to": curr["rating"],
                "composite_from": prev.get("composite_score"),
                "composite_to": curr.get("composite_score"),
            },
        })

    # 2. gap_3sigma (premarket signal)
    pm = _find_signal(curr, "premarket")
    if pm and abs(pm.get("z", 0)) > 3.0:
        alerts.append({
            "type": "gap_3sigma",
            "payload": {"gap_sigma": pm["z"], "raw": pm.get("raw")},
        })

    # 3. iv_spike (options signal)
    opt = _find_signal(curr, "options")
    if opt:
        iv_pct = (opt.get("raw") or {}).get("iv_percentile", 0)
        if iv_pct > 90:
            alerts.append({
                "type": "iv_spike",
                "payload": {"iv_percentile": iv_pct},
            })

    # 4. news_velocity (news signal — count > 3× historical mean)
    news = _find_signal(curr, "news")
    if news:
        n = (news.get("raw") or {}).get("n", 0)
        if n >= 10:  # placeholder threshold; M3 uses moving average
            alerts.append({
                "type": "news_velocity",
                "payload": {"n_24h": n},
            })

    return alerts
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/orchestrator/alert_detector.py tests/orchestrator/test_alert_detector.py
git commit -m "feat(orchestrator): alert detector for 4 trigger types (rating/gap/iv/news)"
```

---

## Phase B · Cron Handlers（Day 11 afternoon · Day 12）

### Task 4: `api/cron/slow_daily.py`

**Files:**
- Create: `api/cron/__init__.py` (empty)
- Create: `api/cron/slow_daily.py`
- Create: `tests/cron/__init__.py` (empty)
- Create: `tests/cron/test_slow_daily.py`

**Why:** Spec §4.1 — daily 21:30 北京 (= 09:30 ET pre-open). Fetch 5 slow signals (factor / analyst / earnings / insider / macro) for full SP500 universe; partial-fuse + write `daily_signals_slow`.

- [ ] **Step 1: Failing test**

```python
# tests/cron/test_slow_daily.py
"""Cron tests use a real Postgres (applied_db fixture) but mock all signal
fetches so external APIs aren't hit."""
import json
from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from api.cron.slow_daily import handler
from alpha_agent.signals.base import SignalScore

pytestmark = pytest.mark.asyncio


def _patch_slow_signals():
    targets = ["factor", "analyst", "earnings", "insider", "macro"]
    def make(name):
        def _f(t, a):
            return SignalScore(ticker=t, z=1.0, raw=1.0, confidence=0.9,
                               as_of=a, source=name, error=None)
        return _f
    return [patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=make(n))
            for n in targets]


async def test_slow_daily_writes_one_row_per_ticker(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.SP500_UNIVERSE",
        ["AAPL", "MSFT", "GOOG"],
    )
    patches = _patch_slow_signals()
    for p in patches: p.start()
    try:
        result = await handler()
    finally:
        for p in patches: p.stop()

    assert result["ok"] is True
    assert result["rows_written"] == 3

    # Verify DB
    import asyncpg
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT ticker, composite_partial FROM daily_signals_slow ORDER BY ticker"
        )
        assert [r["ticker"] for r in rows] == ["AAPL", "GOOG", "MSFT"]
        assert all(r["composite_partial"] is not None for r in rows)
    finally:
        await conn.close()


async def test_slow_daily_records_cron_run(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr("alpha_agent.universe.SP500_UNIVERSE", ["AAPL"])
    patches = _patch_slow_signals()
    for p in patches: p.start()
    try:
        await handler()
    finally:
        for p in patches: p.stop()

    import asyncpg
    conn = await asyncpg.connect(applied_db)
    try:
        run = await conn.fetchrow(
            "SELECT * FROM cron_runs WHERE cron_name='slow_daily' "
            "ORDER BY started_at DESC LIMIT 1"
        )
        assert run["ok"] is True
        assert run["error_count"] == 0
    finally:
        await conn.close()


async def test_slow_daily_logs_errors_per_failing_ticker(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr("alpha_agent.universe.SP500_UNIVERSE", ["AAPL", "BAD"])

    def fake_factor(t, a):
        if t == "BAD":
            return SignalScore(ticker=t, z=0.0, raw=None, confidence=0.0,
                               as_of=a, source="factor_engine",
                               error="ConnectionError: simulated")
        return SignalScore(ticker=t, z=1.0, raw=1.0, confidence=0.9,
                           as_of=a, source="factor_engine", error=None)

    other_patches = [patch(f"alpha_agent.signals.{n}.fetch_signal",
                           side_effect=lambda t, a, name=n: SignalScore(
                               ticker=t, z=0.5, raw=0.5, confidence=0.8,
                               as_of=a, source=name, error=None))
                     for n in ["analyst", "earnings", "insider", "macro"]]
    patches = [patch("alpha_agent.signals.factor.fetch_signal", side_effect=fake_factor)]
    patches.extend(other_patches)
    for p in patches: p.start()
    try:
        result = await handler()
    finally:
        for p in patches: p.stop()

    # Both rows still written; BAD row has factor with confidence=0
    assert result["ok"] is True
    assert result["rows_written"] == 2
```

- [ ] **Step 2-4: Implement**

```python
# api/cron/slow_daily.py
"""Vercel cron: slow daily signal fetch + partial fusion → DB.

Trigger: 21:30 Asia/Shanghai = 09:30 ET pre-open (cron in vercel.json).
Universe: SP500 ~500 tickers.
Signals: factor, analyst, earnings, insider, macro (5 slow signals).
Output: 1 row per ticker in daily_signals_slow.

Spec §4.1. Always returns 200 with {ok: bool, rows_written, errors}; never
raises 5xx (cron retry storms).
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import asyncpg

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS, normalize_weights
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.signals import factor, analyst, earnings, insider, macro
from alpha_agent.signals.base import SignalScore
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import insert_signal_slow, log_error

_SLOW_MODULES = {"factor": factor, "analyst": analyst, "earnings": earnings,
                 "insider": insider, "macro": macro}
_SLOW_WEIGHTS = {k: v for k, v in DEFAULT_WEIGHTS.items() if k in _SLOW_MODULES}


async def _fetch_one(ticker: str, as_of: datetime) -> dict[str, SignalScore]:
    return {name: mod.fetch_signal(ticker, as_of) for name, mod in _SLOW_MODULES.items()}


async def handler() -> dict[str, Any]:
    """Vercel function entry point."""
    from alpha_agent.universe import SP500_UNIVERSE

    pool = await get_pool(os.environ["DATABASE_URL"])
    today = datetime.now(UTC).date().isoformat()
    now = datetime.now(UTC)

    started_at = now
    errors: list[dict] = []

    async def _per_ticker(t: str) -> str:
        sigs = await _fetch_one(t, now)
        norm_w = normalize_weights(_SLOW_WEIGHTS)
        result = combine(sigs, norm_w)
        await insert_signal_slow(pool, t, today, result.composite,
                                 {"breakdown": result.breakdown})
        return t

    results = await run_batched(SP500_UNIVERSE, _per_ticker, batch_size=20)
    rows_written = sum(1 for v in results.values() if not isinstance(v, Exception))
    for t, v in results.items():
        if isinstance(v, Exception):
            errors.append({"ticker": t, "err": str(v)[:200]})
            await log_error(pool, layer="cron", component="cron.slow_daily",
                            ticker=t, err_type=type(v).__name__, err_message=str(v)[:200])

    finished_at = datetime.now(UTC)
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "slow_daily", started_at, finished_at, len(errors) == 0, len(errors),
        json.dumps({"rows_written": rows_written}),
    )
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}
```

- [ ] **Step 5: Commit**

```bash
git add api/cron/__init__.py api/cron/slow_daily.py tests/cron/__init__.py tests/cron/test_slow_daily.py
git commit -m "feat(cron): slow_daily handler — 5 slow signals → daily_signals_slow"
```

---

### Task 5: `api/cron/fast_intraday.py`

**Files:**
- Create: `api/cron/fast_intraday.py`
- Create: `tests/cron/test_fast_intraday.py`

**Why:** Spec §4.1 — every 15min during market hours (9:30-16:00 ET). Pull fast signals (technicals, options, news, premarket) for watchlist + top_100 from slow; merge with cached slow; full fuse; write `daily_signals_fast` + emit alerts.

- [ ] **Step 1: Failing test**

```python
# tests/cron/test_fast_intraday.py
from datetime import datetime, UTC
from unittest.mock import patch

import pytest

from api.cron.fast_intraday import handler
from alpha_agent.signals.base import SignalScore

pytestmark = pytest.mark.asyncio


def _patch_all_signals():
    targets = ["factor", "technicals", "analyst", "earnings", "news",
               "insider", "options", "premarket", "macro", "calendar"]
    def make(name):
        def _f(t, a):
            return SignalScore(ticker=t, z=0.8, raw=0.8, confidence=0.85,
                               as_of=a, source=name, error=None)
        return _f
    return [patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=make(n))
            for n in targets]


async def test_fast_intraday_writes_full_card(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL", "MSFT"],
    )
    patches = _patch_all_signals()
    for p in patches: p.start()
    try:
        result = await handler()
    finally:
        for p in patches: p.stop()

    assert result["ok"] is True
    assert result["rows_written"] == 2

    import asyncpg
    conn = await asyncpg.connect(applied_db)
    try:
        rows = await conn.fetch(
            "SELECT ticker, rating, confidence FROM daily_signals_fast "
            "ORDER BY ticker"
        )
        assert len(rows) == 2
        for r in rows:
            assert r["rating"] in {"BUY", "OW", "HOLD", "UW", "SELL"}
            assert 0.0 <= r["confidence"] <= 1.0
    finally:
        await conn.close()


async def test_fast_intraday_emits_alert_on_rating_change(applied_db, monkeypatch):
    """Pre-seed daily_signals_fast with an old card; new run with different
    rating should enqueue rating_change alert."""
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL"],
    )
    today = datetime.now(UTC).date().isoformat()

    import asyncpg
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast (ticker, date, composite, rating, "
            "confidence, breakdown, partial) VALUES ($1, $2::date, $3, $4, $5, $6::jsonb, $7)",
            "AAPL", today, 0.0, "HOLD", 0.5, '{"breakdown": []}', False,
        )
    finally:
        await conn.close()

    patches = _patch_all_signals()  # all z=0.8 → composite ~0.8 → OW
    for p in patches: p.start()
    try:
        await handler()
    finally:
        for p in patches: p.stop()

    conn = await asyncpg.connect(applied_db)
    try:
        alerts = await conn.fetch(
            "SELECT type, payload FROM alert_queue WHERE ticker='AAPL'"
        )
        assert any(a["type"] == "rating_change" for a in alerts)
    finally:
        await conn.close()
```

- [ ] **Step 2-4: Implement**

```python
# api/cron/fast_intraday.py
"""Vercel cron: fast intraday signal fetch + full fusion + alert emission.

Trigger: every 15min, weekdays 9:30-16:00 ET.
Universe: watchlist ∪ top_100 from daily_signals_slow.
Signals: full 10 (technicals, options, news, premarket fresh; factor/analyst/
earnings/insider/macro pulled from cached slow row + recombined).

Spec §4.1, §4.3.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.rating import map_to_tier, compute_confidence
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.orchestrator.alert_detector import detect_alerts
from alpha_agent.signals import (
    factor, technicals, analyst, earnings, news,
    insider, options, premarket, macro, calendar as cal,
)
from alpha_agent.signals.base import SignalScore
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import (
    upsert_signal_fast, enqueue_alert, log_error,
)

_ALL_MODULES = {
    "factor": factor, "technicals": technicals, "analyst": analyst,
    "earnings": earnings, "news": news, "insider": insider,
    "options": options, "premarket": premarket, "macro": macro,
    "calendar": cal,
}


async def handler() -> dict[str, Any]:
    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    now = datetime.now(UTC)
    today = now.date().isoformat()
    started_at = now

    universe = get_watchlist(top_n=100)
    errors: list[dict] = []
    bucket = int(now.timestamp()) // 1800  # 30-min dedup window

    async def _per_ticker(t: str) -> str:
        # Fetch all 10 signals
        sigs = {name: mod.fetch_signal(t, now) for name, mod in _ALL_MODULES.items()}

        # Combine + rate
        result = combine(sigs, DEFAULT_WEIGHTS)
        contributing_zs = [b["z"] for b in result.breakdown if b["weight_effective"] > 0]
        confidence = compute_confidence(contributing_zs)
        rating = map_to_tier(result.composite)

        # Read previous card for rating_change comparison
        prev_row = await pool.fetchrow(
            "SELECT rating, composite, breakdown FROM daily_signals_fast "
            "WHERE ticker=$1 AND date=$2::date",
            t, today,
        )
        prev_card = (
            {"ticker": t, "rating": prev_row["rating"],
             "composite_score": prev_row["composite"],
             "breakdown": json.loads(prev_row["breakdown"]).get("breakdown", [])}
            if prev_row else None
        )
        curr_card = {"ticker": t, "rating": rating, "composite_score": result.composite,
                     "breakdown": result.breakdown}

        # Write fast row
        await upsert_signal_fast(
            pool, t, today, result.composite, rating, confidence,
            {"breakdown": result.breakdown}, partial=False,
        )

        # Detect + enqueue alerts
        for alert in detect_alerts(prev_card, curr_card):
            await enqueue_alert(pool, t, alert["type"], alert["payload"], bucket)

        return t

    results = await run_batched(universe, _per_ticker, batch_size=20)
    rows_written = sum(1 for v in results.values() if not isinstance(v, Exception))
    for t, v in results.items():
        if isinstance(v, Exception):
            errors.append({"ticker": t, "err": str(v)[:200]})
            await log_error(pool, layer="cron", component="cron.fast_intraday",
                            ticker=t, err_type=type(v).__name__, err_message=str(v)[:200])

    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "fast_intraday", started_at, datetime.now(UTC), len(errors) == 0,
        len(errors), json.dumps({"rows_written": rows_written}),
    )
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}
```

- [ ] **Step 5: Commit**

```bash
git add api/cron/fast_intraday.py tests/cron/test_fast_intraday.py
git commit -m "feat(cron): fast_intraday handler — 10 signals + alert emission → daily_signals_fast"
```

---

### Task 6: `api/cron/alert_dispatcher.py`

**Files:**
- Create: `api/cron/alert_dispatcher.py`
- Create: `tests/cron/test_alert_dispatcher.py`

**Why:** Spec §4.1 — every 5min, drains `alert_queue`. Phase 1 stub: marks alerts as dispatched + logs to console (real push channels in Phase 2 backlog per spec §9).

- [ ] **Step 1: Failing test**

```python
# tests/cron/test_alert_dispatcher.py
import pytest
from api.cron.alert_dispatcher import handler

pytestmark = pytest.mark.asyncio


async def test_dispatcher_marks_pending_alerts_dispatched(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)

    import asyncpg
    conn = await asyncpg.connect(applied_db)
    try:
        for i in range(3):
            await conn.execute(
                "INSERT INTO alert_queue (ticker, type, payload, dedup_bucket) "
                "VALUES ($1, $2, $3::jsonb, $4)",
                f"T{i}", "rating_change", '{"to": "OW"}', 1000 + i,
            )
    finally:
        await conn.close()

    result = await handler()
    assert result["ok"] is True
    assert result["dispatched_count"] == 3

    conn = await asyncpg.connect(applied_db)
    try:
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM alert_queue WHERE dispatched=false"
        )
        assert pending == 0
    finally:
        await conn.close()


async def test_dispatcher_handles_empty_queue(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    result = await handler()
    assert result["ok"] is True
    assert result["dispatched_count"] == 0
```

- [ ] **Step 2-4: Implement**

```python
# api/cron/alert_dispatcher.py
"""Vercel cron: drain alert_queue.

Trigger: every 5min.
Phase 1 implementation: marks alerts dispatched + logs structured payload.
Phase 2+ adds real push channels (Telegram/email/webhook).

Spec §4.1, §5.2.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import list_pending_alerts, mark_alert_dispatched

logger = logging.getLogger(__name__)


async def _push_to_channel(alert: dict[str, Any]) -> None:
    """Phase 1 stub: log to stdout in JSON format. Phase 2 adds real push."""
    logger.info("ALERT %s", json.dumps({
        "ticker": alert["ticker"], "type": alert["type"],
        "payload": json.loads(alert["payload"]) if isinstance(alert["payload"], str) else alert["payload"],
        "created_at": alert["created_at"].isoformat(),
    }))


async def handler() -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    now = datetime.now(UTC)

    pending = await list_pending_alerts(pool, limit=200)
    dispatched_count = 0
    for alert in pending:
        try:
            await _push_to_channel(dict(alert))
            await mark_alert_dispatched(pool, alert["id"])
            dispatched_count += 1
        except Exception as e:  # noqa: BLE001 — push failure shouldn't kill drain
            logger.error("dispatcher: failed to push alert %d: %s", alert["id"], e)

    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "alert_dispatcher", now, datetime.now(UTC), True, 0,
        json.dumps({"dispatched_count": dispatched_count}),
    )
    return {"ok": True, "dispatched_count": dispatched_count}
```

- [ ] **Step 5: Commit**

```bash
git add api/cron/alert_dispatcher.py tests/cron/test_alert_dispatcher.py
git commit -m "feat(cron): alert_dispatcher — drain queue + mark dispatched (Phase 1 log-only)"
```

---

## Phase C · API Endpoints（Day 13-14）

### Task 7: `alpha_agent/api/routes/picks.py`

**Files:**
- Create: `alpha_agent/api/routes/picks.py`
- Create: `tests/api/__init__.py` (empty)
- Create: `tests/api/conftest.py`
- Create: `tests/api/test_picks.py`

**Why:** The headline endpoint. Returns the lean ranked list users see on `/picks`. SLA: < 500ms p95. Reads only from DB; no synchronous signal fetch.

- [ ] **Step 1: Create test client fixture**

```python
# tests/api/conftest.py
"""FastAPI TestClient + DB fixture for API route tests."""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from alpha_agent.api.app import create_app


@pytest.fixture
def client_with_db(applied_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", applied_db)
    app = create_app()
    return TestClient(app)
```

- [ ] **Step 2: Failing test**

```python
# tests/api/test_picks.py
import json
from datetime import datetime, UTC, date

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def _seed_fast_rows(applied_db, n=5):
    conn = await asyncpg.connect(applied_db)
    today = date.today().isoformat()
    try:
        ratings = ["BUY", "OW", "HOLD", "UW", "SELL"]
        for i, rating in enumerate(ratings[:n]):
            await conn.execute(
                "INSERT INTO daily_signals_fast (ticker, date, composite, rating, "
                "confidence, breakdown, partial) VALUES ($1, $2::date, $3, $4, $5, $6::jsonb, $7)",
                f"T{i}", today, 2.0 - 0.5 * i, rating, 0.8, '{"breakdown": []}', False,
            )
    finally:
        await conn.close()


async def test_picks_lean_returns_sorted_by_composite(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert "picks" in body
    composites = [p["composite_score"] for p in body["picks"]]
    assert composites == sorted(composites, reverse=True)


async def test_picks_lean_respects_limit(client_with_db, applied_db):
    await _seed_fast_rows(applied_db, n=5)
    r = client_with_db.get("/api/picks/lean?limit=2")
    assert r.status_code == 200
    assert len(r.json()["picks"]) == 2


async def test_picks_lean_empty_db_returns_empty_list(client_with_db):
    r = client_with_db.get("/api/picks/lean")
    assert r.status_code == 200
    assert r.json()["picks"] == []
    assert r.json()["stale"] is False
```

- [ ] **Step 3-4: Implement**

```python
# alpha_agent/api/routes/picks.py
"""GET /api/picks/lean — top N RatingCards by composite_score."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.core.types import RatingCard, BreakdownEntry

router = APIRouter(prefix="/api/picks", tags=["picks"])

_STALE_THRESHOLD_HOURS = 24


class PicksResponse(BaseModel):
    picks: list[RatingCard]
    as_of: datetime | None
    stale: bool


@router.get("/lean", response_model=PicksResponse)
async def picks_lean(limit: int = Query(20, ge=1, le=100)) -> PicksResponse:
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT ticker, date, composite, rating, confidence, breakdown, fetched_at
        FROM daily_signals_fast
        ORDER BY composite DESC
        LIMIT $1
        """,
        limit,
    )
    if not rows:
        return PicksResponse(picks=[], as_of=None, stale=False)

    cards: list[RatingCard] = []
    most_recent = max(r["fetched_at"] for r in rows)
    stale = (datetime.now(UTC) - most_recent) > timedelta(hours=_STALE_THRESHOLD_HOURS)

    for r in rows:
        breakdown_data = json.loads(r["breakdown"]).get("breakdown", [])
        from alpha_agent.fusion.attribution import top_drivers, top_drags
        cards.append(RatingCard(
            ticker=r["ticker"], rating=r["rating"],
            confidence=r["confidence"], composite_score=r["composite"],
            as_of=r["fetched_at"],
            breakdown=[BreakdownEntry(**b) for b in breakdown_data],
            top_drivers=top_drivers(breakdown_data),
            top_drags=top_drags(breakdown_data),
        ))

    return PicksResponse(picks=cards, as_of=most_recent, stale=stale)
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/picks.py tests/api/__init__.py \
        tests/api/conftest.py tests/api/test_picks.py
git commit -m "feat(api): GET /api/picks/lean — top N RatingCards by composite (M2)"
```

> **Note:** This task introduces `alpha_agent/api/dependencies.py` (assumed to provide `get_db_pool()`) and `alpha_agent/api/app.py` (`create_app()`). If they don't exist, create thin wrappers in this task too:
> - `alpha_agent/api/dependencies.py` — singleton accessor returning `await get_pool(os.environ["DATABASE_URL"])`
> - `alpha_agent/api/app.py:create_app()` — `FastAPI()` instance + `include_router(picks.router)`

---

### Task 8: `alpha_agent/api/routes/stock.py`

**Files:**
- Create: `alpha_agent/api/routes/stock.py`
- Create: `tests/api/test_stock.py`

**Why:** Powers `/stock/[ticker]` page. Returns full RatingCard for one ticker.

- [ ] **Step 1: Failing test**

```python
# tests/api/test_stock.py
import json
from datetime import date

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def _seed(applied_db, ticker="AAPL"):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast (ticker, date, composite, rating, "
            "confidence, breakdown, partial) VALUES ($1, $2::date, $3, $4, $5, $6::jsonb, $7)",
            ticker, date.today().isoformat(), 1.23, "OW", 0.72,
            '{"breakdown": []}', False,
        )
    finally:
        await conn.close()


async def test_stock_returns_full_card(client_with_db, applied_db):
    await _seed(applied_db)
    r = client_with_db.get("/api/stock/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["card"]["ticker"] == "AAPL"
    assert body["card"]["rating"] == "OW"


async def test_stock_unknown_ticker_returns_404(client_with_db):
    r = client_with_db.get("/api/stock/NOTREAL")
    assert r.status_code == 404


async def test_stock_lowercase_ticker_normalized(client_with_db, applied_db):
    await _seed(applied_db, "MSFT")
    r = client_with_db.get("/api/stock/msft")
    assert r.status_code == 200
    assert r.json()["card"]["ticker"] == "MSFT"
```

- [ ] **Step 2-4: Implement**

```python
# alpha_agent/api/routes/stock.py
"""GET /api/stock/{ticker} — full RatingCard for one ticker."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.core.types import RatingCard, BreakdownEntry
from alpha_agent.fusion.attribution import top_drivers, top_drags

router = APIRouter(prefix="/api/stock", tags=["stock"])


class StockResponse(BaseModel):
    card: RatingCard
    stale: bool


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(ticker: str = Path(min_length=1, max_length=10)) -> StockResponse:
    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        SELECT ticker, date, composite, rating, confidence, breakdown, fetched_at
        FROM daily_signals_fast
        WHERE ticker=$1
        ORDER BY date DESC, fetched_at DESC
        LIMIT 1
        """,
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown_data = json.loads(row["breakdown"]).get("breakdown", [])
    card = RatingCard(
        ticker=row["ticker"], rating=row["rating"],
        confidence=row["confidence"], composite_score=row["composite"],
        as_of=row["fetched_at"],
        breakdown=[BreakdownEntry(**b) for b in breakdown_data],
        top_drivers=top_drivers(breakdown_data),
        top_drags=top_drags(breakdown_data),
    )
    stale = (datetime.now(UTC) - row["fetched_at"]) > timedelta(hours=24)
    return StockResponse(card=card, stale=stale)
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/stock.py tests/api/test_stock.py
git commit -m "feat(api): GET /api/stock/{ticker} — full RatingCard with stale flag (M2)"
```

---

### Task 9: `alpha_agent/api/routes/brief.py` (Lean stub)

**Files:**
- Create: `alpha_agent/api/routes/brief.py`
- Create: `tests/api/test_brief.py`

**Why:** Spec §3.4: Lean mode = rule-based thesis from top_drivers/top_drags, NO LLM. Rich mode (BYOK LLM) is M3 — this M2 endpoint stubs that out and returns Lean only.

- [ ] **Step 1: Failing test**

```python
# tests/api/test_brief.py
from datetime import date
import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def _seed(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_signals_fast (ticker, date, composite, rating, "
            "confidence, breakdown, partial) VALUES ($1, $2::date, $3, $4, $5, $6::jsonb, $7)",
            "AAPL", date.today().isoformat(), 1.23, "OW", 0.72,
            '{"breakdown":[{"signal":"factor","z":1.8,"weight":0.30,"weight_effective":0.30,'
            '"contribution":0.54,"raw":1.8,"source":"factor_engine","timestamp":"2024-01-01T00:00:00+00:00","error":null}]}',
            False,
        )
    finally:
        await conn.close()


async def test_brief_lean_mode_returns_thesis(client_with_db, applied_db):
    await _seed(applied_db)
    r = client_with_db.post("/api/brief/AAPL", json={"mode": "lean"})
    assert r.status_code == 200
    body = r.json()
    assert "thesis" in body
    assert "bull" in body["thesis"] and "bear" in body["thesis"]
    assert isinstance(body["thesis"]["bull"], list)


async def test_brief_rich_mode_returns_501_in_m2(client_with_db, applied_db):
    """Rich BYOK LLM is M3; M2 stub returns 501 Not Implemented."""
    await _seed(applied_db)
    r = client_with_db.post("/api/brief/AAPL", json={
        "mode": "rich", "llm_provider": "anthropic", "api_key": "sk-test",
    })
    assert r.status_code == 501


async def test_brief_unknown_ticker_returns_404(client_with_db):
    r = client_with_db.post("/api/brief/NOTREAL", json={"mode": "lean"})
    assert r.status_code == 404
```

- [ ] **Step 2-4: Implement**

```python
# alpha_agent/api/routes/brief.py
"""POST /api/brief/{ticker} — Lean rule-based thesis (Rich/LLM is M3 stub)."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.fusion.attribution import top_drivers, top_drags

router = APIRouter(prefix="/api/brief", tags=["brief"])


class BriefRequest(BaseModel):
    mode: Literal["lean", "rich"] = "lean"
    llm_provider: str | None = None
    api_key: str | None = Field(default=None, repr=False)


class Thesis(BaseModel):
    bull: list[str]
    bear: list[str]


class BriefResponse(BaseModel):
    ticker: str
    rating: str
    thesis: Thesis
    rendered_at: str


def _render_lean_thesis(rating: str, breakdown: list[dict]) -> Thesis:
    drivers = top_drivers(breakdown, n=3)
    drags = top_drags(breakdown, n=3)
    bull = [
        f"{d.upper()} signal contributing positively"
        f" (z={next(b['z'] for b in breakdown if b['signal']==d):+.2f})"
        for d in drivers
    ]
    bear = [
        f"{d.upper()} signal pulling negatively"
        f" (z={next(b['z'] for b in breakdown if b['signal']==d):+.2f})"
        for d in drags
    ]
    if not bull:
        bull = ["No strongly positive signals detected"]
    if not bear:
        bear = ["No strongly negative signals detected"]
    return Thesis(bull=bull, bear=bear)


@router.post("/{ticker}", response_model=BriefResponse)
async def post_brief(
    payload: BriefRequest,
    ticker: str = Path(min_length=1, max_length=10),
) -> BriefResponse:
    if payload.mode == "rich":
        raise HTTPException(
            status_code=501,
            detail="Rich BYOK LLM brief not implemented in M2 (deferred to M3)",
        )

    ticker = ticker.upper()
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT rating, breakdown, fetched_at FROM daily_signals_fast "
        "WHERE ticker=$1 ORDER BY fetched_at DESC LIMIT 1",
        ticker,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")

    breakdown = json.loads(row["breakdown"]).get("breakdown", [])
    thesis = _render_lean_thesis(row["rating"], breakdown)
    return BriefResponse(
        ticker=ticker, rating=row["rating"],
        thesis=thesis, rendered_at=row["fetched_at"].isoformat(),
    )
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/brief.py tests/api/test_brief.py
git commit -m "feat(api): POST /api/brief/{ticker} — Lean rule-based thesis (Rich=M3 stub)"
```

---

### Task 10: `alpha_agent/api/routes/health.py` (3 health endpoints)

**Files:**
- Create: `alpha_agent/api/routes/health.py`
- Create: `tests/api/test_health.py`

**Why:** Spec §5.7 — CLAUDE.md 部署地面真相三板斧 mandate. Independent of business routes.

- [ ] **Step 1: Failing test**

```python
# tests/api/test_health.py
from datetime import datetime, UTC, date

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


async def test_health_returns_json_content_type(client_with_db):
    r = client_with_db.get("/api/_health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


async def test_health_includes_db_status(client_with_db):
    r = client_with_db.get("/api/_health")
    body = r.json()
    assert body["db"] == "ok"


async def test_health_signals_returns_10_rows(client_with_db, applied_db):
    """Even with no error_log entries, all 10 signals listed (last_error=null)."""
    r = client_with_db.get("/api/_health/signals")
    assert r.status_code == 200
    sigs = r.json()["signals"]
    names = {s["name"] for s in sigs}
    assert names == {"factor", "technicals", "analyst", "earnings", "news",
                     "insider", "options", "premarket", "macro", "calendar"}


async def test_health_cron_returns_recent_runs_per_cron(client_with_db, applied_db):
    """Seed 3 runs of slow_daily; expect them in /api/_health/cron."""
    conn = await asyncpg.connect(applied_db)
    try:
        for i in range(3):
            await conn.execute(
                "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count) "
                "VALUES ($1, $2, $3, $4, $5)",
                "slow_daily", datetime.now(UTC), datetime.now(UTC), True, 0,
            )
    finally:
        await conn.close()

    r = client_with_db.get("/api/_health/cron")
    assert r.status_code == 200
    cron_runs = r.json()["cron"]
    assert len(cron_runs.get("slow_daily", [])) == 3
```

- [ ] **Step 2-4: Implement**

```python
# alpha_agent/api/routes/health.py
"""Health endpoints. Independent of business routes — these expose ground
truth for deployment verification (CLAUDE.md 三板斧)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from alpha_agent.api.dependencies import get_db_pool

router = APIRouter(prefix="/api/_health", tags=["health"])

_SIGNAL_NAMES = ["factor", "technicals", "analyst", "earnings", "news",
                 "insider", "options", "premarket", "macro", "calendar"]


class HealthResponse(BaseModel):
    tunnel: str
    db: str
    last_slow_cron: str | None
    last_fast_cron: str | None
    last_dispatcher: str | None


class SignalStatus(BaseModel):
    name: str
    last_success: str | None
    last_error: str | None
    error_count_24h: int


class HealthSignalsResponse(BaseModel):
    signals: list[SignalStatus]


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    pool = await get_db_pool()
    try:
        await pool.fetchval("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "down"

    async def _last(cron_name: str) -> str | None:
        row = await pool.fetchrow(
            "SELECT started_at FROM cron_runs WHERE cron_name=$1 "
            "ORDER BY started_at DESC LIMIT 1", cron_name)
        return row["started_at"].isoformat() if row else None

    return HealthResponse(
        tunnel="ok", db=db_status,
        last_slow_cron=await _last("slow_daily"),
        last_fast_cron=await _last("fast_intraday"),
        last_dispatcher=await _last("alert_dispatcher"),
    )


@router.get("/signals", response_model=HealthSignalsResponse)
async def health_signals() -> HealthSignalsResponse:
    pool = await get_db_pool()
    out: list[SignalStatus] = []
    for name in _SIGNAL_NAMES:
        comp = f"signals.{name}"
        last_err = await pool.fetchrow(
            "SELECT ts, err_message FROM error_log WHERE component=$1 "
            "ORDER BY ts DESC LIMIT 1", comp)
        count_24h = await pool.fetchval(
            "SELECT COUNT(*) FROM error_log WHERE component=$1 AND ts > now() - INTERVAL '24 hours'", comp)
        out.append(SignalStatus(
            name=name, last_success=None,  # not yet tracked; M3 backlog
            last_error=(last_err["err_message"] if last_err else None),
            error_count_24h=count_24h or 0,
        ))
    return HealthSignalsResponse(signals=out)


@router.get("/cron")
async def health_cron() -> dict[str, dict[str, list[Any]]]:
    pool = await get_db_pool()
    out: dict[str, list[Any]] = {}
    for name in ("slow_daily", "fast_intraday", "alert_dispatcher"):
        rows = await pool.fetch(
            "SELECT started_at, finished_at, ok, error_count, details "
            "FROM cron_runs WHERE cron_name=$1 ORDER BY started_at DESC LIMIT 5",
            name)
        out[name] = [
            {"started_at": r["started_at"].isoformat(),
             "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
             "ok": r["ok"], "error_count": r["error_count"]}
            for r in rows
        ]
    return {"cron": out}
```

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/health.py tests/api/test_health.py
git commit -m "feat(api): /api/_health{,_signals,_cron} — deployment ground truth (CLAUDE.md 三板斧)"
```

---

## Phase D · Wiring + Schema Drift（Day 14 afternoon）

### Task 11: Vercel config + router registration

**Files:**
- Modify: `vercel.json` (add `crons` array; add `functions` config for 300s timeout)
- Modify: `alpha_agent/api/app.py` (or create) — register 4 new routers
- Create: `alpha_agent/api/dependencies.py` if missing

- [ ] **Step 1: Update `vercel.json`**

Replace existing content with:
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "version": 2,
  "regions": ["hkg1"],
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index" },
    { "source": "/qcore", "destination": "/api/index" }
  ],
  "functions": {
    "api/cron/slow_daily.py": { "maxDuration": 300 },
    "api/cron/fast_intraday.py": { "maxDuration": 90 },
    "api/cron/alert_dispatcher.py": { "maxDuration": 30 }
  },
  "crons": [
    { "path": "/api/cron/slow_daily", "schedule": "30 13 * * *" },
    { "path": "/api/cron/fast_intraday", "schedule": "*/15 14-21 * * 1-5" },
    { "path": "/api/cron/alert_dispatcher", "schedule": "*/5 * * * *" }
  ]
}
```

(`30 13 * * *` UTC = 21:30 北京. `14-21` UTC = 9:30-16:00 ET roughly; widened slightly.)

- [ ] **Step 2: `alpha_agent/api/dependencies.py`**

If file doesn't exist:
```python
"""FastAPI dependency injection helpers."""
from __future__ import annotations

import os

import asyncpg

from alpha_agent.storage.postgres import get_pool


async def get_db_pool() -> asyncpg.Pool:
    return await get_pool(os.environ["DATABASE_URL"])
```

- [ ] **Step 3: `alpha_agent/api/app.py`**

If a `create_app()` exists, just `include_router` 4 new routers. If not:
```python
"""FastAPI app factory."""
from __future__ import annotations

from fastapi import FastAPI

from alpha_agent.api.routes import picks, stock, brief, health


def create_app() -> FastAPI:
    app = FastAPI(title="Alpha Agent v4 API", version="0.1.0")
    app.include_router(picks.router)
    app.include_router(stock.router)
    app.include_router(brief.router)
    app.include_router(health.router)
    return app


app = create_app()  # for Vercel ASGI handler
```

- [ ] **Step 4: Verify `/api/openapi.json` exposes the 7 expected paths**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/.worktrees/m2-cron-api
python -c "from alpha_agent.api.app import create_app; \
import json; \
spec = create_app().openapi(); \
print(sorted(spec['paths'].keys()))"
```

Expected output:
```
['/api/_health', '/api/_health/cron', '/api/_health/signals', '/api/brief/{ticker}', '/api/picks/lean', '/api/stock/{ticker}']
```

(That's 6 unique paths; with method variants the openapi dict has 6.)

- [ ] **Step 5: Commit**

```bash
git add vercel.json alpha_agent/api/dependencies.py alpha_agent/api/app.py
git commit -m "ci(m2): vercel.json crons + 300s slow_daily timeout + register 4 routers"
```

---

### Task 12: API contract drift gate

**Files:**
- Modify: `Makefile` (add `openapi-export` + `openapi-check` targets)
- Create: `tests/api/test_openapi_export.py`
- Create: `frontend/api-types.gen.ts` (initial commit; CI keeps it fresh)

**Why:** Spec §6.5 — frontend types are generated from backend OpenAPI; CI fails if drift.

- [ ] **Step 1: Test the export tooling exists**

```python
# tests/api/test_openapi_export.py
import json
from pathlib import Path


def test_openapi_export_matches_disk():
    """Verifies frontend/api-types.gen.ts is up to date with backend openapi.

    Run `make openapi-export` to regenerate when intentionally changing API."""
    from alpha_agent.api.app import create_app
    spec = create_app().openapi()

    expected_path = Path(__file__).parent.parent.parent / "openapi.snapshot.json"
    if not expected_path.exists():
        # First-run: write snapshot, fail
        expected_path.write_text(json.dumps(spec, indent=2, sort_keys=True))
        raise AssertionError(f"Wrote initial snapshot to {expected_path}; review and re-run")

    on_disk = json.loads(expected_path.read_text())
    if json.dumps(on_disk, sort_keys=True) != json.dumps(spec, sort_keys=True):
        raise AssertionError(
            "OpenAPI schema drift detected. Run `make openapi-export` to update."
        )
```

- [ ] **Step 2: Add Makefile targets**

```makefile
openapi-export:
	python -c "from alpha_agent.api.app import create_app; \
	import json; \
	open('openapi.snapshot.json','w').write(json.dumps(create_app().openapi(), indent=2, sort_keys=True))"
	@echo "Snapshot updated. Commit openapi.snapshot.json."
	@if [ -d frontend ]; then \
	  npx -y openapi-typescript openapi.snapshot.json -o frontend/api-types.gen.ts || \
	  echo "Frontend type gen skipped (npx unavailable)"; \
	fi

openapi-check:
	pytest tests/api/test_openapi_export.py -v
```

- [ ] **Step 3: First export**

```bash
make openapi-export
git add openapi.snapshot.json
```

(If frontend dir doesn't exist yet, skip the .ts gen.)

- [ ] **Step 4: Run check — should PASS**

```bash
make openapi-check
```

- [ ] **Step 5: Commit**

```bash
git add Makefile openapi.snapshot.json tests/api/test_openapi_export.py
git commit -m "ci(m2): openapi schema drift gate (snapshot + drift test)"
```

---

## Phase E · Deploy + Acceptance（Day 15）

### Task 13: `deploy.sh` 三板斧 + `m2-acceptance` Makefile target

**Files:**
- Create: `deploy.sh` (or modify if exists)
- Modify: `Makefile` (add `m2-acceptance`)

**Why:** Spec §6.8 — every deploy verifies tunnel + routes + bundle. M2 specific: cron + business + health.

- [ ] **Step 1: `deploy.sh`**

```bash
#!/usr/bin/env bash
# Deploy to Vercel preview + verify per spec §6.8
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> deploying to vercel preview"
DEPLOY_OUT=$(vercel deploy --yes 2>&1)
URL=$(echo "$DEPLOY_OUT" | grep -oE 'https://[a-z0-9.-]+\.vercel\.app' | head -1)
if [[ -z "$URL" ]]; then
    echo "ERROR: failed to extract URL from vercel deploy output:"
    echo "$DEPLOY_OUT"
    exit 1
fi
echo "==> preview URL: $URL"

echo "==> 1. backend liveness (Content-Type JSON)"
HEALTH_CT=$(curl -fsI "$URL/api/_health" | grep -i 'content-type' | tr -d '\r')
if ! echo "$HEALTH_CT" | grep -qi 'application/json'; then
    echo "FAIL: $URL/api/_health did not return JSON. Got: $HEALTH_CT"
    exit 1
fi

echo "==> 2. route completeness (openapi paths)"
PATH_COUNT=$(curl -fs "$URL/api/openapi.json" | jq '.paths | keys | length')
if [[ "$PATH_COUNT" -lt 6 ]]; then
    echo "FAIL: expected ≥6 OpenAPI paths, got $PATH_COUNT"
    exit 1
fi

echo "==> 3. picks.lean smoke"
curl -fs "$URL/api/picks/lean?limit=1" | jq -e '.picks' > /dev/null

echo "==> 4. health.signals smoke (10 rows)"
ROWS=$(curl -fs "$URL/api/_health/signals" | jq '.signals | length')
[[ "$ROWS" -eq 10 ]] || { echo "FAIL: expected 10 signal rows, got $ROWS"; exit 1; }

echo "✓ M2 deploy + 三板斧 PASS at $URL"
```

Make executable: `chmod +x deploy.sh`.

- [ ] **Step 2: Makefile target**

```makefile
m2-acceptance:
	@echo "==> Running M2 acceptance suite"
	pytest tests/api tests/orchestrator tests/cron \
	    --cov=alpha_agent.api.routes --cov=alpha_agent.orchestrator \
	    --cov-fail-under=85 -m "not slow"
	$(MAKE) openapi-check
	@echo "M2 acceptance PASS (deploy.sh runs separately for actual Vercel deploy)"
```

- [ ] **Step 3: Local acceptance**

```bash
make m2-acceptance
```

Expected: pytest + openapi-check both pass.

- [ ] **Step 4: Commit**

```bash
git add deploy.sh Makefile
chmod +x deploy.sh
git commit -m "ci(m2): deploy.sh 三板斧 + m2-acceptance Makefile target"
```

---

### Task 14: M2 end-to-end integration test

**Files:**
- Create: `tests/api/test_full_pipeline_e2e.py`

**Why:** Verifies the full M2 pipeline: cron writes → API reads → JSON shape matches Pydantic → response sane.

- [ ] **Step 1: Test**

```python
# tests/api/test_full_pipeline_e2e.py
"""M2 acceptance: simulated cron run → DB → API read → schema validates."""
from datetime import datetime, UTC
from unittest.mock import patch
import pytest

from alpha_agent.signals.base import SignalScore

pytestmark = pytest.mark.asyncio


def _patch_all():
    targets = ["factor", "technicals", "analyst", "earnings", "news",
               "insider", "options", "premarket", "macro", "calendar"]
    def fake(name):
        def _f(t, a):
            return SignalScore(ticker=t, z=1.5, raw=1.5, confidence=0.85,
                               as_of=a, source=name, error=None)
        return _f
    return [patch(f"alpha_agent.signals.{n}.fetch_signal", side_effect=fake(n))
            for n in targets]


async def test_full_pipeline(client_with_db, applied_db, monkeypatch):
    """1. fast_intraday cron runs → writes daily_signals_fast for AAPL+MSFT.
       2. /api/picks/lean returns those 2 cards sorted by composite.
       3. /api/stock/AAPL returns the full card.
       4. /api/brief/AAPL Lean returns thesis."""
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL", "MSFT"],
    )

    from api.cron.fast_intraday import handler
    patches = _patch_all()
    for p in patches: p.start()
    try:
        cron_result = await handler()
    finally:
        for p in patches: p.stop()
    assert cron_result["ok"] is True
    assert cron_result["rows_written"] == 2

    # 2. /api/picks/lean
    r = client_with_db.get("/api/picks/lean?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body["picks"]) == 2
    assert {p["ticker"] for p in body["picks"]} == {"AAPL", "MSFT"}

    # 3. /api/stock/AAPL
    r = client_with_db.get("/api/stock/AAPL")
    assert r.status_code == 200
    assert r.json()["card"]["ticker"] == "AAPL"

    # 4. /api/brief/AAPL Lean
    r = client_with_db.post("/api/brief/AAPL", json={"mode": "lean"})
    assert r.status_code == 200
    assert "bull" in r.json()["thesis"]


async def test_health_endpoints_after_cron(client_with_db, applied_db, monkeypatch):
    """After cron run, /api/_health/cron should show the run."""
    monkeypatch.setenv("DATABASE_URL", applied_db)
    monkeypatch.setattr(
        "alpha_agent.universe.get_watchlist",
        lambda top_n=100: ["AAPL"],
    )

    from api.cron.fast_intraday import handler
    patches = _patch_all()
    for p in patches: p.start()
    try:
        await handler()
    finally:
        for p in patches: p.stop()

    r = client_with_db.get("/api/_health/cron")
    assert r.status_code == 200
    runs = r.json()["cron"]["fast_intraday"]
    assert len(runs) >= 1
    assert runs[0]["ok"] is True
```

- [ ] **Step 2-3: Run + commit**

```bash
pytest tests/api/test_full_pipeline_e2e.py -v
git add tests/api/test_full_pipeline_e2e.py
git commit -m "test(m2): full-pipeline e2e (cron → DB → API → schema validation)"
```

---

## Self-Review Checklist (before declaring M2 complete)

- [ ] All 14 tasks committed; `git log --oneline | grep -c "(m2)"` ≥ 14
- [ ] `make m2-acceptance` returns 0 (pytest + openapi-check pass)
- [ ] `python -c "from alpha_agent.api.app import create_app; print(sorted(create_app().openapi()['paths']))"` shows 6 paths covering picks/stock/brief/_health/_health/signals/_health/cron
- [ ] No naked `except Exception` in `alpha_agent/api/routes/` or `api/cron/`: `grep -rn "except Exception" alpha_agent/api api/cron`
- [ ] Coverage: `api.routes` ≥ 90%, `orchestrator` ≥ 85%, cron handlers ≥ 80% (cron tests need real DB so coverage easier)
- [ ] `vercel.json` parses: `python -c "import json; json.load(open('vercel.json'))"`
- [ ] `deploy.sh` is executable + has set -euo pipefail at top
- [ ] All cron handlers return `{ok: true|false}` + never raise 5xx (Vercel cron retry storms)

If any item fails, fix in-place + add a regression test.

---

## Hand-off to M3

After M2 acceptance + actual deploy passes:
- M2 → M3 contract: `/api/picks/lean` and `/api/stock/{ticker}` return real RatingCards from Postgres; M3 frontend consumes via the openapi-typescript generated types
- `BriefRequest.mode == "rich"` returns 501; M3 implements BYOK LLM streaming
- `_health/signals` `last_success` field is null in M2; M3 backlog tracks per-signal success timestamps (requires schema additions to either error_log or a new heartbeat table)

**M2 → M3 things to watch:**
- Cron secrets: M2 leaves `Authorization: Bearer $CRON_SECRET` as a TODO. Vercel cron supports `crons[].headers` for this; production deploy needs the secret set.
- The `news` and `insider` signals are placeholder-returning in M1; cron writes will have `confidence=0` for those signals until real fetchers ship in M3 backlog tasks.

---

## Recommended Execution

```
Day 11: T1 (universe) + T2 (batch_runner) + T3 (alert_detector) + T4 (slow_daily)
Day 12: T5 (fast_intraday) + T6 (alert_dispatcher) + tests stabilize
Day 13: T7 (picks) + T8 (stock) + T9 (brief stub)
Day 14: T10 (health) + T11 (vercel + wiring) + T12 (openapi drift)
Day 15: T13 (deploy.sh + acceptance) + T14 (e2e) + actual `vercel deploy --yes` + 三板斧 verify

Critical path: T1 → T4 → T5 → T11. Picks/stock/brief/health (T7-T10) parallel.
```
