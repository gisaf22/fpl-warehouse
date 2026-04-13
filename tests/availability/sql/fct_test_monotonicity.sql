-- Test: logical monotonicity constraints on count and rate features.
--
-- Expectation: returns 0 rows.
-- Failure means:
--   starts > appearances      — a player cannot start more GWs than they appeared in
--   sub_appearances < 0       — sub count is derived as appearances - starts; must be >= 0
--   start_rate > appearance_rate — a player cannot start more GWs than they appeared in
--     (rate version of the same invariant; fires on join or aggregation bugs)
SELECT 'starts_last_5gws > appearances_last_5gws' AS failure, as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE starts_last_5gws > appearances_last_5gws
UNION ALL
SELECT 'sub_appearances_last_5gws < 0', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE sub_appearances_last_5gws < 0
UNION ALL
SELECT 'start_rate_last_5gws > appearance_rate_last_5gws', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE start_rate_last_5gws > appearance_rate_last_5gws
