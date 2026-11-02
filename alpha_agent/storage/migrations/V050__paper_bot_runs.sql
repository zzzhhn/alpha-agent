-- Additive bot state; no existing account, position or fill is rewritten.
CREATE TABLE IF NOT EXISTS sim_bot_config (
    account_id bigint PRIMARY KEY REFERENCES sim_account(id),
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    config_version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sim_bot_run (
    id uuid PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES sim_account(id),
    trigger text NOT NULL,
    slot_key text UNIQUE,
    trading_session date NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    stage text NOT NULL DEFAULT 'queued',
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    expires_at timestamptz NOT NULL,
    lease_until timestamptz,
    lease_token uuid,
    config_version integer NOT NULL,
    config_snapshot jsonb NOT NULL,
    context jsonb,
    result jsonb,
    summary text NOT NULL DEFAULT '',
    error text,
    provider text,
    model text,
    prompt_tokens integer NOT NULL DEFAULT 0,
    completion_tokens integer NOT NULL DEFAULT 0,
    llm_calls integer NOT NULL DEFAULT 0,
    CHECK (status IN ('queued','running','completed','no_trade','partial','failed','skipped','stopped'))
);
CREATE UNIQUE INDEX IF NOT EXISTS sim_bot_one_active_run ON sim_bot_run(account_id)
    WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS sim_bot_run_history ON sim_bot_run(account_id,created_at DESC);
CREATE INDEX IF NOT EXISTS sim_bot_run_queue ON sim_bot_run(created_at)
    WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS sim_bot_position_note (
    account_id bigint NOT NULL REFERENCES sim_account(id),
    ticker text NOT NULL,
    note text NOT NULL,
    run_id uuid NOT NULL REFERENCES sim_bot_run(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(account_id,ticker)
);
CREATE TABLE IF NOT EXISTS sim_instrument (
    id bigserial PRIMARY KEY,
    ticker text NOT NULL UNIQUE,
    identity_status text NOT NULL DEFAULT 'supported_universe',
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS bot_run_id uuid REFERENCES sim_bot_run(id);
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS action_id text;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS instrument_id bigint REFERENCES sim_instrument(id);
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS execution_model text NOT NULL DEFAULT 'daily_close_v1';
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS cancel_requested_at timestamptz;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS reference_price double precision;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS slippage_bps double precision NOT NULL DEFAULT 0;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS execution_evidence jsonb;
ALTER TABLE sim_order ADD COLUMN IF NOT EXISTS fail_reason text;
ALTER TABLE sim_order DROP CONSTRAINT IF EXISTS sim_order_status_check;
ALTER TABLE sim_order ADD CONSTRAINT sim_order_status_check
    CHECK (status IN ('pending','filled','expired','cancelled','failed'));
CREATE UNIQUE INDEX IF NOT EXISTS sim_bot_action_once ON sim_order(bot_run_id,action_id)
    WHERE bot_run_id IS NOT NULL;
ALTER TABLE sim_position ADD COLUMN IF NOT EXISTS instrument_id bigint REFERENCES sim_instrument(id);
ALTER TABLE sim_position ADD COLUMN IF NOT EXISTS mark_price double precision;
ALTER TABLE sim_position ADD COLUMN IF NOT EXISTS mark_at timestamptz;
ALTER TABLE sim_position ADD COLUMN IF NOT EXISTS price_quality text;
ALTER TABLE sim_equity_daily ADD COLUMN IF NOT EXISTS valuation_quality text;
ALTER TABLE sim_equity_daily ADD COLUMN IF NOT EXISTS valued_at timestamptz;
ALTER TABLE sim_equity_daily ALTER COLUMN portfolio_value DROP NOT NULL;
ALTER TABLE sim_equity_daily ALTER COLUMN unrealized_pnl DROP NOT NULL;
