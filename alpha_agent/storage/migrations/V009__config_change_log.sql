-- V009__config_change_log.sql (2026-05-19)
--
-- Append-only audit log of user-facing config edits (BYOK provider /
-- model / base_url, future signal weight overrides). Drives the B9
-- diff card + 1-click rollback UI in /settings.
--
-- rollback_of points back at the change_log row this rollback undoes,
-- so the user-facing list can render "↶ rolled back from #42" annotations
-- without a separate join.
--
-- old_value / new_value are stored as text — for non-secret fields only.
-- Secret material (api_key ciphertext + nonce) is intentionally NOT
-- logged here; the BYOK route hooks record the non-secret coordinates
-- (provider / model / base_url) only.
CREATE TABLE IF NOT EXISTS config_change_log (
    id BIGSERIAL PRIMARY KEY,
    user_id integer NOT NULL,
    field text NOT NULL,
    old_value text,
    new_value text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL DEFAULT 'manual',
    rollback_of bigint REFERENCES config_change_log(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_config_change_log_user_changed
    ON config_change_log (user_id, changed_at DESC);
