-- Private research cache, never read by ranking, LLM or execution.
CREATE TABLE IF NOT EXISTS research_option_sample (
    symbol text NOT NULL CHECK (symbol IN ('SPY','QQQ','NVDA')),
    slot timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    status text NOT NULL,
    sample jsonb NOT NULL,
    PRIMARY KEY(symbol,slot)
);
