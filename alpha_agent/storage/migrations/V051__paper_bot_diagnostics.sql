-- Additive observability only. Existing cash, holdings, BYOK and schedules stay unchanged.
ALTER TABLE sim_bot_run ADD COLUMN IF NOT EXISTS diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE sim_bot_position_note ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS sim_bot_run_session ON sim_bot_run(account_id,trading_session);
CREATE TABLE IF NOT EXISTS sim_bot_schedule_slot (
    account_id bigint NOT NULL REFERENCES sim_account(id),
    session_date date NOT NULL,
    slot text NOT NULL CHECK(slot IN ('open_after','close_before')),
    planned_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    config_version integer NOT NULL,
    status text NOT NULL CHECK(status IN ('planned','enqueued','blocked','missed')),
    reason text,
    run_id uuid REFERENCES sim_bot_run(id),
    PRIMARY KEY(account_id,session_date,slot)
);
