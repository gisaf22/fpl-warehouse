-- Test: minutes_volatility_5gws is non-negative where not NULL.
--
-- Expectation: returns 0 rows.
-- Standard deviation is always >= 0 mathematically, but floating-point
-- rounding in SQRT(AVG(x²) - AVG(x)²) can produce tiny negative values
-- (e.g., -1e-15) when all minutes are identical. This test catches such
-- cases before they propagate as NaN or negative downstream features.
SELECT as_of_gw, fpl_id, minutes_volatility_5gws
FROM fct_player_availability_features
WHERE minutes_volatility_5gws < 0
