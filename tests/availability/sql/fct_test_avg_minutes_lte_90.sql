-- Test: average minutes per GW cannot exceed 90 (one full match).
--
-- Expectation: returns 0 rows.
-- Failure means: avg_minutes_last_3gws or avg_minutes_last_5gws is above 90,
-- which is impossible for a single player in a single 90-minute match.
-- Silent failure mode: minutes values in fact_player_gw contain bad data, or
-- the averaging window is applied to the wrong column.
SELECT
    as_of_gw,
    fpl_id,
    avg_minutes_last_3gws,
    avg_minutes_last_5gws
FROM fct_player_availability_features
WHERE
    avg_minutes_last_3gws > 90
    OR avg_minutes_last_5gws > 90
