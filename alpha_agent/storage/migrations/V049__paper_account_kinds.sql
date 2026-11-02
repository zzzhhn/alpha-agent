-- Preserve all existing account IDs, cash, reset cohorts and ledger references.
-- Defaults classify every old account as human without rebuilding its history.
ALTER TABLE sim_account ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'human'
    CHECK (kind IN ('human', 'bot'));
ALTER TABLE sim_account ADD COLUMN IF NOT EXISTS name text NOT NULL DEFAULT 'Human account';
ALTER TABLE sim_account ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'paused', 'disabled'));

ALTER TABLE sim_account DROP CONSTRAINT IF EXISTS sim_account_user_id_key;
ALTER TABLE sim_account ADD CONSTRAINT sim_account_user_kind_key UNIQUE (user_id, kind);
