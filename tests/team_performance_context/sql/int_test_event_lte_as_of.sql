-- Test: int_team_fixture_base must not include matches from events after as_of_gw.
--
-- Expectation: returns 0 rows.
SELECT as_of_gw, team_fpl_id, event, understat_match_id
FROM int_team_fixture_base
WHERE event > as_of_gw