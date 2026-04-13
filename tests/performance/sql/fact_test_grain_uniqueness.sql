-- Test: fact_player_performance_snapshot has no duplicate (as_of_gw, fpl_id) rows.
--
-- Expectation: returns 0 rows.
-- Duplicates would corrupt any downstream join on (as_of_gw, fpl_id).
SELECT
    as_of_gw,
    fpl_id,
    COUNT(*) AS n
FROM fact_player_performance_snapshot
GROUP BY as_of_gw, fpl_id
HAVING n > 1
