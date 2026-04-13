-- Test: minutes_last_3gws <= minutes_last_5gws for all rows.
--
-- Expectation: returns 0 rows.
-- Failure means: the 3-GW sum exceeds the 5-GW sum, which is structurally
-- impossible because the 3-GW window is a strict subset of the 5-GW window.
-- Silent failure mode: wrong round boundary in the CASE expression.
SELECT as_of_gw, fpl_id, minutes_last_3gws, minutes_last_5gws
FROM fct_player_availability_features
WHERE minutes_last_3gws > minutes_last_5gws
