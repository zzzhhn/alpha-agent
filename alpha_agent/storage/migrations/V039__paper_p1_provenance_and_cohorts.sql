-- Paper-trading P1: auditable pick provenance, pending-order reservations,
-- explicit transaction costs, and reset cohorts. Additive columns keep the
-- migration small enough for Neon; existing rows remain cohort 0.

ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS source_run_id bigint
    REFERENCES research_run(id);
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS source_policy_id text;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS source_payload_hash text;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS reserved_notional double precision
    NOT NULL DEFAULT 0.0;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS fee_bps double precision
    NOT NULL DEFAULT 10.0;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS transaction_cost double precision
    NOT NULL DEFAULT 0.0;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS cohort_id int NOT NULL DEFAULT 0;

ALTER TABLE sim_position ADD COLUMN IF NOT EXISTS cohort_id int NOT NULL DEFAULT 0;
ALTER TABLE sim_position DROP CONSTRAINT IF EXISTS sim_position_account_id_ticker_key;
ALTER TABLE sim_position ADD CONSTRAINT sim_position_account_cohort_ticker_key
    UNIQUE (account_id, cohort_id, ticker);

ALTER TABLE sim_equity_daily ADD COLUMN IF NOT EXISTS cohort_id int NOT NULL DEFAULT 0;
ALTER TABLE sim_equity_daily
    DROP CONSTRAINT IF EXISTS sim_equity_daily_account_id_as_of_date_key;
ALTER TABLE sim_equity_daily ADD CONSTRAINT sim_equity_daily_account_cohort_date_key
    UNIQUE (account_id, cohort_id, as_of_date);

CREATE INDEX IF NOT EXISTS idx_sim_order_account_cohort_status
    ON sim_order (account_id, cohort_id, status);
CREATE INDEX IF NOT EXISTS idx_sim_position_account_cohort
    ON sim_position (account_id, cohort_id) WHERE qty > 0;

ALTER TABLE l2_equity_daily ADD COLUMN IF NOT EXISTS rsp_return double precision;
