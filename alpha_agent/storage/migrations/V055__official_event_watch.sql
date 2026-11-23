-- Official evidence is append-only by observation/version, never a trade instruction.
CREATE TABLE official_event_watch (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('sec_edgar', 'investor_relations')),
    source_key TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    published_date DATE,
    published_at_quality TEXT NOT NULL CHECK (published_at_quality IN
        ('sec_accepted', 'source_timestamp', 'date_only', 'unavailable')),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('observed', 'corrected', 'withdrawn')),
    UNIQUE (ticker, source, source_key, content_hash)
);

CREATE INDEX official_event_watch_latest_idx ON official_event_watch (ticker, first_seen_at DESC, id DESC);

CREATE TABLE official_event_source (
    ticker TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('sec_edgar', 'investor_relations')),
    cik TEXT,
    cik_checked_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    etag TEXT,
    last_modified TEXT,
    PRIMARY KEY (ticker, source)
);

CREATE TABLE official_event_watch_state (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    tickers TEXT[] NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL
);
