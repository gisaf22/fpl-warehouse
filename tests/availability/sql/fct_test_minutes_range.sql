-- Test (distribution sanity): last_gw_minutes is between 0 and 90 where not NULL.
--
-- Expectation: returns 0 rows.
-- Failure means: a player's last GW minutes is outside the valid range for a
-- single 90-minute match. Values > 90 indicate source data corruption in
-- fact_player_gw. Values < 0 indicate a COALESCE or arithmetic error.
-- Extra time (up to 120 min) is not tracked at the GW level in FPL data.
SELECT as_of_gw, fpl_id, last_gw_minutes
FROM fct_player_availability_features
WHERE
    last_gw_minutes IS NOT NULL
    AND (last_gw_minutes < 0 OR last_gw_minutes > 90)
