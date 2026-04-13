-- Test: fixture_count is non-negative and at most 2 (EPL scheduling constraint).
--
-- Expectation: returns 0 rows.
-- A DGW has 2 fixtures, a BGW has 0, a standard GW has 1.
-- fixture_count > 2 would indicate a data error.
SELECT as_of_gw, team_fpl_id, fixture_count
FROM fact_team_fixture_snapshot
WHERE fixture_count < 0 OR fixture_count > 2
