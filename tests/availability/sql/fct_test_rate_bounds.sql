-- Test: rate features are bounded [0, 1] where not NULL.
--
-- Expectation: returns 0 rows.
-- Upper bound of 1.0 is not enforced for start_rate: in DGWs, fact_player_gw
-- aggregates two fixtures into one round row. If `starts` counts both
-- fixtures (starts = 2), rate denominator = 1 GW → start_rate = 2.0.
-- This is a known upstream grain constraint for start_rate only.
-- appearance_rate is fully bounded: a player cannot appear in more GWs than
-- their team played.
SELECT 'start_rate_last_3gws < 0' AS failure, as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE start_rate_last_3gws < 0
UNION ALL
SELECT 'start_rate_last_5gws < 0', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE start_rate_last_5gws < 0
UNION ALL
SELECT 'appearance_rate_last_5gws < 0', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE appearance_rate_last_5gws < 0
UNION ALL
SELECT 'appearance_rate_last_5gws > 1', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE appearance_rate_last_5gws > 1
UNION ALL
SELECT 'starts_per_appearance_last_5gws < 0', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE starts_per_appearance_last_5gws < 0
UNION ALL
SELECT 'starts_per_appearance_last_5gws > 1', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE starts_per_appearance_last_5gws > 1
UNION ALL
SELECT 'sub_rate_last_5gws < 0', as_of_gw, fpl_id
FROM fct_player_availability_features
WHERE sub_rate_last_5gws < 0
