-- Test: BGW/DGW flags are consistent with fixture_count.
--
-- Expectation: returns 0 rows.
-- upcoming_bgw_flag = 1 iff fixture_count = 0.
-- upcoming_dgw_flag = 1 iff fixture_count > 1.
-- They must never both be 1.
SELECT as_of_gw, team_fpl_id, fixture_count, upcoming_bgw_flag, upcoming_dgw_flag
FROM fact_team_fixture_snapshot
WHERE
    -- BGW flag set but fixture_count != 0
    (upcoming_bgw_flag = 1 AND fixture_count != 0)
    OR
    -- DGW flag set but fixture_count <= 1
    (upcoming_dgw_flag = 1 AND fixture_count <= 1)
    OR
    -- Both flags set simultaneously
    (upcoming_bgw_flag = 1 AND upcoming_dgw_flag = 1)
    OR
    -- fixture_count = 0 but BGW flag not set
    (fixture_count = 0 AND upcoming_bgw_flag != 1)
    OR
    -- fixture_count > 1 but DGW flag not set
    (fixture_count > 1 AND upcoming_dgw_flag != 1)
