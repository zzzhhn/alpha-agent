-- Isolated paper research books. No DDL or DML touches sim_/l2_ or event sources.
-- Forward-only. To roll back, disable the research tick and keep its receipts;
-- any eventual removal is a new migration after the audit-retention decision.
CREATE TABLE event_shadow_runtime (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    activated_at timestamptz NOT NULL
);

CREATE TABLE event_shadow_book (
    sleeve text PRIMARY KEY CHECK (sleeve IN ('long_only', 'long_short', 'no_trade')),
    initial_cash numeric(16,2) NOT NULL CHECK (initial_cash > 0),
    free_cash numeric(16,2) NOT NULL,
    restricted_cash numeric(16,2) NOT NULL DEFAULT 0 CHECK (restricted_cash >= 0)
);

CREATE TABLE event_shadow_observation (
    event_id bigint PRIMARY KEY,
    event_key text NOT NULL,
    considered_at timestamptz NOT NULL
);

CREATE TABLE event_shadow_trial (
    id bigserial PRIMARY KEY,
    policy text NOT NULL,
    event_id bigint NOT NULL,
    event_key text NOT NULL,
    sleeve text NOT NULL REFERENCES event_shadow_book(sleeve),
    ticker text NOT NULL,
    direction text CHECK (direction IN ('long', 'short')),
    rule text NOT NULL,
    event_evidence jsonb NOT NULL,
    decision_at timestamptz NOT NULL,
    entry_after timestamptz NOT NULL,
    entry_until timestamptz NOT NULL CHECK (entry_until > entry_after),
    status text NOT NULL CHECK (status IN ('pending', 'open', 'closed', 'abstained', 'expired')),
    reason text NOT NULL,
    qty integer NOT NULL DEFAULT 0 CHECK (qty >= 0),
    held_cash numeric(16,2) NOT NULL DEFAULT 0 CHECK (held_cash >= 0),
    entry_price numeric(16,6),
    entry_at timestamptz,
    exit_after timestamptz,
    exit_price numeric(16,6),
    exit_at timestamptz,
    realized_pnl numeric(16,2),
    fees numeric(16,2) NOT NULL DEFAULT 0 CHECK (fees >= 0),
    borrow_cost numeric(16,2) NOT NULL DEFAULT 0 CHECK (borrow_cost >= 0),
    dividend_cash numeric(16,2) NOT NULL DEFAULT 0,
    receipts jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL,
    UNIQUE (policy, event_id, sleeve),
    UNIQUE (policy, event_key, sleeve),
    CHECK (status NOT IN ('open', 'closed') OR (direction IS NOT NULL AND qty > 0 AND entry_at IS NOT NULL AND entry_price > 0)),
    CHECK (status <> 'closed' OR (exit_at > entry_at AND exit_price > 0 AND realized_pnl IS NOT NULL))
);

CREATE INDEX event_shadow_active_idx ON event_shadow_trial (status, decision_at, id)
    WHERE status IN ('pending', 'open');
