-- Test: opponent_team_fpl_id must be NULL for BGW and DGW rows.
--
-- Expectation: returns 0 rows.
-- When fixture_count != 1 there is no single opponent. Storing a non-NULL
-- opponent would misrepresent the fixture context.
SELECT as_of_gw, team_fpl_id, fixture_count, opponent_team_fpl_id
FROM fact_team_fixture_snapshot
WHERE
    fixture_count != 1
    AND opponent_team_fpl_id IS NOT NULL
