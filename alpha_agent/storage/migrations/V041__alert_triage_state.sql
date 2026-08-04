-- Per-user alert triage state. The alert payload remains in alert_queue;
-- this narrow table stores only the user's reversible workflow decision.

CREATE TABLE IF NOT EXISTS alert_triage_state (
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id      bigint NOT NULL REFERENCES alert_queue(id) ON DELETE CASCADE,
    status        text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'snoozed', 'resolved')),
    snooze_until  timestamptz,
    resolved_at   timestamptz,
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_alert_triage_user_open
    ON alert_triage_state (user_id, status, updated_at DESC)
    WHERE status IN ('open', 'snoozed');
