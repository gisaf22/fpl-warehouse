-- Test: starts cannot exceed appearances in either the 3-GW or 5-GW window.
--
-- Expectation: returns 0 rows.
-- Failure means: a player is recorded as having started more games than they
-- appeared in, which is structurally impossible (start implies appearance).
-- Silent failure mode: starts and appearances use mismatched filter conditions.
SELECT
    as_of_gw,
    fpl_id,
    starts_last_3gws,
    appearances_last_3gws,
    starts_last_5gws,
    appearances_last_5gws
FROM fct_player_availability_features
WHERE
    starts_last_3gws > appearances_last_3gws
    OR starts_last_5gws > appearances_last_5gws
