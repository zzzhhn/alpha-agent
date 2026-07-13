-- Persist BLEND provenance: a mined candidate stitched together from two real
-- parent alphas (mining_loop's family_focus == "blend" round) is otherwise
-- indistinguishable from any other row of its family once written — the
-- in-memory blend_parents map never reached the DB, so the UI had no way to
-- tag/color a blend or show its parents. NULL = not a blend (or provenance
-- unknown for pre-existing rows); non-null = the list of parent expressions.
-- `is_blend` is intentionally NOT a stored column — it's derived from this
-- JSONB at read time (store._decode_row) so it can never drift from the list.
-- Additive, nullable (old rows valid).
ALTER TABLE brain_alphas ADD COLUMN IF NOT EXISTS blend_parents JSONB;
