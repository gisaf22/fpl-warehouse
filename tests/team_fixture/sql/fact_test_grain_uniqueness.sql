-- Test: fact_team_fixture_snapshot has no duplicate (as_of_gw, team_fpl_id) rows.
--
-- Expectation: returns 0 rows.
SELECT
    as_of_gw,
    team_fpl_id,
    COUNT(*) AS n
FROM fact_team_fixture_snapshot
GROUP BY as_of_gw, team_fpl_id
HAVING n > 1
