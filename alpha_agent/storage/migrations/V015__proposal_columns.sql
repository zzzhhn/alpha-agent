-- alpha_agent/storage/migrations/V015__proposal_columns.sql (2026-05-22)
-- Phase 2a: the methodology proposer queues candidates as pending rows in
-- config_change_log. status: NULL for the existing auto-tier / manual rows,
-- 'pending'|'approved'|'rejected' for proposer rows. evidence: the Sharpe/IC
-- distribution + Deflated-Sharpe + trial count behind the proposal.
ALTER TABLE config_change_log
    ADD COLUMN IF NOT EXISTS status text,
    ADD COLUMN IF NOT EXISTS evidence jsonb;

CREATE INDEX IF NOT EXISTS idx_config_change_log_status
    ON config_change_log (status) WHERE status = 'pending';
