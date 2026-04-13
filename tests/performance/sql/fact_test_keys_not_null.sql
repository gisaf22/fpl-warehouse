-- Test: primary key columns and team identifier are never NULL.
--
-- Expectation: returns 0 rows.
-- NULL in as_of_gw or fpl_id breaks the primary key contract.
-- NULL in team_fpl_id makes rate denominator joins silently return NULL.
SELECT as_of_gw, fpl_id, team_fpl_id
FROM fact_player_performance_snapshot
WHERE
    as_of_gw    IS NULL
    OR fpl_id     IS NULL
    OR team_fpl_id IS NULL
