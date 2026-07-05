-- One-off backfill: rows mined before the grade column existed have grade NULL.
-- The user verified on the BRAIN platform that the successful (passed/flagged)
-- mined alphas are graded AVERAGE, so fill those. rejected/sim_error rows are
-- left NULL on purpose — their platform grade isn't AVERAGE (or they have no
-- alpha at all), so filling them would be inaccurate. Idempotent (only NULLs);
-- a no-op on fresh DBs.
UPDATE brain_alphas
   SET grade = 'AVERAGE'
 WHERE grade IS NULL
   AND alpha_id IS NOT NULL
   AND outcome IN ('passed', 'flagged');
