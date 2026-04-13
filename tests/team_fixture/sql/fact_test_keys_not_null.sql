-- Test: primary key columns are never NULL.
--
-- Expectation: returns 0 rows.
SELECT as_of_gw, team_fpl_id
FROM fact_team_fixture_snapshot
WHERE
    as_of_gw    IS NULL
    OR team_fpl_id IS NULL
