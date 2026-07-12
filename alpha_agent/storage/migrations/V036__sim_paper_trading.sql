-- alpha_agent/storage/migrations/V036__sim_paper_trading.sql
-- User-facing paper-trading simulator. Namespace: sim_ (isolated from l2_ system tables).
-- Sizing: ~6 MB per user over 5 years — safe for Neon 512 MB free tier.

CREATE TABLE IF NOT EXISTS sim_account (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    initial_cash  double precision NOT NULL DEFAULT 1000000.0,
    cash          double precision NOT NULL DEFAULT 1000000.0,
    created_at    timestamptz NOT NULL DEFAULT now(),
    reset_at      timestamptz,
    reset_count   int NOT NULL DEFAULT 0,
    UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS sim_order (
    id                bigserial PRIMARY KEY,
    account_id        bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    ticker            text NOT NULL,
    side              text NOT NULL CHECK (side IN ('buy','sell')),
    order_type        text NOT NULL CHECK (order_type IN ('market','limit')),
    qty               int NOT NULL CHECK (qty > 0),
    limit_price       double precision,
    signal_date       date NOT NULL,
    fill_date         date,
    fill_price        double precision,
    status            text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','filled','expired','cancelled')),
    expire_after_days int NOT NULL DEFAULT 5,
    created_at        timestamptz NOT NULL DEFAULT now(),
    filled_at         timestamptz
);
CREATE INDEX IF NOT EXISTS idx_sim_order_account_status
    ON sim_order (account_id, status, signal_date);
CREATE INDEX IF NOT EXISTS idx_sim_order_ticker_pending
    ON sim_order (ticker, status) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS sim_position (
    id            bigserial PRIMARY KEY,
    account_id    bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    ticker        text NOT NULL,
    qty           int NOT NULL DEFAULT 0,
    avg_cost      double precision NOT NULL,
    realized_pnl  double precision NOT NULL DEFAULT 0.0,
    opened_at     timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_sim_position_account
    ON sim_position (account_id) WHERE qty > 0;

CREATE TABLE IF NOT EXISTS sim_equity_daily (
    id               bigserial PRIMARY KEY,
    account_id       bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    as_of_date       date NOT NULL,
    portfolio_value  double precision NOT NULL,
    cash             double precision NOT NULL,
    unrealized_pnl   double precision NOT NULL,
    realized_pnl     double precision NOT NULL,
    benchmark_close  double precision,
    UNIQUE (account_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_sim_equity_daily_account
    ON sim_equity_daily (account_id, as_of_date DESC);
