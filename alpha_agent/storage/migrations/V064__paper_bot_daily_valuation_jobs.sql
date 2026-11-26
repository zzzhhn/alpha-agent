-- Add resumable daily valuation receipts without modifying existing equity data.
CREATE TABLE IF NOT EXISTS sim_bot_valuation_job (
    session_date date NOT NULL,
    account_id bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    cohort_id int NOT NULL,
    status text NOT NULL CHECK (status IN ('pending','running','deferred','completed','skipped')),
    attempts int NOT NULL DEFAULT 0,
    reason text,
    valuation_quality text,
    claim_token uuid,
    lease_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_date, account_id, cohort_id)
);

CREATE INDEX IF NOT EXISTS idx_sim_bot_valuation_job_open
    ON sim_bot_valuation_job (session_date, account_id, cohort_id)
    WHERE status IN ('pending','running','deferred');
