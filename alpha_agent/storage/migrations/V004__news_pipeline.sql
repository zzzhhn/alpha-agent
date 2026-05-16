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
