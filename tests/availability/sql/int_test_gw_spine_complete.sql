-- Test: every finished GW in fact_fixtures has at least one player row in
-- int_player_gw_base.
--
-- Expectation: returns 0 rows.
-- Failure means: a finished GW was dropped entirely, leaving a gap in the
-- historical snapshot that would silently exclude players for that GW.
SELECT f.event AS as_of_gw
FROM fact_fixtures f
WHERE f.finished = 1
GROUP BY f.event
HAVING f.event NOT IN (
    SELECT DISTINCT as_of_gw FROM int_player_gw_base
)
