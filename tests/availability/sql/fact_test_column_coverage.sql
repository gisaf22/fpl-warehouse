-- Test: count features with COALESCE defaults are never entirely NULL.
--
-- Expectation: returns 0 rows.
-- A fully NULL column indicates the column was dropped, renamed, or the
-- COALESCE was removed.
--
-- Legitimately nullable columns (excluded from this check):
--   minutes_last_gw, started_last_gw_flag                 — NULL for players who didn't play GW1
--   minutes_avg_last_3gws, minutes_avg_last_5gws         — NULL with no window data
--   minutes_std_last_5gws                                — NULL with < 3 observations
--   minutes_max_last_5gws                                — NULL when no game rows in window
--   minutes_min_when_in_squad_last_5gws                  — NULL when no game rows in window
--   starts_rate_last_3gws, starts_rate_last_5gws         — NULL when team played 0 GWs
--   appearances_rate_last_5gws                           — NULL when team played 0 GWs
--   starts_per_appearance_last_5gws                      — NULL when appearances = 0
--   sub_appearances_rate_last_5gws                       — NULL when team played 0 GWs
--   minutes_avg_delta_last_3gws_vs_last_5gws            — NULL when either avg is NULL
--   starts_rate_delta_last_3gws_vs_last_5gws            — NULL when either rate is NULL
SELECT 'minutes_total_last_3gws all null'   WHERE (SELECT COUNT(*) FROM fact_player_availability_snapshot WHERE minutes_total_last_3gws   IS NOT NULL) = 0
UNION ALL
SELECT 'minutes_total_last_5gws all null'   WHERE (SELECT COUNT(*) FROM fact_player_availability_snapshot WHERE minutes_total_last_5gws   IS NOT NULL) = 0
UNION ALL
SELECT 'starts_count_last_3gws all null'    WHERE (SELECT COUNT(*) FROM fact_player_availability_snapshot WHERE starts_count_last_3gws    IS NOT NULL) = 0
UNION ALL
SELECT 'starts_count_last_5gws all null'    WHERE (SELECT COUNT(*) FROM fact_player_availability_snapshot WHERE starts_count_last_5gws    IS NOT NULL) = 0
