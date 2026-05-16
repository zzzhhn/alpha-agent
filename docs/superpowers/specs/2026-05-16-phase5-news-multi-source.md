# Phase 5 — News Multi-Source Aggregation

**Date:** 2026-05-16
**Status:** Spec approved, plan pending
**Owner:** zzzhhn

## Goal

Replace yfinance-as-sole-news-source with a dual-channel aggregator
covering both per-ticker financial news (Finnhub / FMP / RSS) and
market-wide political-macro context (Trump's Truth Social / Fed / OFAC),
with BYOK-LLM doing sentiment + ticker-extraction at cron time so page
loads are zero-LLM-latency.

## Why

1. **yfinance is too thin and too fragile**: shallow (~5-10 items per
   ticker), schema changes without notice, breaks under load. The only
   news source today.
2. **Financial-only sources miss half the signal**: prior research
   returned Finnhub + FMP + RSS as the recommendation. User pushed back:
   "可能影响美股股价的 news factor 永远不只是金融时报" - Trump posts,
   Fed speeches, OFAC sanctions, tariffs, geopolitical events. This is
   captured in memory `feedback_us_equity_news_political_signal.md`.
3. **The two news classes do not share a data shape**: per-ticker news
   maps cleanly to one row per (ticker, event). Macro events map to
   *N tickers per event*; baking them as N rows is quadratic write
   amplification. They need separate storage and a dynamic mapping at
   query time.

## Decisions resolved during brainstorm

| Question | Answer | Rationale |
|---|---|---|
| Architecture | Dual-channel: `news_items` (per-ticker) + `macro_events` (market-wide) | Avoids quadratic writes; lets LLM map macro -> tickers dynamically at query time. Validated by Stocktwits/Finchat experience: macro buried in per-ticker pages gets skipped, dedicated context widget gets read. |
| Source set | Full v1: 3 per-ticker + 3 macro adapters | Aggregator + failover + dedup is built once regardless; adding more adapters later is one file each. Macro sources are all keyless (Truth/Fed/OFAC), so trimming them gains nothing. |
| UI surface | Per-ticker page only: existing `NewsBlock` + new `MarketContextWidget`. No `/news` global feed in v1 | Smallest UI scope, validates pipeline. `/news` feed deferred to phase 2. |
| LLM strategy | Cron-time BYOK-LLM batched: sentiment for per-ticker, entity-extraction + sentiment for macro | Page loads stay zero-LLM-latency. Cost bounded by per-day item count (~$3-10/mo BYOK estimate). Skipping LLM for macro is not viable - it is required for ticker mapping. |

## Architecture

```
                  ┌──────────────────────────────────────┐
                  │             NewsBus                  │
                  │                                      │
┌─────────────┐   │   ┌────────────────────────┐         │   ┌────────────────┐
│  Finnhub    │──>│   │                        │         │   │                │
│  FMP        │──>│──>│  PerTickerAggregator   │──[upsert]──>│  news_items    │
│  RSS        │──>│   │  (priority + failover) │         │   │                │
└─────────────┘   │   └────────────────────────┘         │   └────────────────┘
                  │                                      │
┌─────────────┐   │   ┌────────────────────────┐         │   ┌────────────────┐
│ Truth (CNN) │──>│   │                        │         │   │                │
│ Fed RSS     │──>│──>│  MacroAggregator       │──[upsert]──>│  macro_events  │
│ OFAC RSS    │──>│   │  (parallel poll)       │         │   │                │
└─────────────┘   │   └────────────────────────┘         │   └────────────────┘
                  │                                      │
                  └──────────────────────────────────────┘
                                                                     │
                                                                     v
                                              ┌─────────────────────────────────┐
                                              │  llm_batch_worker (every 15min) │
                                              │  picks WHERE llm_processed_at   │
                                              │    IS NULL → batched LLM call → │
                                              │    sentiment, tickers_extracted │
                                              └─────────────────────────────────┘
```

## Schema (V004 migration)

```sql
-- Per-ticker news (one row per (ticker, dedup_hash); a single source story
-- about AAPL produces exactly one row for AAPL).
CREATE TABLE news_items (
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
CREATE INDEX ON news_items (ticker, published_at DESC);
CREATE INDEX ON news_items (source, published_at DESC);
CREATE INDEX ON news_items (llm_processed_at) WHERE llm_processed_at IS NULL;

-- Macro events (one row per event; tickers_extracted carries the LLM
-- mapping so per-ticker queries do an array contains).
CREATE TABLE macro_events (
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
CREATE INDEX ON macro_events (published_at DESC);
CREATE INDEX ON macro_events USING GIN (tickers_extracted);
CREATE INDEX ON macro_events (llm_processed_at) WHERE llm_processed_at IS NULL;
```

## Adapters (6 v1)

All adapters implement one protocol:

```python
class NewsAdapter(Protocol):
    name: str
    channel: Literal["per_ticker", "macro"]
    priority: int  # 1 = primary in failover order; macro adapters all = 1

    async def fetch(
        self, *, ticker: str | None = None, since: datetime
    ) -> list[NewsItem | MacroEvent]:
        ...

    async def is_available(self) -> bool:
        ...
```

### Per-ticker (channel="per_ticker")

| Adapter | Priority | Endpoint | Free-tier limit | Notes |
|---|---|---|---|---|
| `FinnhubAdapter` | 1 | `/company-news?symbol=X&from=Y&to=Z` | 60 req/min | Primary; sized for 557 tickers/hour comfortably |
| `FMPAdapter` | 2 | `/v3/stock_news?tickers=X` | 250/day | Failover-only: invoked only when Finnhub returns empty or errors |
| `RSSAdapter` | 3 | Yahoo Finance per-symbol RSS + Google News keyword | Keyless | Tertiary; fills long-tail when API sources blank |

### Macro (channel="macro")

| Adapter | Source | Cadence | Notes |
|---|---|---|---|
| `TruthSocialAdapter` | `ix.cnn.io/data/truth-social/truth_archive.json` | 5 min | CNN-hosted JSON mirror, append-only |
| `FedRSSAdapter` | `federalreserve.gov/feeds/press_all.xml` | 60 min | Press releases + FOMC + speeches |
| `OFACRSSAdapter` | `ofac.treasury.gov/recent-actions` (RSS) | 60 min | Sanctions designations - directly ticker-relevant |

## Aggregator + dedup

**PerTickerAggregator**: per ticker per cycle, try `FinnhubAdapter.fetch`
first. If empty or `is_available()==False`, fall through to FMP, then
RSS. All hit items merged into one list. Dedup via `dedup_hash` upsert
(`ON CONFLICT DO NOTHING`). Circuit breaker: an adapter failing **5
consecutive cycles** is marked down for a 1-hour cooldown, then probed
on the next cycle and reset to healthy on success.

**MacroAggregator**: each macro source polled independently on its own
cadence (parallel, not failover - they cover non-overlapping events).
Dedup via same `dedup_hash` discipline.

**Dedup hash**:

```python
def dedup_hash(ticker: str | None, url: str, headline: str) -> str:
    """For per-ticker news, include ticker so the same story relevant to
    multiple tickers (e.g. a Bloomberg piece mentioning both AAPL and
    GOOG, returned by both /company-news?symbol=AAPL and ?symbol=GOOG)
    produces one row per ticker. For macro events, ticker is None."""
    tk = (ticker or "").upper()
    norm_url = strip_query_params_and_utm(url).lower()
    norm_headline = " ".join(strip_punct(headline.lower()).split())
    return sha256(f"{tk}|{norm_url}|{norm_headline}".encode()).hexdigest()
```

Composite key (ticker scope + URL + normalized headline) tolerates the
same story arriving from multiple sources with slightly different URLs
while preserving per-ticker rows when a multi-ticker story is returned
by independent per-symbol queries.

## LLM enrichment pipeline

A separate cron worker `llm_news_enrich` runs every 15 min. It queries
both tables for `llm_processed_at IS NULL` rows (limit 100 per run),
calls the BYOK LLM in batches of 10-20, writes the structured response
back, and stamps `llm_processed_at = now()`.

**Per-ticker prompt** (per batch of 10-20 headlines for the same or
mixed tickers):

> Return a JSON array. For each headline below, output `{id, sentiment_score, sentiment_label}` where sentiment_score is a float in [-1, 1] capturing market-impact sentiment for the named ticker, and sentiment_label is one of pos/neg/neu. Be conservative: "company beats earnings" is +0.4 to +0.6, not 1.0. Use 1.0 / -1.0 only for genuinely landmark events.

**Macro prompt** (per batch of 10-20 events):

> Return a JSON array. For each event below, output `{id, tickers, sectors, sentiment_score}` where tickers is the list of US-listed stock tickers materially affected (1-15 max, leave empty for purely partisan posts), sectors is GICS sector names affected, and sentiment_score is a float in [-1, 1] capturing market-wide tone. Apple-related Truth posts → tickers includes AAPL. Tariff announcements → tickers list relevant ADRs + sectors. Sanctions → tickers list affected names.

**Budget**: estimate 100-300 new items/day combined × ~$0.001/item via
BYOK Sonnet 4.6 = $0.10-0.30/day = $3-10/month. Per-call max_tokens
capped at 2000.

**Error semantics**: if a batch LLM call fails (rate-limit, malformed
JSON, BYOK key invalid), the worker logs to `error_log`, leaves
`llm_processed_at = NULL` so the next run retries. No retry cap on the
row itself: each cron tick re-picks the same NULL rows and tries again.
The backlog count surfaces via `/api/_health/news_freshness.llm_backlog`,
so a stuck pipeline is visible from one curl. Rationale: a stuck row
that keeps failing means the LLM is genuinely down (key revoked, budget
hit), and dropping the row would mean losing data; making the user see
backlog growth is the right signal.

## UI surface

### `NewsBlock` (existing, enhanced)

Data source switches from `card.breakdown.find(b => b.signal === "news").raw.headlines`
(yfinance shape) to `card.news_items` (new field on the stock-detail API
response, populated by the backend joining `news_items WHERE ticker = $1
ORDER BY published_at DESC LIMIT 20`).

Each item displays: headline, source badge (finnhub/fmp/rss),
relative time, sentiment color tone (from `sentiment_label`).

### `MarketContextWidget` (new)

Rendered in `StockCardLayout` immediately below `NewsBlock` and above
`SourcesBlock`. Fetches `/api/macro_context?ticker=X&limit=5`. Each
item displays: author icon (Trump 🐘 / Fed 🏛 / OFAC 🇺🇸 / WhiteHouse),
title, relative time, body excerpt (first 200 chars), sentiment tone.
Empty state: "No relevant market-wide events in the last 7 days."

### Sentiment confidence labelling

The widget shows a small "LLM-tagged" caption below each macro item with
the extracted tickers + sectors, so users see why a Trump Apple post
surfaced on the AAPL page.

## API endpoints (new)

```
GET /api/macro_context?ticker=X&limit=5

Response:
{
  "items": [
    {
      "id": 123,
      "author": "trump",
      "title": "Apple should make iPhones in America",
      "url": "https://truthsocial.com/...",
      "body_excerpt": "...",
      "published_at": "2026-05-16T13:24:00Z",
      "sentiment_score": -0.4,
      "tickers_extracted": ["AAPL"],
      "sectors_extracted": ["Information Technology"]
    },
    ...
  ]
}

Implementation: SELECT * FROM macro_events
                WHERE $1 = ANY(tickers_extracted)
                  AND published_at > now() - interval '7 days'
                ORDER BY published_at DESC LIMIT $2
```

Public endpoint, no auth required.

`/api/_health/news_freshness` (new):

```
{
  "sources": [
    {"name": "finnhub",      "last_fetched_at": "...", "items_24h": 1843},
    {"name": "fmp",          "last_fetched_at": "...", "items_24h": 12},
    {"name": "rss_yahoo",    "last_fetched_at": "...", "items_24h": 0},
    {"name": "truth_social", "last_fetched_at": "...", "items_24h": 27},
    {"name": "fed_rss",      "last_fetched_at": "...", "items_24h": 3},
    {"name": "ofac_rss",     "last_fetched_at": "...", "items_24h": 1}
  ],
  "llm_backlog": 14
}
```

So a silently-broken adapter is visible from one curl.

## Cron cadence (added to `.github/workflows/cron-shards.yml`)

```yaml
# Per-ticker news: hourly during market hours (Finnhub 60 req/min easily
# handles 557 tickers per cycle; FMP only kicks in on failover so its
# 250/day budget is preserved).
- cron: '0 14-20 * * 1-5'

# Truth Social: aligned with CNN mirror's own 5-min refresh.
# 24/7 (Trump posts on weekends and overnight).
- cron: '*/5 * * * *'

# Fed + OFAC: hourly 24/7; both publish at most a few times/day so this
# is conservative.
- cron: '0 * * * *'

# LLM enrichment: every 15 min, picks up llm_processed_at IS NULL rows.
- cron: '*/15 * * * *'
```

Each new cron lands a separate GH Actions job that calls a corresponding
backend endpoint (`/api/cron/news_per_ticker`, `/api/cron/news_macro`,
`/api/cron/llm_news_enrich`). Backend handler in
`api/cron/news_pipeline.py`. Same shape as `fast_intraday`: returns
`{ok, source, rows_written, errors}` and writes to `cron_runs` for the
diagnostic dashboards.

## Backfill / bootstrap

- **Per-ticker**: no backfill. Cron starts from deploy time forward.
  Finnhub free does not expose history beyond ~7 days anyway.
- **Macro**: one-shot script `scripts/backfill_macro.py --days 30`
  pulls 30 days of Truth Social CNN archive + Fed RSS + OFAC RSS,
  inserts as `llm_processed_at = NULL`, then `llm_news_enrich` cron
  picks them up over the next few cycles. Estimated 200-500 macro events
  × $0.001 = $0.20-0.50 one-time LLM cost.

## Backward compatibility

The existing `news` signal in `combine`'s breakdown stays - it is the
ticker's news-flow z-score, used by the rating fusion. Today
`alpha_agent/signals/news.py` calls yfinance directly. Post-v1 it
becomes a thin function querying `news_items WHERE ticker = $1 AND
published_at > now() - interval '24 hours'` and computing the same z
from the LLM `sentiment_score` field (average score × tanh count
bonus, same shape as today's keyword-rule sentiment z). The fast cron
keeps writing the `news` breakdown entry as before.

`raw` shape stays compatible: continues to return
`{n, mean_sent, headlines}` so legacy code reading
`card.breakdown.find(b => b.signal === "news").raw.headlines` keeps
working. v1 also adds a new `card.news_items` field on the stock-detail
API response (populated by the backend joining `news_items WHERE
ticker = $1 ORDER BY published_at DESC LIMIT 20`), and `NewsBlock` is
rewritten in v1 to consume `card.news_items` directly - cutover is
atomic, not staged.

## Tests

- **Adapter integration tests** (`tests/news/test_*_adapter.py`): each
  adapter has a fixture file of a real upstream response sample, test
  asserts normalize → NewsItem shape and dedup_hash determinism.
- **Aggregator failover test**: mock FinnhubAdapter to raise, assert
  FMP is called next, assert RSS is called when both above empty.
- **Dedup unit test**: known URL + headline pairs produce identical
  hash; URL with vs without query params normalize to same hash.
- **LLM enrichment test**: mock LLM client returns canned JSON,
  assert `update_news_items_llm_result` writes back the right fields,
  `llm_processed_at` stamped, malformed JSON path leaves the row alone.
- **Schema test** (`tests/storage/test_migration_v004.py`): apply
  V004, insert sample rows, assert constraints.
- **E2E smoke** (`make news-acceptance`): V004 migration + single
  trigger of each cron + LLM single-batch run + curl
  `/api/macro_context?ticker=AAPL` returns 200 with a list shape.

## USER SETUP (one-time, before first deploy)

1. Apply for Finnhub free key at `finnhub.io/register` (~2 min). Add
   `FINNHUB_API_KEY` to Vercel `alpha-agent` project env.
2. Apply for FMP free key at
   `site.financialmodelingprep.com/register` (~2 min). Add
   `FMP_API_KEY`.
3. (No other keys needed - CNN mirror, Fed RSS, OFAC RSS are keyless.)
4. After implementation merges, apply V004 migration:
   `python -m alpha_agent.storage.migrations.runner $DATABASE_URL`.
5. Run one-time macro backfill:
   `python scripts/backfill_macro.py --days 30`.
6. Verify all six adapters live:
   `curl https://alpha.bobbyzhong.com/api/_health/news_freshness`
   should show non-null `last_fetched_at` for every source after the
   first cron cycle.

## Out of scope (deferred to Phase 5+)

- `/news` global feed page (current decision: per-ticker only in v1).
- GDELT Doc 2.0 macro source (good Phase 2 add once core channel
  shipped).
- Polymarket / Kalshi prediction-market signal.
- X / Twitter (free tier killed Feb 2026, pay-per-use cost not
  justified for v1).
- Benzinga Newswire (paid $200/mo, defer until revenue).
- Push notifications when macro_events for a watchlisted ticker land
  (defer to Phase 6 alerts work).

## Risks

| Risk | Mitigation |
|---|---|
| CNN's Truth Social mirror goes offline | Fall back to `trumpstruth.org` RSS or `stiles/trump-truth-social-archive` GitHub auto-update; switch via TRUTH_SOURCE env var |
| Finnhub free-tier IP rate-limit under 557-ticker hourly fanout | The 60 req/min limit allows ~3600/hour comfortably for 557 tickers/hour; if hit, FMP failover absorbs the spillover for that ticker |
| LLM costs spike (e.g. high news day) | Per-batch token cap + per-day limit in `llm_news_enrich`; backlog visible via `/api/_health/news_freshness` |
| Macro events extract zero tickers (LLM judges the post irrelevant) | Stored anyway with `tickers_extracted = []`; widget filter naturally hides them per-ticker, but the row stays for a future global `/news` feed |
| Dedup misses (same story slightly reworded) | Acceptable for v1; can later add SimHash-based fuzzy match |
| FMP 250/day budget burned by an unexpected Finnhub outage | Circuit breaker pauses FMP escalation after N failures in a cycle; budget consumed but bounded; alert via `news_freshness` |

## Phase 5 LOC estimate

| Layer | Files | LOC |
|---|---|---|
| Backend adapters | 6 new + base protocol | ~450 |
| Aggregators + dedup helpers | 2 new modules | ~200 |
| Cron handlers | 3 new (`news_per_ticker`, `news_macro`, `llm_news_enrich`) | ~250 |
| `/api/macro_context` + `/api/_health/news_freshness` | 2 endpoints | ~120 |
| V004 migration | 1 file | ~60 |
| `alpha_agent/signals/news.py` rewrite | edit | ~80 |
| Frontend `MarketContextWidget` + `NewsBlock` rewrite | 2 components | ~250 |
| Frontend types + API client | edits | ~80 |
| Tests | 8 new files | ~400 |
| YAML workflow additions | edit | ~120 |
| Bootstrap script | 1 new | ~80 |
| **Total** | **~25 new + ~6 edited files** | **~2090 LOC** |
