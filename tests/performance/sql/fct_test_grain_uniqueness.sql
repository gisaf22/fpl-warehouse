-- Test: fct_player_performance_features has no duplicate (as_of_gw, fpl_id) rows.
--
-- Expectation: returns 0 rows.
-- A fanout here would cause duplicates in the materialised fact table even if
-- the INSERT deduplicates on primary key. Silent failure mode: a JOIN in per90
-- or a missing GROUP BY key in rolling produces multiple rows per player-GW.
SELECT
    as_of_gw,
    fpl_id,
    COUNT(*) AS n
FROM fct_player_performance_features
GROUP BY as_of_gw, fpl_id
HAVING n > 1
