-- Test: fact_player_availability_snapshot has no duplicate (as_of_gw, fpl_id) rows.
--
-- Expectation: returns 0 rows.
-- This is the primary key contract for the snapshot table. Duplicates would
-- corrupt any downstream join on (as_of_gw, fpl_id) by producing fanout.
-- Silent failure mode: fct_ view returns multiple rows per (as_of_gw, fpl_id)
-- due to a missing GROUP BY key or a fanout in team_window_counts.
SELECT
    as_of_gw,
    fpl_id,
    COUNT(*) AS n
FROM fact_player_availability_snapshot
GROUP BY as_of_gw, fpl_id
HAVING n > 1
