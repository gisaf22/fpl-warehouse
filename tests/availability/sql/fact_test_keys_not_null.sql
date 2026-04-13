-- Test: primary key columns and team identifier are never NULL.
--
-- Expectation: returns 0 rows.
-- as_of_gw, fpl_id: NULL in any of these breaks the table's primary
-- key and makes all downstream joins on this grain silently incorrect.
-- team_fpl_id: NULL means the player could not be matched to a team in
-- dim_players, which would make rate denominator joins silently return NULL.
SELECT as_of_gw, fpl_id, team_fpl_id
FROM fact_player_availability_snapshot
WHERE
    as_of_gw   IS NULL
    OR fpl_id    IS NULL
    OR team_fpl_id IS NULL
