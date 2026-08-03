-- Independent recommendation sleeves and continuous share-level L2 accounting.
-- The recommendation payload already stores both frozen sleeve snapshots; the
-- additions below upgrade the L2 evidence from isolated target-weight batches
-- to a continuous cash + shares book without rewriting legacy evidence.

ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS pre_qty bigint;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS target_qty bigint;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS delta_qty bigint;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS side text
    CHECK (side IN ('buy', 'sell', 'hold'));
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS gross_notional double precision;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS transaction_cost double precision;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS source_policy_id text;
ALTER TABLE l2_order ADD COLUMN IF NOT EXISTS source_sleeve text;

CREATE TABLE IF NOT EXISTS l2_account (
    strategy_id        bigint PRIMARY KEY REFERENCES l2_strategy(id),
    initial_cash       double precision NOT NULL,
    cash               double precision NOT NULL,
    nav                double precision NOT NULL,
    start_after_run_id bigint NOT NULL,
    last_fill_date     date,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS l2_position (
    strategy_id      bigint NOT NULL REFERENCES l2_strategy(id),
    ticker           text NOT NULL,
    qty              bigint NOT NULL DEFAULT 0 CHECK (qty >= 0),
    avg_cost         double precision NOT NULL DEFAULT 0.0,
    realized_pnl     double precision NOT NULL DEFAULT 0.0,
    last_price       double precision,
    last_price_date  date,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy_id, ticker)
);

ALTER TABLE l2_equity_daily ADD COLUMN IF NOT EXISTS nav double precision;
ALTER TABLE l2_equity_daily ADD COLUMN IF NOT EXISTS cash double precision;
ALTER TABLE l2_equity_daily ADD COLUMN IF NOT EXISTS market_value double precision;
ALTER TABLE l2_equity_daily ADD COLUMN IF NOT EXISTS cumulative_return double precision;

CREATE INDEX IF NOT EXISTS idx_l2_order_pending_continuous
    ON l2_order (strategy_id, signal_date) WHERE status = 'pending';
