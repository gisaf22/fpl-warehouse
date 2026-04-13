-- Test: velocity features must be NULL when as_of_gw < 4.
--
-- Expectation: returns 0 rows.
-- Velocity uses a 3-GW lag (round = as_of_gw - 3). Before GW 4 there is no
-- round 0 or earlier, so any non-NULL velocity at as_of_gw < 4 would be a
-- PIT violation — it would imply data from before the season started.
SELECT as_of_gw, fpl_id, price_delta_last_3gws, ownership_delta_last_3gws
FROM fact_player_market_snapshot
WHERE
    as_of_gw < 4
    AND (
        price_delta_last_3gws IS NOT NULL
        OR ownership_delta_last_3gws IS NOT NULL
    )
