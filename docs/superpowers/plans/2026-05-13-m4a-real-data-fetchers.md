# Alpha-Agent v4 · M4a · Real Data Fetchers + TradingView Chart · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three placeholder right-pane blocks (Fundamentals / News / Catalysts) and the placeholder PriceChart on `/stock/[ticker]` with real data sourced from yfinance, so a manual retail trader sees real P/E, real headlines, real next-earnings, and a candlestick chart — not JSON dumps and "M4 placeholder" stubs.

**Architecture:** A single thin yfinance helper module (`yf_helpers.py`) centralizes `Ticker` instance caching + structured field extraction, and three existing signal modules (`factor`, `news`, `earnings`) enrich their `raw` payloads with the data those right-pane blocks need to render. The frontend block components decode the enriched `raw` shapes and render proper UI; the PriceChart calls a new `GET /api/stock/{ticker}/ohlcv` endpoint and renders candlestick + volume via TradingView's `lightweight-charts` library (Apache 2.0, npm install — no key, no upstream service).

**Tech Stack:** Python 3.12 + yfinance (already in deps), FastAPI, asyncpg / Neon Postgres. Frontend Next.js 14 App Router, Tailwind `tm-*` theme tokens (dark/light), TypeScript strict mode, `lightweight-charts` 4.x replacing Recharts on the price surface.

**Spec reference:** `docs/superpowers/specs/2026-05-10-alpha-pivot-phase1-design.md` §3.3 (stock card right pane), §3.4 (Lean vs Rich).

**Backlog source:** `docs/superpowers/plans/2026-05-10-m3-frontend.md` end-of-doc M4 list.

---

## Scope

| In M4a | Out of scope (deferred to M4b) |
|--------|--------------------------------|
| `alpha_agent/signals/yf_helpers.py` — cached Ticker + structured extractors | `/api/alerts/recent` + per-ticker alert timeline (M4b) |
| `factor.raw` enriched with fundamentals dict (P/E, EPS, market cap, dividend yield, profit margin, D/E, beta) | Rich BYOK LLM SSE streaming brief (M4b) |
| `news.raw` populated from `yf.Ticker.news` (headlines + keyword-rule sentiment) | BYOK key UI in /settings (M4b) |
| `earnings.raw` structured (next_date, eps_estimate, eps_actual, surprise_pct) | Playwright E2E test suite (M4b) |
| `GET /api/stock/{ticker}/ohlcv?period=6mo` endpoint | Real news sentiment via LLM (keyword rules suffice for M4a) |
| `FundamentalsBlock.tsx` metric grid (8 KPIs) | SEC EDGAR XBRL ingestion (yfinance is enough for retail user) |
| `NewsBlock.tsx` new component (headline list with publisher + sentiment tag) | Finnhub / Polygon (would need API key — defer) |
| `CatalystsBlock.tsx` real earnings card + macro calendar | Multi-window OHLCV (just 6mo for M4a) |
| `PriceChart.tsx` TradingView lightweight-charts (candlestick + volume + 50-day MA) | Live tick streaming / websocket OHLCV (REST poll sufficient) |
| `make m4a-acceptance` (tsc + lint + next build + pytest signals + curl smoke) | |

**Out of scope confirmation:** Anything that needs an external API key, a new auth flow, an LLM call, or a Playwright runner is M4b. M4a is "right pane stops lying."

---

## File Structure

**New files:**

```
alpha_agent/
├── signals/
│   └── yf_helpers.py                       # cached Ticker + safe extractors (A1)
api/
└── (no new files; ohlcv route added to stock.py)
tests/
├── signals/
│   └── test_yf_helpers.py                  # helper unit tests (A1)
└── api/
    └── test_stock_ohlcv.py                 # /ohlcv endpoint test (C1)

frontend/src/
├── components/
│   └── stock/
│       └── NewsBlock.tsx                   # NEW (D2) — headline list
```

**Modified files:**

```
alpha_agent/
├── signals/
│   ├── factor.py                           # B1 — enrich raw with fundamentals dict
│   ├── news.py                             # B2 — real yfinance Ticker.news
│   └── earnings.py                         # B3 — enrich raw for UI
└── api/routes/
    └── stock.py                            # C1 — add /ohlcv route

tests/signals/
├── test_factor.py                          # B1 — new raw shape assertion
├── test_news.py                            # B2 — yfinance fixture
└── test_earnings.py                        # B3 — new raw shape

frontend/
├── package.json                            # E1 — add lightweight-charts dep
└── src/
    ├── lib/
    │   ├── api/picks.ts                    # A2 — typed raw shapes; ohlcv client (C1)
    │   └── i18n.ts                         # E2 — block label keys (zh/en)
    ├── components/stock/
    │   ├── FundamentalsBlock.tsx           # D1 — metric grid
    │   ├── CatalystsBlock.tsx              # D3 — earnings card + calendar
    │   ├── PriceChart.tsx                  # E1 — TradingView lightweight-charts
    │   └── StockCardLayout.tsx             # E2 — wire NewsBlock in
    └── ...

Makefile                                    # F1 — add m4a-acceptance target
```

Backend net change: +260 LOC (yf_helpers + tests + ohlcv route + signal enrichments).
Frontend net change: +450 LOC (1 new component + 3 rewrites + chart swap + types).

---

## Phase Order

```
A1 → A2  (foundation; parallelisable but trivial)
   ↓
B1, B2, B3 (signal enrichment; independent — can run in parallel as separate subagents)
   ↓
C1  (backend OHLCV — independent of B; can start in parallel with B)
   ↓
D1, D2, D3 (frontend blocks — D1 depends on B1, D2 on B2, D3 on B3)
   ↓
E1 → E2 (chart swap then layout wiring)
   ↓
F1 (acceptance gate)
```

Dependency rule: any task in D requires the matching B task to be merged first (block decodes signal's raw shape). E1 requires C1. F1 requires everything.

---

## Phase A — Foundation

### Task A1: yfinance helpers module + tests

**Why:** Three signal modules and one new API endpoint all need to call yfinance. Today, `earnings.py` re-instantiates `yf.Ticker(ticker)` per call, and the same ticker hit twice (once in fast cron, once on a stock page load) creates two Ticker objects, two HTTP request stacks, two chances to trip yfinance's per-second rate guard. Centralizing here gives us one Ticker per `(ticker, ttl-window)` plus structured `None`-safe extractors so callers never sprinkle `info.get('foo', None) or default`.

**Files:**
- Create: `alpha_agent/signals/yf_helpers.py`
- Test: `tests/signals/test_yf_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/signals/test_yf_helpers.py
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from alpha_agent.signals.yf_helpers import (
    extract_fundamentals,
    extract_news_items,
    extract_next_earnings,
    extract_ohlcv,
    get_ticker,
)


def test_get_ticker_caches_within_ttl():
    """Two calls within TTL should return the same Ticker instance."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_yf.return_value = MagicMock(name="aapl_ticker")
        a = get_ticker("AAPL")
        b = get_ticker("AAPL")
    assert a is b
    assert mock_yf.call_count == 1


def test_extract_fundamentals_full_payload():
    info = {
        "trailingPE": 28.5, "forwardPE": 26.0, "trailingEps": 6.42,
        "marketCap": 3_200_000_000_000, "dividendYield": 0.0043,
        "profitMargins": 0.246, "debtToEquity": 145.3, "beta": 1.21,
    }
    out = extract_fundamentals(info)
    assert out["pe_trailing"] == 28.5
    assert out["pe_forward"] == 26.0
    assert out["eps_ttm"] == 6.42
    assert out["market_cap"] == 3_200_000_000_000
    assert out["dividend_yield"] == 0.0043
    assert out["profit_margin"] == 0.246
    assert out["debt_to_equity"] == 145.3
    assert out["beta"] == 1.21


def test_extract_fundamentals_missing_fields_returns_none():
    """yfinance returns sparse `info` dicts for thinly-traded names; missing
    keys must surface as None (frontend uses ?? '—'), not 0 or NaN."""
    out = extract_fundamentals({"trailingPE": 12.0})
    assert out["pe_trailing"] == 12.0
    assert out["pe_forward"] is None
    assert out["market_cap"] is None


def test_extract_fundamentals_nan_normalised_to_none():
    """Pandas/yfinance occasionally surfaces NaN floats; Postgres JSONB
    rejects literal NaN tokens, so we coerce at the extraction boundary."""
    out = extract_fundamentals({"trailingPE": float("nan"), "beta": 1.1})
    assert out["pe_trailing"] is None
    assert out["beta"] == 1.1


def test_extract_news_items_max_5():
    raw = [
        {"title": f"Headline {i}", "publisher": "Reuters",
         "providerPublishTime": 1700000000 + i * 60, "link": f"https://x/{i}"}
        for i in range(10)
    ]
    out = extract_news_items(raw, limit=5)
    assert len(out) == 5
    assert out[0]["title"] == "Headline 0"
    assert out[0]["publisher"] == "Reuters"
    assert out[0]["published_at"].startswith("2023")
    assert out[0]["sentiment"] in ("pos", "neg", "neu")


def test_extract_news_items_sentiment_keyword_classifier():
    out = extract_news_items(
        [
            {"title": "Apple beats Q3 earnings, raises guidance",
             "publisher": "WSJ", "providerPublishTime": 1700000000, "link": "x"},
            {"title": "Stock plunges on weak iPhone sales",
             "publisher": "Bloomberg", "providerPublishTime": 1700000000, "link": "y"},
            {"title": "Apple announces new product launch",
             "publisher": "Reuters", "providerPublishTime": 1700000000, "link": "z"},
        ],
        limit=5,
    )
    assert out[0]["sentiment"] == "pos"  # "beats" + "raises"
    assert out[1]["sentiment"] == "neg"  # "plunges" + "weak"
    assert out[2]["sentiment"] == "neu"


def test_extract_next_earnings_when_calendar_has_entry():
    cal = pd.DataFrame(
        {"Earnings Date": [pd.Timestamp("2026-07-31", tz="UTC")],
         "EPS Estimate": [1.45], "Revenue Estimate": [120_000_000_000]}
    )
    out = extract_next_earnings(cal, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out["next_date"] == "2026-07-31"
    assert out["days_until"] == 79
    assert out["eps_estimate"] == 1.45
    assert out["revenue_estimate"] == 120_000_000_000


def test_extract_next_earnings_when_no_entry_returns_none_fields():
    out = extract_next_earnings(None, as_of=datetime(2026, 5, 13, tzinfo=UTC))
    assert out == {"next_date": None, "days_until": None,
                   "eps_estimate": None, "revenue_estimate": None}


def test_extract_ohlcv_shapes_pandas_to_records():
    df = pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0],
         "Low": [99.0, 100.5], "Close": [101.5, 102.5],
         "Volume": [1_000_000, 1_100_000]},
        index=pd.DatetimeIndex(["2026-05-12", "2026-05-13"]),
    )
    out = extract_ohlcv(df)
    assert len(out) == 2
    assert out[0] == {"date": "2026-05-12", "open": 100.0, "high": 102.0,
                      "low": 99.0, "close": 101.5, "volume": 1_000_000}


def test_extract_ohlcv_empty_df_returns_empty_list():
    out = extract_ohlcv(pd.DataFrame())
    assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent
pytest tests/signals/test_yf_helpers.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'alpha_agent.signals.yf_helpers'`.

- [ ] **Step 3: Write the implementation**

```python
# alpha_agent/signals/yf_helpers.py
"""Centralized yfinance access with Ticker caching + structured extractors.

Why this module exists:
- yfinance creates a fresh HTTP session per Ticker instance. Without caching,
  every signal module re-creates a Ticker for the same symbol, multiplying
  the request count under cron load.
- `info` dicts are sparse for thinly-traded names. Returning `None` for any
  missing field (rather than a default `0` or `nan`) lets frontend
  components fall back to "—" cleanly + keeps Neon JSONB happy (NaN tokens
  are rejected by Postgres' JSON parser).
- All extractors take pre-fetched data (dicts / DataFrames) so the actual
  network call lives in one place (`get_ticker`) and tests don't need a
  network mock for every signal module.
"""
from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf

# 10-minute TTL keeps Ticker instances reusable across one cron cycle without
# accumulating stale state across days.
_TTL_SECONDS = 600
_cache: dict[str, tuple[float, yf.Ticker]] = {}

_POSITIVE_WORDS = {
    "beats", "beat", "raises", "raise", "surge", "surges", "soars", "rally",
    "upgrade", "strong", "record", "boost", "gains", "outperform",
}
_NEGATIVE_WORDS = {
    "misses", "miss", "cuts", "cut", "plunges", "plunge", "drops", "fall",
    "downgrade", "weak", "concern", "loss", "lawsuit", "probe", "investigation",
}


def get_ticker(symbol: str) -> yf.Ticker:
    """Cached yf.Ticker. Same symbol within TTL → same instance."""
    now = time.time()
    cached = _cache.get(symbol)
    if cached is not None and (now - cached[0]) < _TTL_SECONDS:
        return cached[1]
    t = yf.Ticker(symbol)
    _cache[symbol] = (now, t)
    return t


def _safe_float(v: Any) -> float | None:
    """yfinance returns mixed int/float/NaN/None. Normalize to float|None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def extract_fundamentals(info: dict) -> dict[str, float | None]:
    """Pluck the 8 retail-relevant metrics from yfinance Ticker.info.
    Keys aligned with frontend FundamentalsBlock display order."""
    return {
        "pe_trailing": _safe_float(info.get("trailingPE")),
        "pe_forward": _safe_float(info.get("forwardPE")),
        "eps_ttm": _safe_float(info.get("trailingEps")),
        "market_cap": _safe_float(info.get("marketCap")),
        "dividend_yield": _safe_float(info.get("dividendYield")),
        "profit_margin": _safe_float(info.get("profitMargins")),
        "debt_to_equity": _safe_float(info.get("debtToEquity")),
        "beta": _safe_float(info.get("beta")),
    }


def _classify_sentiment(title: str) -> str:
    """Keyword-rule sentiment. M4a does not call an LLM here; M4b can replace
    this with a Rich-brief enrichment step that scores headlines via the user's
    BYOK key."""
    lower = title.lower()
    pos_hits = sum(1 for w in _POSITIVE_WORDS if w in lower)
    neg_hits = sum(1 for w in _NEGATIVE_WORDS if w in lower)
    if pos_hits > neg_hits:
        return "pos"
    if neg_hits > pos_hits:
        return "neg"
    return "neu"


def extract_news_items(raw: list[dict], limit: int = 5) -> list[dict]:
    """yfinance Ticker.news → frontend-renderable list. Returns at most
    `limit` items (most-recent first per yfinance default order)."""
    out: list[dict] = []
    for item in raw[:limit]:
        title = item.get("title") or ""
        ts_unix = item.get("providerPublishTime")
        try:
            ts_iso = datetime.fromtimestamp(int(ts_unix), tz=UTC).isoformat() if ts_unix else ""
        except (TypeError, ValueError):
            ts_iso = ""
        out.append({
            "title": title,
            "publisher": item.get("publisher") or "",
            "published_at": ts_iso,
            "link": item.get("link") or "",
            "sentiment": _classify_sentiment(title),
        })
    return out


def extract_next_earnings(
    calendar: pd.DataFrame | None, *, as_of: datetime
) -> dict[str, Any]:
    """Decode `yf.Ticker.calendar` (a DataFrame) into a structured upcoming
    earnings block. Returns all-None fields if no calendar entry exists."""
    none_payload: dict[str, Any] = {
        "next_date": None, "days_until": None,
        "eps_estimate": None, "revenue_estimate": None,
    }
    if calendar is None or len(calendar) == 0:
        return none_payload
    try:
        date = pd.to_datetime(calendar["Earnings Date"].iloc[0])
        if date.tzinfo is None:
            date = date.tz_localize("UTC")
        days = (date - as_of).days
        return {
            "next_date": date.strftime("%Y-%m-%d"),
            "days_until": int(days),
            "eps_estimate": _safe_float(calendar["EPS Estimate"].iloc[0])
                if "EPS Estimate" in calendar else None,
            "revenue_estimate": _safe_float(calendar["Revenue Estimate"].iloc[0])
                if "Revenue Estimate" in calendar else None,
        }
    except (KeyError, IndexError, ValueError):
        return none_payload


def extract_ohlcv(df: pd.DataFrame) -> list[dict]:
    """yfinance.Ticker.history() DataFrame → list of {date, ohlcv} dicts
    serialisable to JSON for the chart endpoint."""
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for ts, row in df.iterrows():
        out.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": _safe_float(row.get("Open")) or 0.0,
            "high": _safe_float(row.get("High")) or 0.0,
            "low": _safe_float(row.get("Low")) or 0.0,
            "close": _safe_float(row.get("Close")) or 0.0,
            "volume": int(_safe_float(row.get("Volume")) or 0),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/signals/test_yf_helpers.py -v
```

Expected: PASS — 10 tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/yf_helpers.py tests/signals/test_yf_helpers.py
git commit -m "feat(signals): yf_helpers module — cached Ticker + structured extractors

Centralizes yfinance access for M4a real-data signal modules:
- get_ticker() caches yf.Ticker per symbol on a 10min TTL
- extract_fundamentals/news/next_earnings/ohlcv take pre-fetched data
  and normalize NaN/missing → None (Postgres JSONB safe)
- _classify_sentiment is a keyword-rule placeholder; M4b can swap for
  an LLM-backed scorer using the user's BYOK key."
```

---

### Task A2: Frontend typed raw shapes

**Why:** `BreakdownEntry.raw` is `unknown` today, which is honest but means every block component does an unsafe cast. M4a is adding three new structured shapes (factor fundamentals, news headlines, earnings forecast). Defining them once in `picks.ts` gives every block a single source of truth + breaks any future shape drift at the type checker, not at runtime.

**Files:**
- Modify: `frontend/src/lib/api/picks.ts`

- [ ] **Step 1: Read the current file**

```bash
cat frontend/src/lib/api/picks.ts
```

Note the existing `BreakdownEntry.raw: unknown` (line 13). We're keeping that as the wire shape and adding *expectation* types below it that block components cast to.

- [ ] **Step 2: Add type definitions**

Replace the bottom of `frontend/src/lib/api/picks.ts` (after the existing `postBrief` function) with the following additions. Do NOT modify `BreakdownEntry` itself — `raw: unknown` is the truthful contract.

```typescript
// frontend/src/lib/api/picks.ts (additions — append after postBrief)

/**
 * Expected shape of `breakdown[signal="factor"].raw` after M4a. Block
 * components cast via `raw as FactorRaw | null`; legacy rows from before
 * the signal enrichment may still have raw=float, so the cast is unsafe —
 * the block must check `typeof raw === "object" && raw !== null` first.
 */
export interface FundamentalsData {
  pe_trailing: number | null;
  pe_forward: number | null;
  eps_ttm: number | null;
  market_cap: number | null;
  dividend_yield: number | null;
  profit_margin: number | null;
  debt_to_equity: number | null;
  beta: number | null;
}

export interface FactorRaw {
  z: number;
  fundamentals: FundamentalsData | null;
}

export interface NewsItem {
  title: string;
  publisher: string;
  published_at: string; // ISO 8601
  link: string;
  sentiment: "pos" | "neg" | "neu";
}

export interface NewsRaw {
  n: number;
  mean_sent: number;
  headlines: NewsItem[];
}

export interface EarningsRaw {
  surprise_pct: number | null;
  days_to_earnings: number | null;
  next_date: string | null; // YYYY-MM-DD
  days_until: number | null;
  eps_estimate: number | null;
  revenue_estimate: number | null;
}

export interface OhlcvBar {
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OhlcvResponse {
  ticker: string;
  period: string;
  bars: OhlcvBar[];
}

export const fetchOhlcv = (ticker: string, period = "6mo") =>
  apiGet<OhlcvResponse>(
    `/api/stock/${ticker.toUpperCase()}/ohlcv?period=${period}`,
  );
```

- [ ] **Step 3: Verify type check passes**

```bash
cd frontend && npx tsc --noEmit
```

Expected: silent (no output) — clean compile.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api/picks.ts
git commit -m "feat(types): typed raw shapes for M4a signal enrichments

Adds FactorRaw / NewsRaw / EarningsRaw / OhlcvResponse interfaces +
fetchOhlcv() client helper. BreakdownEntry.raw stays 'unknown' as the
wire contract; block components cast at decode time and check
typeof === 'object' to tolerate pre-M4a rows (where raw was a float)."
```

---

## Phase B — Backend signal enrichment

### Task B1: factor.py — enrich raw with fundamentals dict

**Why:** `factor.raw` is currently just the z-score float. FundamentalsBlock has nothing to render but the score, hence the JSON-dump placeholder. After this task, every fast-intraday refresh writes the 8 retail KPIs to `daily_signals_fast.breakdown` so the stock card can show real P/E + market cap without any extra fetch on the request path.

**Files:**
- Modify: `alpha_agent/signals/factor.py`
- Modify: `tests/signals/test_factor.py`

- [ ] **Step 1: Update the existing test**

Replace the body of `tests/signals/test_factor.py` with:

```python
# tests/signals/test_factor.py
from datetime import UTC, datetime
from unittest.mock import patch

from alpha_agent.signals.factor import fetch_signal


def test_factor_signal_happy_path():
    fake_scores = {"AAPL": 1.8, "MSFT": 0.5, "GOOG": -1.2}
    fake_info = {
        "trailingPE": 28.5, "forwardPE": 26.0, "trailingEps": 6.42,
        "marketCap": 3_200_000_000_000, "dividendYield": 0.0043,
        "profitMargins": 0.246, "debtToEquity": 145.3, "beta": 1.21,
    }
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores), \
         patch("alpha_agent.signals.factor._fetch_info_for",
               return_value=fake_info):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert -3.0 <= out["z"] <= 3.0
    # raw is now a dict, not a float — UI block consumes raw["fundamentals"]
    assert isinstance(out["raw"], dict)
    assert out["raw"]["z"] == 1.8
    assert out["raw"]["fundamentals"]["pe_trailing"] == 28.5
    assert out["raw"]["fundamentals"]["market_cap"] == 3_200_000_000_000
    assert out["confidence"] > 0.5
    assert out["source"] == "factor_engine"


def test_factor_signal_unknown_ticker_returns_zero_confidence():
    fake_scores = {"MSFT": 0.5}
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores):
        out = fetch_signal("UNKN", datetime.now(UTC))
    assert out["z"] == 0.0
    assert out["confidence"] == 0.0
    assert out["error"] is not None


def test_factor_signal_fundamentals_unavailable_keeps_z():
    """If yfinance info fetch fails, we still emit the z score with
    fundamentals=None — the rating logic doesn't depend on UI fields."""
    fake_scores = {"AAPL": 1.8}
    with patch("alpha_agent.signals.factor._evaluate_for_universe",
               return_value=fake_scores), \
         patch("alpha_agent.signals.factor._fetch_info_for",
               side_effect=KeyError("info missing")):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] != 0.0  # z survives even though info fetch failed
    assert out["raw"]["fundamentals"] is None
```

- [ ] **Step 2: Run the test (expect failure)**

```bash
pytest tests/signals/test_factor.py -v
```

Expected: 2 FAIL (happy_path + fundamentals_unavailable) — `_fetch_info_for` doesn't exist; `raw` is still a float.

- [ ] **Step 3: Update factor.py**

Replace `alpha_agent/signals/factor.py` with:

```python
"""Composite factor signal: leverages the existing v3 factor engine.

The "value" we expose as z is the cross-sectional z-score of the
default composite factor (Pure-Alpha pick from spec §3.1: weight 0.30).

M4a: raw payload upgraded from `float` (just the z score) to
`{z: float, fundamentals: dict | None}` so FundamentalsBlock has real
P/E, market cap, dividend yield etc. to render without a separate
per-page fetch. yfinance is the data source (already in deps, no key).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_fundamentals, get_ticker

DEFAULT_FACTOR_EXPR = "rank(ts_mean(returns, 12)) - rank(ts_std(returns, 60))"


def _evaluate_for_universe(as_of: datetime, expr: str = DEFAULT_FACTOR_EXPR) -> dict[str, float]:
    """Returns {ticker: z_score} on as_of's date row.
    Wraps factor_engine.kernel.evaluate_cross_section.
    """
    from alpha_agent.factor_engine.factor_backtest import _load_panel
    from alpha_agent.factor_engine.kernel import evaluate_cross_section
    from alpha_agent.core.types import FactorSpec

    panel = _load_panel()
    spec = FactorSpec(expression=expr)
    scores = evaluate_cross_section(panel, spec, as_of_index=-1)
    arr = np.array(list(scores.values()), dtype=float)
    mu, sigma = np.nanmean(arr), np.nanstd(arr)
    if sigma == 0 or np.isnan(sigma):
        return {t: 0.0 for t in scores}
    return {t: float(np.clip((v - mu) / sigma, -3.0, 3.0)) for t, v in scores.items()}


def _fetch_info_for(ticker: str) -> dict:
    """Indirection so tests can patch the yfinance call without mocking
    the whole `get_ticker` chain."""
    return get_ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    scores = _evaluate_for_universe(as_of)
    if ticker not in scores:
        raise KeyError(f"{ticker} not in panel universe")
    z = scores[ticker]

    # Best-effort fundamentals enrichment. If yfinance is rate-limited or
    # the ticker has sparse `info` (small caps), we still return the z;
    # the UI block falls back to "—" cells.
    try:
        info = _fetch_info_for(ticker)
        fundamentals = extract_fundamentals(info)
    except (KeyError, ValueError, ConnectionError, TimeoutError):
        fundamentals = None

    return SignalScore(
        ticker=ticker, z=z,
        raw={"z": z, "fundamentals": fundamentals},
        confidence=0.95, as_of=as_of, source="factor_engine", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="factor_engine")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/signals/test_factor.py -v
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/factor.py tests/signals/test_factor.py
git commit -m "feat(signals): factor.raw carries fundamentals dict (M4a B1)

raw was just the z-score float — FundamentalsBlock had nothing to render
but JSON-dump it. Now raw is {z, fundamentals: {pe_trailing, pe_forward,
eps_ttm, market_cap, dividend_yield, profit_margin, debt_to_equity,
beta}} pulled from yfinance.Ticker.info via yf_helpers.

Fundamentals fetch is best-effort: if yfinance is rate-limited or the
info dict is sparse (small caps), fundamentals=None and the UI falls
back to '—' cells. The z score is unaffected."
```

---

### Task B2: news.py — real yfinance Ticker.news

**Why:** `_search_recent` returns `[]` — every NewsBlock currently shows "—". Replacing the stub with `yf.Ticker.news` gives real headlines + publisher + timestamp without an API key. A keyword sentiment classifier (already in yf_helpers) marks each headline `pos`/`neg`/`neu` so the existing `mean_sent → z` math still works.

**Files:**
- Modify: `alpha_agent/signals/news.py`
- Modify: `tests/signals/test_news.py`

- [ ] **Step 1: Update the test**

Replace `tests/signals/test_news.py` with:

```python
# tests/signals/test_news.py
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from alpha_agent.signals.news import fetch_signal


def _ticker_mock(news_payload):
    m = MagicMock()
    m.news = news_payload
    return m


def test_positive_news_yields_positive_z():
    payload = [
        {"title": "Apple beats Q3 earnings, raises guidance",
         "publisher": "WSJ", "providerPublishTime": 1700000000, "link": "x"},
        {"title": "Strong iPhone sales surge",
         "publisher": "Bloomberg", "providerPublishTime": 1700000100, "link": "y"},
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["z"] > 0
    assert out["raw"]["n"] == 2
    assert out["raw"]["headlines"][0]["sentiment"] == "pos"
    assert out["raw"]["headlines"][0]["publisher"] == "WSJ"


def test_negative_news_yields_negative_z():
    payload = [
        {"title": "Stock plunges on weak iPhone sales",
         "publisher": "Reuters", "providerPublishTime": 1700000000, "link": "x"},
        {"title": "Apple misses analyst estimates",
         "publisher": "FT", "providerPublishTime": 1700000100, "link": "y"},
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["z"] < 0


def test_no_news_low_confidence():
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock([])):
        out = fetch_signal("XYZ", datetime(2026, 5, 13, tzinfo=UTC))
    assert out["confidence"] < 0.4
    assert out["raw"]["n"] == 0
    assert out["raw"]["headlines"] == []


def test_caps_headlines_at_five():
    payload = [
        {"title": f"Headline {i}", "publisher": "Reuters",
         "providerPublishTime": 1700000000 + i * 60, "link": f"x{i}"}
        for i in range(10)
    ]
    with patch("alpha_agent.signals.news.get_ticker",
               return_value=_ticker_mock(payload)):
        out = fetch_signal("AAPL", datetime(2026, 5, 13, tzinfo=UTC))
    assert len(out["raw"]["headlines"]) == 5
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest tests/signals/test_news.py -v
```

Expected: FAIL — `news.py` still uses the empty `_search_recent` stub; nothing references `get_ticker`.

- [ ] **Step 3: Rewrite news.py**

Replace `alpha_agent/signals/news.py` with:

```python
"""News-flow signal via yfinance Ticker.news (free, no API key).

Each headline gets a keyword-rule sentiment in {pos, neg, neu}; we average
mapped to [-1, +1] then scale by a tanh count-bonus so a wall of 1 positive
headline doesn't outweigh 5 mixed ones. Spec §3.1 weight 0.10.

M4a: replaces the M1 `_search_recent` stub (returned []) with real headlines
and keyword sentiment. M4b can swap _classify_sentiment for an LLM-backed
scorer that uses the user's BYOK key (in yf_helpers._classify_sentiment).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_news_items, get_ticker

_SENT_TO_FLOAT = {"pos": 1.0, "neg": -1.0, "neu": 0.0}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    raw_news = get_ticker(ticker).news or []
    items = extract_news_items(raw_news, limit=5)

    if not items:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"n": 0, "mean_sent": 0.0, "headlines": []},
            confidence=0.3, as_of=as_of, source="yfinance",
            error="no news in last fetch window",
        )

    sentiments = [_SENT_TO_FLOAT[it["sentiment"]] for it in items]
    mean_sent = float(np.mean(sentiments))
    count_bonus = float(np.tanh(len(items) / 5))
    z = float(np.clip(mean_sent * 2 * count_bonus, -3.0, 3.0))

    return SignalScore(
        ticker=ticker, z=z,
        raw={"n": len(items), "mean_sent": mean_sent, "headlines": items},
        confidence=0.65, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/signals/test_news.py -v
```

Expected: PASS — 4 tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/news.py tests/signals/test_news.py
git commit -m "feat(signals): real yfinance headlines for news.raw (M4a B2)

Replaces M1 _search_recent stub (returned []) with yf.Ticker.news +
keyword-rule sentiment via yf_helpers.extract_news_items. raw shape:
{n, mean_sent, headlines: [{title, publisher, published_at, link,
sentiment}]} — caps at 5 headlines, most recent first.

NewsBlock.tsx (D2) consumes raw['headlines'] directly."
```

---

### Task B3: earnings.py — structured upcoming earnings

**Why:** `earnings.raw` already has `surprise_pct` and `days_to_earnings` (good), but CatalystsBlock can't show "next earnings: 2026-07-31, EPS estimate 1.45" without `next_date` + `eps_estimate` on the raw payload. Adding those via the existing `yf.Ticker.calendar` data path.

**Files:**
- Modify: `alpha_agent/signals/earnings.py`
- Modify: `tests/signals/test_earnings.py`

- [ ] **Step 1: Update the test**

Replace `tests/signals/test_earnings.py` with:

```python
# tests/signals/test_earnings.py
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from alpha_agent.signals.earnings import fetch_signal


def _ticker_mock(info=None, earnings_dates_df=None, calendar_df=None):
    m = MagicMock()
    m.info = info or {}
    m.earnings_dates = earnings_dates_df
    m.calendar = calendar_df
    return m


def test_recent_beat_yields_positive_z():
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    edates = pd.DataFrame(
        {"Reported EPS": [1.20], "EPS Estimate": [1.00]},
        index=pd.DatetimeIndex([datetime.now(UTC) - timedelta(days=5)]),
    )
    cal = pd.DataFrame(
        {"Earnings Date": [pd.Timestamp("2026-07-31", tz="UTC")],
         "EPS Estimate": [1.45], "Revenue Estimate": [120_000_000_000]}
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, cal)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["z"] > 0
    assert out["raw"]["surprise_pct"] > 0
    # New structured upcoming-earnings fields
    assert out["raw"]["next_date"] == "2026-07-31"
    assert out["raw"]["eps_estimate"] == 1.45
    assert out["raw"]["revenue_estimate"] == 120_000_000_000


def test_no_data_low_confidence():
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock()):
        out = fetch_signal("XYZ", datetime.now(UTC))
    assert out["confidence"] < 0.4


def test_no_upcoming_calendar_returns_null_fields():
    """If yf.Ticker.calendar is None but earnings_dates has a row,
    surprise_pct still populates while next_date/eps_estimate stay None."""
    info = {"epsActual": 1.20, "epsEstimate": 1.00}
    edates = pd.DataFrame(
        {"Reported EPS": [1.20], "EPS Estimate": [1.00]},
        index=pd.DatetimeIndex([datetime.now(UTC) - timedelta(days=5)]),
    )
    with patch("alpha_agent.signals.earnings.get_ticker",
               return_value=_ticker_mock(info, edates, None)):
        out = fetch_signal("AAPL", datetime.now(UTC))
    assert out["raw"]["surprise_pct"] > 0
    assert out["raw"]["next_date"] is None
    assert out["raw"]["eps_estimate"] is None
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest tests/signals/test_earnings.py -v
```

Expected: FAIL — `next_date` / `eps_estimate` keys don't exist on raw.

- [ ] **Step 3: Rewrite earnings.py**

Replace `alpha_agent/signals/earnings.py` with:

```python
# alpha_agent/signals/earnings.py
"""Earnings catalyst signal. Two components contribute to z:
- Proximity: |days_until_or_since_earnings|; sigmoid -> [0, 1]
- Surprise: (actual - estimate) / |estimate|; +-50% saturates.

M4a: raw payload extended with structured upcoming-earnings fields
(next_date, eps_estimate, revenue_estimate) so CatalystsBlock can render
a real earnings card without a separate fetch.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.yf_helpers import extract_next_earnings, get_ticker


def _fetch_info(ticker: str) -> tuple[dict, object]:
    """Returns (info_dict, ticker_for_calendar). Keeping the legacy
    signature so existing tests that patch _fetch_info don't break — but
    now we also surface the Ticker for calendar extraction."""
    t = get_ticker(ticker)
    info = dict(t.info or {})
    edates = getattr(t, "earnings_dates", None)
    if edates is not None and not edates.empty:
        info["epsActual"] = edates["Reported EPS"].iloc[0]
        info["epsEstimate"] = edates["EPS Estimate"].iloc[0]
        info["earningsDate"] = [edates.index[0]]
    return info, t


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info, ticker_obj = _fetch_info(ticker)
    actual = info.get("epsActual")
    est = info.get("epsEstimate")
    earn_dates = info.get("earningsDate") or []

    # Upcoming earnings (always try, even when surprise data is missing).
    upcoming = extract_next_earnings(getattr(ticker_obj, "calendar", None), as_of=as_of)

    if not earn_dates or actual is None or est is None or est == 0:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={
                "surprise_pct": None, "days_to_earnings": None,
                "next_date": upcoming["next_date"],
                "days_until": upcoming["days_until"],
                "eps_estimate": upcoming["eps_estimate"],
                "revenue_estimate": upcoming["revenue_estimate"],
            },
            confidence=0.3, as_of=as_of, source="yfinance",
            error="missing earnings",
        )

    surprise = (actual - est) / abs(est)
    surprise_z = float(np.clip(surprise / 0.20, -2.0, 2.0))
    days = abs((earn_dates[0].replace(tzinfo=as_of.tzinfo) - as_of).days)
    proximity_w = float(np.exp(-days / 14))
    z = float(np.clip(surprise_z * proximity_w, -3.0, 3.0))

    return SignalScore(
        ticker=ticker, z=z,
        raw={
            "surprise_pct": surprise * 100,
            "days_to_earnings": days,
            "next_date": upcoming["next_date"],
            "days_until": upcoming["days_until"],
            "eps_estimate": upcoming["eps_estimate"],
            "revenue_estimate": upcoming["revenue_estimate"],
        },
        confidence=0.75, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/signals/test_earnings.py -v
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/signals/earnings.py tests/signals/test_earnings.py
git commit -m "feat(signals): earnings.raw carries upcoming earnings card (M4a B3)

Adds next_date / days_until / eps_estimate / revenue_estimate fields
sourced from yf.Ticker.calendar via yf_helpers.extract_next_earnings.
Existing surprise_pct / days_to_earnings still populate when info has
the prior-quarter actual+estimate; both contribute independently so
CatalystsBlock can render today's card even on quiet weeks."
```

---

## Phase C — Backend OHLCV endpoint

### Task C1: GET /api/stock/{ticker}/ohlcv

**Why:** TradingView lightweight-charts needs an array of `{date, open, high, low, close, volume}` bars. Putting this on `/api/stock/{ticker}` would bloat the rating-card payload (180 days × 6 fields ≈ 10KB per stock); a separate endpoint lets the frontend lazy-load chart data while the rating renders immediately.

**Files:**
- Modify: `alpha_agent/api/routes/stock.py`
- Create: `tests/api/test_stock_ohlcv.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_stock_ohlcv.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.index import app
    return TestClient(app)


def _ohlcv_df():
    return pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0],
         "Low": [99.0, 100.5], "Close": [101.5, 102.5],
         "Volume": [1_000_000, 1_100_000]},
        index=pd.DatetimeIndex(["2026-05-12", "2026-05-13"]),
    )


def test_ohlcv_returns_bars(client):
    m = MagicMock()
    m.history.return_value = _ohlcv_df()
    with patch("alpha_agent.api.routes.stock.get_ticker", return_value=m):
        r = client.get("/api/stock/AAPL/ohlcv?period=6mo")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["period"] == "6mo"
    assert len(body["bars"]) == 2
    assert body["bars"][0] == {
        "date": "2026-05-12", "open": 100.0, "high": 102.0,
        "low": 99.0, "close": 101.5, "volume": 1_000_000,
    }


def test_ohlcv_empty_returns_empty_bars(client):
    m = MagicMock()
    m.history.return_value = pd.DataFrame()
    with patch("alpha_agent.api.routes.stock.get_ticker", return_value=m):
        r = client.get("/api/stock/UNKN/ohlcv")
    assert r.status_code == 200
    assert r.json()["bars"] == []


def test_ohlcv_invalid_period_rejected(client):
    """Pydantic Query validation should reject periods outside the allowed set."""
    r = client.get("/api/stock/AAPL/ohlcv?period=99y")
    assert r.status_code == 422
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest tests/api/test_stock_ohlcv.py -v
```

Expected: FAIL — endpoint doesn't exist (404).

- [ ] **Step 3: Add the imports + route**

First, modify the import block at the top of `alpha_agent/api/routes/stock.py`. The file already has `from pydantic import BaseModel` (line 13) and `from fastapi import APIRouter, HTTPException, Path`. Add two lines:

```python
# After the existing "from datetime import ..." import block, add:
from typing import Literal

# After "from alpha_agent.api.dependencies import get_db_pool", add:
from alpha_agent.signals.yf_helpers import extract_ohlcv, get_ticker
```

Then append the route definition + Pydantic models at the END of `stock.py` (after the existing `stock_card` function):

```python
class OhlcvBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class OhlcvResponse(BaseModel):
    ticker: str
    period: str
    bars: list[OhlcvBar]


# yfinance period vocabulary: 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max.
# Restrict to the ones the chart UI offers to avoid surprises.
_AllowedPeriod = Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"]


@router.get("/{ticker}/ohlcv", response_model=OhlcvResponse)
async def stock_ohlcv(
    ticker: str,
    period: _AllowedPeriod = "6mo",
) -> OhlcvResponse:
    """Lazy OHLCV feed for the price chart. Cache headers in middleware
    (or here, future) — for now relies on FE-side staleness."""
    ticker = ticker.upper()
    df = get_ticker(ticker).history(period=period)
    bars = extract_ohlcv(df)
    return OhlcvResponse(
        ticker=ticker,
        period=period,
        bars=[OhlcvBar(**b) for b in bars],
    )
```

- [ ] **Step 4: Run test to verify pass**

```bash
pytest tests/api/test_stock_ohlcv.py -v
```

Expected: PASS — 3 tests green.

- [ ] **Step 5: Commit**

```bash
git add alpha_agent/api/routes/stock.py tests/api/test_stock_ohlcv.py
git commit -m "feat(api): GET /api/stock/{ticker}/ohlcv (M4a C1)

Lazy OHLCV feed for TradingView lightweight-charts. Period vocabulary
restricted to {1mo,3mo,6mo,1y,2y,5y} via Literal Query type so the
chart UI's dropdown maps 1:1 to validated server inputs.

Bars are normalized through yf_helpers.extract_ohlcv (NaN-safe, JSON
serializable). No DB hit on the request path — yfinance.Ticker.history()
is cached per Ticker instance, and the Ticker itself is TTL-cached in
yf_helpers."
```

---

## Phase D — Frontend block components

### Task D1: FundamentalsBlock — metric grid

**Why:** Currently dumps `factor.raw` as JSON. After this task it renders an 8-cell grid: P/E (T), P/E (F), EPS, Market Cap, Div Yield, Profit Margin, D/E, Beta — with `"—"` placeholders for missing fields. Uses `tm-*` tokens so it works in light + dark.

**Files:**
- Modify: `frontend/src/components/stock/FundamentalsBlock.tsx`
- Modify: `frontend/src/lib/i18n.ts` (zh + en blocks — labels only)

- [ ] **Step 1: Add i18n keys**

Locate the `picks.lastrun` key block in `frontend/src/lib/i18n.ts` (in BOTH the zh block ~line 460 and the en block ~line 924). Add the following keys immediately after `picks.lastrun`:

```typescript
// zh block (after "picks.lastrun")
    "fundamentals.title": "基本面",
    "fundamentals.pe_trailing": "TTM 市盈率",
    "fundamentals.pe_forward": "前瞻市盈率",
    "fundamentals.eps_ttm": "每股收益 (TTM)",
    "fundamentals.market_cap": "市值",
    "fundamentals.dividend_yield": "股息率",
    "fundamentals.profit_margin": "净利率",
    "fundamentals.debt_to_equity": "负债权益比",
    "fundamentals.beta": "Beta",
    "fundamentals.empty": "暂无基本面数据",
```

```typescript
// en block (after "picks.lastrun")
    "fundamentals.title": "Fundamentals",
    "fundamentals.pe_trailing": "P/E (TTM)",
    "fundamentals.pe_forward": "P/E (Fwd)",
    "fundamentals.eps_ttm": "EPS (TTM)",
    "fundamentals.market_cap": "Market Cap",
    "fundamentals.dividend_yield": "Div Yield",
    "fundamentals.profit_margin": "Profit Margin",
    "fundamentals.debt_to_equity": "D/E",
    "fundamentals.beta": "Beta",
    "fundamentals.empty": "No fundamentals data available",
```

- [ ] **Step 2: Replace FundamentalsBlock.tsx**

Replace `frontend/src/components/stock/FundamentalsBlock.tsx` entirely with:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { RatingCard, FactorRaw, FundamentalsData } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function decodeFactorRaw(raw: unknown): FundamentalsData | null {
  // Pre-M4a rows had factor.raw = float (the z score). Tolerate that by
  // checking shape before reading nested fields.
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Partial<FactorRaw>;
  return obj.fundamentals ?? null;
}

function fmtNumber(v: number | null, digits = 2): string {
  if (v == null) return "—";
  return v.toFixed(digits);
}

function fmtPercent(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtCurrency(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

export default function FundamentalsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const factor = card.breakdown.find((b) => b.signal === "factor");
  const fund = decodeFactorRaw(factor?.raw);

  if (!fund) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "fundamentals.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "fundamentals.empty")}</p>
      </section>
    );
  }

  const cells: { labelKey: Parameters<typeof t>[1]; value: string }[] = [
    { labelKey: "fundamentals.pe_trailing", value: fmtNumber(fund.pe_trailing) },
    { labelKey: "fundamentals.pe_forward", value: fmtNumber(fund.pe_forward) },
    { labelKey: "fundamentals.eps_ttm", value: fmtNumber(fund.eps_ttm) },
    { labelKey: "fundamentals.market_cap", value: fmtCurrency(fund.market_cap) },
    { labelKey: "fundamentals.dividend_yield", value: fmtPercent(fund.dividend_yield) },
    { labelKey: "fundamentals.profit_margin", value: fmtPercent(fund.profit_margin) },
    { labelKey: "fundamentals.debt_to_equity", value: fmtNumber(fund.debt_to_equity, 1) },
    { labelKey: "fundamentals.beta", value: fmtNumber(fund.beta) },
  ];

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "fundamentals.title")}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cells.map((c) => (
          <div key={c.labelKey} className="space-y-0.5">
            <div className="text-xs text-tm-muted uppercase tracking-wide">
              {t(locale, c.labelKey)}
            </div>
            <div className="text-base font-mono text-tm-fg">{c.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Verify type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

Expected: silent tsc + `✔ No ESLint warnings or errors`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stock/FundamentalsBlock.tsx frontend/src/lib/i18n.ts
git commit -m "feat(stock): FundamentalsBlock renders real KPI grid (M4a D1)

Reads factor.raw.fundamentals (populated by B1) and renders 8 metric
cells in a 2x4 grid: P/E (T/Fwd), EPS, Market Cap, Div Yield, Profit
Margin, D/E, Beta. Missing values show '—'.

Tolerates pre-M4a rows where factor.raw was just a float by checking
typeof === 'object' before destructuring. i18n keys added to both
zh + en blocks (9 new keys × 2 locales)."
```

---

### Task D2: NewsBlock — new component for headlines

**Why:** News currently shares CatalystsBlock and shows as one JSON-dump line. M4a splits it into its own section: 5 headlines × {publisher chip + relative time + sentiment dot + clickable title link}.

**Files:**
- Create: `frontend/src/components/stock/NewsBlock.tsx`
- Modify: `frontend/src/lib/i18n.ts` (zh + en — labels only)

- [ ] **Step 1: Add i18n keys**

In `frontend/src/lib/i18n.ts`, add to both zh and en blocks (after the fundamentals.* keys from D1):

```typescript
// zh block
    "news.title": "近期新闻",
    "news.empty": "近 24 小时无相关新闻",
    "news.sentiment_pos": "正面",
    "news.sentiment_neg": "负面",
    "news.sentiment_neu": "中性",
```

```typescript
// en block
    "news.title": "Recent News",
    "news.empty": "No relevant news in the last 24h",
    "news.sentiment_pos": "Positive",
    "news.sentiment_neg": "Negative",
    "news.sentiment_neu": "Neutral",
```

- [ ] **Step 2: Create NewsBlock.tsx**

Create `frontend/src/components/stock/NewsBlock.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { RatingCard, NewsItem, NewsRaw } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function decodeNewsRaw(raw: unknown): NewsItem[] {
  if (typeof raw !== "object" || raw === null) return [];
  const obj = raw as Partial<NewsRaw>;
  return obj.headlines ?? [];
}

function relativeTime(iso: string, locale: Locale): string {
  if (!iso) return locale === "zh" ? "未知" : "—";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

const SENTIMENT_TONE: Record<NewsItem["sentiment"], string> = {
  pos: "bg-tm-pos",
  neg: "bg-tm-neg",
  neu: "bg-tm-muted",
};

export default function NewsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const news = card.breakdown.find((b) => b.signal === "news");
  const items = decodeNewsRaw(news?.raw);

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
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={`${item.link}-${i}`} className="flex gap-3 items-start">
            <span
              aria-label={t(locale, `news.sentiment_${item.sentiment}`)}
              className={`mt-1.5 inline-block w-2 h-2 rounded-full shrink-0 ${SENTIMENT_TONE[item.sentiment]}`}
            />
            <div className="flex-1 min-w-0">
              {item.link ? (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-tm-fg hover:text-tm-accent line-clamp-2"
                >
                  {item.title}
                </a>
              ) : (
                <div className="text-sm text-tm-fg line-clamp-2">{item.title}</div>
              )}
              <div className="text-xs text-tm-muted mt-1 flex gap-2">
                <span>{item.publisher || "—"}</span>
                <span>·</span>
                <span>{relativeTime(item.published_at, locale)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 3: Verify type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

Expected: silent tsc + lint pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stock/NewsBlock.tsx frontend/src/lib/i18n.ts
git commit -m "feat(stock): NewsBlock component (M4a D2)

New right-pane section reading news.raw.headlines (populated by B2).
Renders ≤5 items as: sentiment dot + clickable title + publisher
chip + relative time (Xm/Xh/Xd ago). i18n in both zh + en (5 new
keys × 2 locales).

Sentiment colors via tm-pos/tm-neg/tm-muted tokens for dark+light
theme parity."
```

---

### Task D3: CatalystsBlock — earnings card + macro calendar

**Why:** Drop the news triple-up (moved to NewsBlock D2); render the earnings raw as a real card (next date, days until, EPS estimate, revenue estimate) + the calendar event list as a vertical timeline.

**Files:**
- Modify: `frontend/src/components/stock/CatalystsBlock.tsx`
- Modify: `frontend/src/lib/i18n.ts` (zh + en)

- [ ] **Step 1: Add i18n keys**

After the `news.*` keys from D2 in both zh and en blocks:

```typescript
// zh block
    "catalysts.title": "催化剂",
    "catalysts.earnings_label": "下次财报",
    "catalysts.eps_estimate": "EPS 预期",
    "catalysts.revenue_estimate": "营收预期",
    "catalysts.days_until": "天后",
    "catalysts.no_earnings": "无已知财报日期",
    "catalysts.calendar_label": "宏观日历",
    "catalysts.no_calendar": "近期无相关宏观事件",
```

```typescript
// en block
    "catalysts.title": "Catalysts",
    "catalysts.earnings_label": "Next Earnings",
    "catalysts.eps_estimate": "EPS Est.",
    "catalysts.revenue_estimate": "Rev Est.",
    "catalysts.days_until": "days",
    "catalysts.no_earnings": "No earnings date on file",
    "catalysts.calendar_label": "Macro Calendar",
    "catalysts.no_calendar": "No upcoming macro events",
```

- [ ] **Step 2: Replace CatalystsBlock.tsx**

Replace `frontend/src/components/stock/CatalystsBlock.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { RatingCard, EarningsRaw } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function decodeEarnings(raw: unknown): EarningsRaw | null {
  if (typeof raw !== "object" || raw === null) return null;
  return raw as EarningsRaw;
}

function decodeCalendar(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  return [];
}

function fmtCurrency(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

export default function CatalystsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const earnings = decodeEarnings(card.breakdown.find((b) => b.signal === "earnings")?.raw);
  const calendar = decodeCalendar(card.breakdown.find((b) => b.signal === "calendar")?.raw);

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-4">
      <h2 className="text-lg font-semibold text-tm-fg">{t(locale, "catalysts.title")}</h2>

      {/* Earnings card */}
      <div>
        <div className="text-xs text-tm-muted uppercase tracking-wide mb-2">
          {t(locale, "catalysts.earnings_label")}
        </div>
        {earnings && earnings.next_date ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <div className="text-tm-fg font-mono">{earnings.next_date}</div>
              <div className="text-xs text-tm-muted">
                {earnings.days_until != null
                  ? `${earnings.days_until} ${t(locale, "catalysts.days_until")}`
                  : ""}
              </div>
            </div>
            <div>
              <div className="text-xs text-tm-muted">{t(locale, "catalysts.eps_estimate")}</div>
              <div className="text-tm-fg font-mono">
                {earnings.eps_estimate != null ? earnings.eps_estimate.toFixed(2) : "—"}
              </div>
            </div>
            <div>
              <div className="text-xs text-tm-muted">{t(locale, "catalysts.revenue_estimate")}</div>
              <div className="text-tm-fg font-mono">{fmtCurrency(earnings.revenue_estimate)}</div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-tm-muted">{t(locale, "catalysts.no_earnings")}</p>
        )}
      </div>

      {/* Macro calendar */}
      <div>
        <div className="text-xs text-tm-muted uppercase tracking-wide mb-2">
          {t(locale, "catalysts.calendar_label")}
        </div>
        {calendar.length === 0 ? (
          <p className="text-sm text-tm-muted">{t(locale, "catalysts.no_calendar")}</p>
        ) : (
          <ul className="text-xs text-tm-fg-2 space-y-1">
            {calendar.slice(0, 5).map((evt, i) => (
              <li key={i} className="font-mono">
                {typeof evt === "string" ? evt : JSON.stringify(evt)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Verify type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

Expected: silent tsc + lint pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stock/CatalystsBlock.tsx frontend/src/lib/i18n.ts
git commit -m "feat(stock): CatalystsBlock renders earnings card + macro calendar (M4a D3)

Drops the news triple-up (moved to NewsBlock D2). Now renders:
- Earnings card: next_date + days_until + EPS estimate + revenue
  estimate, in a 3-cell grid (— for missing fields)
- Macro calendar: first 5 events as a font-mono list

i18n keys added for both zh + en (8 new keys × 2 locales). Calendar
items render as JSON.stringify for now (calendar.raw shape is upstream
M4b scope when real macro events land)."
```

---

## Phase E — Frontend chart + layout

### Task E1: PriceChart — TradingView lightweight-charts

**Why:** Replaces the "Chart for AAPL — full lightweight-charts integration in M4" placeholder with real candlestick + volume bars + a 50-day moving average overlay. Fetches via the C1 endpoint, falls back to a friendly "no data" message on empty bars.

**Files:**
- Modify: `frontend/package.json` (add `lightweight-charts` dep)
- Modify: `frontend/src/components/stock/PriceChart.tsx`
- Modify: `frontend/src/lib/i18n.ts`

- [ ] **Step 1: Install the npm dep**

```bash
cd /Users/a22309/Desktop/Side-projects/Artifacts/alpha-agent/frontend
pnpm add lightweight-charts@^4
```

Expected: package.json gains `"lightweight-charts": "^4.x"` in dependencies. pnpm-lock.yaml updates.

- [ ] **Step 2: Add i18n keys**

In `frontend/src/lib/i18n.ts`, append to both zh and en blocks (after the catalysts.* keys from D3):

```typescript
// zh block
    "chart.title": "价格走势",
    "chart.no_data": "暂无价格数据",
    "chart.loading": "加载中…",
    "chart.error": "图表加载失败：{reason}",
```

```typescript
// en block
    "chart.title": "Price Action",
    "chart.no_data": "No price data available",
    "chart.loading": "Loading…",
    "chart.error": "Chart load failed: {reason}",
```

- [ ] **Step 3: Replace PriceChart.tsx**

Replace `frontend/src/components/stock/PriceChart.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchOhlcv, type OhlcvBar } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

// lightweight-charts v4 imports — keep dynamic to avoid SSR breakage (the
// lib touches `document` at import time). The component itself is
// client-only via "use client".

function sma(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i >= window - 1 ? sum / window : null);
  }
  return out;
}

export default function PriceChart({ ticker }: { ticker: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "empty" | "error">("loading");
  const [errMsg, setErrMsg] = useState<string>("");

  const renderChart = useCallback(async (bars: OhlcvBar[]) => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = "";

    const { createChart, ColorType } = await import("lightweight-charts");

    // Resolve theme from data-theme attribute (set globally by ThemeProvider).
    const isLight = document.documentElement.dataset.theme === "light";
    const bg = isLight ? "#fafaf7" : "#0a0a0a";
    const text = isLight ? "#27272a" : "#d4d4d8";
    const grid = isLight ? "#e4e4e7" : "#27272a";

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 320,
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: text },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: grid },
      timeScale: { borderColor: grid, timeVisible: false },
    });

    const candle = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
    });
    candle.setData(
      bars.map((b) => ({ time: b.date, open: b.open, high: b.high, low: b.low, close: b.close }))
    );

    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      bars.map((b) => ({
        time: b.date,
        value: b.volume,
        color: b.close >= b.open ? "rgba(22,163,74,0.4)" : "rgba(220,38,38,0.4)",
      }))
    );

    const smaValues = sma(bars.map((b) => b.close), 50);
    const ma = chart.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false });
    ma.setData(
      bars
        .map((b, i) => ({ time: b.date, value: smaValues[i] }))
        .filter((p): p is { time: string; value: number } => p.value !== null)
    );

    chart.timeScale().fitContent();

    // Resize handler — TradingView doesn't auto-resize.
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    (async () => {
      setStatus("loading");
      try {
        const r = await fetchOhlcv(ticker);
        if (cancelled) return;
        if (!r.bars.length) {
          setStatus("empty");
          return;
        }
        cleanup = await renderChart(r.bars);
        setStatus("ok");
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        setErrMsg(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [ticker, renderChart]);

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "chart.title")} · {ticker}
      </h2>
      {/* Fixed-height parent: lightweight-charts reads offsetWidth/Height at
          init; collapsing to 0 in a flex/grid parent kills the canvas
          (CLAUDE.md memory feedback_recharts_responsive_container_zero_width.md). */}
      <div style={{ width: "100%", height: 320 }}>
        {status === "loading" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "chart.loading")}
          </div>
        ) : status === "empty" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "chart.no_data")}
          </div>
        ) : status === "error" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-neg">
            {t(locale, "chart.error").replace("{reason}", errMsg)}
          </div>
        ) : null}
        <div ref={containerRef} style={{ width: "100%", height: "100%", display: status === "ok" ? "block" : "none" }} />
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Verify type check + lint + build**

```bash
cd frontend && npx tsc --noEmit && npx next lint && npx next build
```

Expected: silent tsc + lint pass + build success. The build step is important here — `lightweight-charts` has SSR pitfalls, and `next build` exercises the import path that `next dev` does not.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/stock/PriceChart.tsx frontend/src/lib/i18n.ts
git commit -m "feat(stock): TradingView lightweight-charts PriceChart (M4a E1)

Swaps the M3 placeholder for a real candlestick + volume + 50d MA chart
backed by /api/stock/{ticker}/ohlcv (C1). Theme switches based on
document.documentElement.dataset.theme (light/dark parity).

lightweight-charts (Apache 2.0) imported dynamically so SSR is safe.
Fixed-height parent div per CLAUDE.md memory
feedback_recharts_responsive_container_zero_width.md. Resize via
ResizeObserver. i18n: 4 new keys × 2 locales."
```

---

### Task E2: StockCardLayout — wire NewsBlock in

**Why:** Add the new NewsBlock to the right-pane scroll, between CatalystsBlock and SourcesBlock so the visual order is: Lean Thesis → Attribution → Price → Fundamentals → Catalysts → **News** → Sources.

**Files:**
- Modify: `frontend/src/components/stock/StockCardLayout.tsx`

- [ ] **Step 1: Modify imports + JSX**

Open `frontend/src/components/stock/StockCardLayout.tsx`. Add the import:

```tsx
import NewsBlock from "./NewsBlock";
```

Then add `<NewsBlock card={card} />` between `<CatalystsBlock card={card} />` and `<SourcesBlock card={card} />` in the right `<main>`:

```tsx
        <FundamentalsBlock card={card} />
        <CatalystsBlock card={card} />
        <NewsBlock card={card} />
        <SourcesBlock card={card} />
```

- [ ] **Step 2: Verify type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx next lint
```

Expected: silent + lint pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stock/StockCardLayout.tsx
git commit -m "feat(stock): wire NewsBlock into right-pane (M4a E2)

Right-pane render order: Lean Thesis → Attribution → Price → Fundamentals
→ Catalysts → News → Sources. M4a structural rendering is now complete."
```

---

## Phase F — Acceptance

### Task F1: m4a-acceptance Makefile + smoke

**Why:** Encodes the manual checklist so subagents/CI can verify M4a is done with one command. Mirrors the m3-acceptance shape so the muscle memory stays the same.

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Read current Makefile end**

```bash
cat Makefile | tail -15
```

Note the existing `m3-acceptance:` target — we'll add a sibling `m4a-acceptance:` target right after it.

- [ ] **Step 2: Append the new target**

Add to the end of `Makefile` (after `m3-acceptance`):

```makefile

m4a-acceptance:
	@echo "==> Running M4a acceptance suite"
	# Backend: signal fetcher + ohlcv endpoint tests
	pytest tests/signals/test_yf_helpers.py tests/signals/test_factor.py \
	       tests/signals/test_news.py tests/signals/test_earnings.py \
	       tests/api/test_stock_ohlcv.py -v
	# Frontend: same checks as M3 (deps clean, types clean, lint clean, builds)
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm tsc --noEmit
	cd frontend && pnpm next lint
	cd frontend && pnpm next build
	# Smoke: hit the deployed endpoints to confirm production parity
	@echo "==> Smoke: /api/stock/AAPL/ohlcv (deployed)"
	@curl -sS --max-time 30 "https://alpha.bobbyzhong.com/api/stock/AAPL/ohlcv?period=6mo" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  bars={len(d[\"bars\"])}, period={d[\"period\"]}')" \
	  || (echo 'ohlcv smoke FAILED' && exit 1)
	@echo "==> Smoke: /api/stock/AAPL has factor.raw.fundamentals"
	@curl -sS --max-time 15 "https://alpha.bobbyzhong.com/api/stock/AAPL" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); f=next((b for b in d['card']['breakdown'] if b['signal']=='factor'), None); assert f and isinstance(f['raw'], dict) and 'fundamentals' in f['raw'], 'factor.raw missing fundamentals'" \
	  || (echo 'factor.raw smoke FAILED' && exit 1)
	@echo "M4a acceptance PASS"
```

- [ ] **Step 3: Run it (after all prior tasks merged)**

```bash
make m4a-acceptance
```

Expected (after every previous task is merged + deployed):

```
==> Running M4a acceptance suite
... pytest output, all green ...
... frontend build output, ✓ Compiled successfully ...
==> Smoke: /api/stock/AAPL/ohlcv (deployed)
  bars=126, period=6mo
==> Smoke: /api/stock/AAPL has factor.raw.fundamentals
M4a acceptance PASS
```

- [ ] **Step 4: Manual UAT (no automation possible here)**

In a browser, open `https://alpha.bobbyzhong.com/stock/AAPL` and visually verify:

1. **FundamentalsBlock** shows a 2×4 grid with non-"—" values for P/E (T), Market Cap, Beta at minimum.
2. **NewsBlock** shows ≥1 headline with a publisher chip + relative time + colored sentiment dot.
3. **CatalystsBlock** shows next earnings date in YYYY-MM-DD with EPS estimate (or "—" if Apple is between cycles).
4. **PriceChart** renders a candlestick chart (green/red bars) with volume histogram at the bottom and a blue 50-day MA line. Resize the browser to confirm the chart re-fits.
5. Toggle the theme switch (light ↔ dark) — chart background updates; block text stays readable; no flash of un-themed content.
6. Toggle locale (zh ↔ en) — block titles update; "—" placeholders remain in both.

Capture a screenshot of each block in both themes. Save to `docs/superpowers/screenshots/m4a-aapl-{light,dark}.png` (the screenshot dir doesn't need to exist; `mkdir -p` it).

- [ ] **Step 5: Commit + handoff note**

```bash
mkdir -p docs/superpowers/screenshots
# (drop the captured screenshots here)
git add Makefile docs/superpowers/screenshots/
git commit -m "ci(m4a): m4a-acceptance target + UAT screenshots

Encodes the full M4a verification path: pytest signal+endpoint tests,
frontend tsc+lint+build, then two curl smokes against the deployed
backend confirming /api/stock/AAPL/ohlcv returns bars and the rating
card carries factor.raw.fundamentals.

Acceptance is now reproducible by 'make m4a-acceptance'. Manual UAT
screenshots in docs/superpowers/screenshots/ document the visual
deliverable for the audit trail.

M4a SHIPS. Hand off to M4b (alerts feed + Rich BYOK LLM SSE)."
```

---

## Hand-off to M4b

After M4a acceptance passes + visual approval:

**M4b plan inputs (write next):**
- `GET /api/alerts/recent?ticker=X&limit=20` exposing `alert_queue` rows + frontend `/alerts` page becomes per-ticker timeline (currently it renders cron run history)
- Rich BYOK LLM SSE streaming endpoint `POST /api/brief/{ticker}/stream` + frontend EventSource consumer in a new `<RichThesis />` component; BYOK key UI in `/settings` (already has BYOK scaffolding from M3)
- Playwright E2E covering 8 critical paths (picks load, click ticker, back-to-picks, refresh button, alerts feed, settings BYOK roundtrip, zh/en toggle, dark/light toggle)

**M4a → M4b contract:**

| M4a output | M4b consumer |
|------------|--------------|
| `factor.raw.fundamentals` (dict) | LLM brief prompt context: real P/E, EPS, market cap go into the bull/bear template |
| `news.raw.headlines` (5 items) | LLM brief prompt context: titles + sentiment tags go into bull/bear |
| `earnings.raw.next_date` etc. | LLM brief: "next earnings in N days" framing |
| `GET /api/stock/{t}/ohlcv` | Not directly used by M4b; reused by M5+ if backtester UI ships |
| `NewsBlock`, `FundamentalsBlock`, `CatalystsBlock` decoder helpers | Reused as-is — Rich brief renders **alongside** (not instead of) the structured blocks |

**Open questions for M4b kickoff brainstorming:**
- BYOK key storage: localStorage (existing pattern, leaks via XSS) vs. session cookie HttpOnly (round-trip cost)?
- SSE stream protocol: line-delimited JSON deltas vs. AI SDK's standardized message envelope?
- Rate limit on the LLM brief endpoint: per-user (we have no auth) vs. per-IP (proxy spoofable)?
- Alert feed dedup: `alert_queue.dedup_bucket` is per-30min — does that match the per-ticker timeline UX or do we want hourly buckets?

---

## Risk Matrix

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| yfinance throws under burst load (cron + many users) | Medium | yf_helpers caches Ticker on 10min TTL; OHLCV endpoint is request-time so spikes are user-driven, not cron-driven |
| `yf.Ticker.calendar` returns DataFrame with different column names per ticker | Medium | `extract_next_earnings` wraps key access in try/except + returns None payload on KeyError |
| `lightweight-charts` SSR-imports `document` and breaks `next build` | Low (uses dynamic import) | `next build` step in F1 acceptance gate catches it; if it fails, fall back to wrapping the import in `next/dynamic` |
| Keyword-rule sentiment misclassifies negation ("not bad" → neu, but "Apple's stock not falling" → "falling" → neg) | Medium | M4b LLM-based scorer replaces this; M4a accepts the noise (it's directionally OK in aggregate over 5 headlines) |
| `factor.raw` legacy float rows (written before B1) break FundamentalsBlock | Low | `decodeFactorRaw` checks `typeof === 'object'` first; legacy rows show "No fundamentals data" until next cron tick rewrites them |
| Frontend project rootDirectory misconfigured → git push doesn't redeploy frontend | High (known issue) | Each frontend-touching task's commit message reminds executor to manually `vercel --prod --token $VTOK --scope ...` from `frontend/`; or fix rootDirectory in Vercel project settings as a separate ops task |
| Test fixtures drift from yfinance live shape | Medium | All B-phase tests mock `get_ticker`; live yfinance is only touched via the F1 smoke curl, which would surface any wire-shape drift |

---

## Total LOC estimate

- **Backend:** ~260 LOC (yf_helpers 175 + signal enrichments 50 + ohlcv route 35)
- **Frontend:** ~450 LOC (NewsBlock 75 + FundamentalsBlock 65 rewrite + CatalystsBlock 65 rewrite + PriceChart 130 rewrite + types 40 + i18n 30 + StockCardLayout edit 5 + package.json edit 1)
- **Tests:** ~370 LOC (test_yf_helpers 140 + test_factor 35 update + test_news 50 update + test_earnings 50 update + test_stock_ohlcv 50)
- **Plan total: ~1080 LOC of new+modified code across 12 tasks**

---

## Execution Tip

The 12 tasks fall into three dependency tiers:

- **Tier 1 (foundation, sequential):** A1 → A2
- **Tier 2 (signal+endpoint, can run as 4 parallel subagents):** B1, B2, B3, C1
- **Tier 3 (frontend, can run as 3-4 parallel subagents):** D1, D2, D3, E1 — each requires the matching Tier 2 task
- **Tier 4 (integration, sequential):** E2 → F1

If executing via `superpowers:subagent-driven-development`, dispatch Tier 2 as one wave of 4 parallel subagents, Tier 3 as one wave of 4, and run Tier 1 + Tier 4 inline. Saves ~40% wall time vs strict sequential.
