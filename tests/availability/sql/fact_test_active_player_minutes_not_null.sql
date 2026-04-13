-- Test: players with at least one appearance in the 5-GW window have non-NULL
-- minutes features.
--
-- Expectation: returns 0 rows.
-- If a player has appearances_count_last_5gws > 0, they played in at least one GW
-- within the window, so minutes_total_last_5gws must be a real value (>= 1).
-- NULL here would mean the LEFT JOIN to fact_player_gw produced no rows
-- despite the appearances count being positive, which is contradictory.
SELECT as_of_gw, fpl_id, appearances_count_last_5gws, minutes_total_last_5gws
FROM fact_player_availability_snapshot
WHERE
    appearances_count_last_5gws > 0
    AND minutes_total_last_5gws IS NULL
