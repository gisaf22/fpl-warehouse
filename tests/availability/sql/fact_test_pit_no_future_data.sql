-- Test: no feature in a row uses data from rounds after as_of_gw.
--
-- Expectation: returns 0 rows.
-- Proxy check: minutes_last_gw for a row at as_of_gw = N must be NULL or
-- match the player's minutes in fact_player_gw at round = N only.
-- If minutes_last_gw > 0 but the player had 0 minutes at round = N in the
-- source, it means the MAX(CASE WHEN round = as_of_gw ...) leaked a value
-- from a different round boundary.
--
-- This is a targeted PIT probe, not an exhaustive check. It tests that the
-- last-GW value is consistent with the source for the exact as_of_gw round.
SELECT
    s.as_of_gw,
    s.fpl_id,
    s.minutes_last_gw         AS snapshot_minutes_last_gw,
    COALESCE(pg.minutes, 0)   AS source_minutes
FROM fact_player_availability_snapshot s
LEFT JOIN fact_player_gw pg
    ON  pg.fpl_id = s.fpl_id
    AND pg.round  = s.as_of_gw
WHERE
    -- minutes_last_gw disagrees with the source for that exact round
    s.minutes_last_gw IS NOT NULL
    AND s.minutes_last_gw != COALESCE(pg.minutes, 0)
