-- New decisions bind their applied and rollback records. Historical decisions
-- retain NULL pointers and require review before they can be reverted.
ALTER TABLE config_change_log
    ADD COLUMN IF NOT EXISTS applied_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS supersedes_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rollback_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL;

ALTER TABLE factor_proposals
    ADD COLUMN IF NOT EXISTS applied_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS rollback_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL;

ALTER TABLE engine_config
    ADD COLUMN IF NOT EXISTS current_change_id bigint
        REFERENCES config_change_log(id) ON DELETE SET NULL;

-- A legacy or out-of-band writer may replace value without advancing the
-- pointer. Even an identical value written that way has unverified lineage.
CREATE OR REPLACE FUNCTION invalidate_unversioned_engine_config_write()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.current_change_id IS NOT DISTINCT FROM OLD.current_change_id THEN
        NEW.current_change_id := NULL;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS engine_config_requires_new_version ON engine_config;
CREATE TRIGGER engine_config_requires_new_version BEFORE UPDATE OF value ON engine_config
    FOR EACH ROW EXECUTE FUNCTION invalidate_unversioned_engine_config_write();

-- A rollback to an unconfigured key deletes its live row. Its journal
-- timestamp gives cache refreshes a revision for the absence.
CREATE INDEX IF NOT EXISTS idx_config_change_log_engine_unset
    ON config_change_log (field, changed_at DESC)
    WHERE source = 'rollback' AND new_value IS NULL AND supersedes_change_id IS NOT NULL;
