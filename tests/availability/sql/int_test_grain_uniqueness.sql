-- Test: int_player_gw_base has no duplicate (as_of_gw, fpl_id, round) rows.
--
-- Expectation: returns 0 rows.
-- Failure means: a player appears more than once per (GW, round) combination,
-- which would inflate all downstream fct_ aggregations.
SELECT
    as_of_gw,
    fpl_id,
    round,
    COUNT(*) AS n
FROM int_player_gw_base
GROUP BY as_of_gw, fpl_id, round
HAVING n > 1
