-- alpha_agent/storage/migrations/V016__factor_proposals.sql (2026-05-23)
-- Phase 3a foundation: the LLM factor invention substrate. Two tables:
--   factor_proposals  : one row per LLM-generated candidate; status enum +
--                       structured evidence/diagnostic jsonb so the UI can
--                       render Approve/Reject without re-querying.
--   extended_operators: approved operator names registered for AST whitelist
--                       acceptance; runtime dispatch goes through the Phase 3b
--                       subprocess sandbox, never inlined.

CREATE TABLE IF NOT EXISTS factor_proposals (
    id              bigserial PRIMARY KEY,
    status          text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected')),
    expression      text NOT NULL,
    new_operators   jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence        jsonb NOT NULL,
    diagnostic      jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    decided_at      timestamptz,
    decided_by      bigint
);

CREATE INDEX IF NOT EXISTS idx_factor_proposals_status_created
    ON factor_proposals (status, created_at DESC);

CREATE TABLE IF NOT EXISTS extended_operators (
    name                text PRIMARY KEY,
    signature           text NOT NULL,
    python_impl         text NOT NULL,
    doc                 text,
    registered_at       timestamptz NOT NULL DEFAULT now(),
    registered_by       bigint NOT NULL,
    source_proposal_id  bigint REFERENCES factor_proposals(id)
);

CREATE INDEX IF NOT EXISTS idx_extended_operators_registered_at
    ON extended_operators (registered_at DESC);
