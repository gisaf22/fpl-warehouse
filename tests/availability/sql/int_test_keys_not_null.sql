-- Test: int_player_gw_base has no NULL values in key columns.
--
-- Expectation: returns 0 rows.
-- Failure means: a join produced a NULL key, corrupting downstream grain.
-- as_of_gw, fpl_id, round: composite grain key.
-- team_fpl_id: required for rate denominator joins in the fct_ layer.
SELECT as_of_gw, fpl_id, team_fpl_id, round
FROM int_player_gw_base
WHERE
    as_of_gw   IS NULL
    OR fpl_id  IS NULL
    OR team_fpl_id IS NULL
    OR round   IS NULL
