-- =============================================================================
-- Layer: fct_ (feature)
-- Model: fct_player_performance_features
-- =============================================================================
--
-- Purpose:
--   Derives normalized on-pitch performance rates for each
--   (as_of_gw, fpl_id) combination. One row per player per finished GW.
--
-- Grain:
--   One row per (as_of_gw, fpl_id). Aggregated from int_player_gw_base rows.
--
-- PIT contract:
--   All features use fact_player_gw rows with round <= as_of_gw, inherited
--   from int_player_gw_base. No feature references round > as_of_gw.
--
-- Feature groups:
--   1. Per-90 rates (Window 1 = last 5 calendar rounds)
--      xgi_per90, xg_per90, xa_per90, threat_per90, creativity_per90,
--      ict_per90, cbi_per90, dc_per90, gc_per90, xgc_per90, cs_pct
--
-- Window contract:
--   Window 1: rn_calendar <= 5 (calendar rounds, regardless of minutes played).
--
-- Null/default policy:
--   Per-90 rates: NULL when SUM(minutes) < 45 in Window 1 (insufficient sample).
--   cs_pct: NULL when no historical rows are available in the window.
--
-- Source tables:
--   int_player_gw_base  — ref: int_player_gw_base (int_ layer)
--
-- Future dbt migration:
--   Replace this file with a dbt model. Swap table references with
--   {{ ref('int_player_gw_base') }}.
--   Remove CREATE VIEW and configure with materialized='view' or 'ephemeral'.
-- =============================================================================

CREATE VIEW IF NOT EXISTS fct_player_performance_features AS

WITH

-- Window 1: last 5 calendar rounds — per-90 rates
window_1 AS (
    SELECT *
    FROM int_player_gw_base
    WHERE rn_calendar <= 5
),

-- Per-90 rates from Window 1
per90 AS (
    SELECT
        as_of_gw,
        fpl_id,
        team_fpl_id,
        COUNT(*)        AS gws_in_window,
        SUM(minutes)    AS total_minutes_w1,
        -- Attacking rates: NULL when total minutes < 45
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(us_xgi, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS xgi_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(us_xg, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS xg_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(us_xa, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS xa_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(threat, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS threat_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(creativity, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS creativity_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(ict_index, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS ict_per90,
        -- Defensive rates
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(clearances_blocks_interceptions, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS cbi_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(defensive_contribution, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS dc_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(goals_conceded, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS gc_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(expected_goals_conceded, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS xgc_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(bonus, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS bonus_per90,
        CASE WHEN SUM(minutes) >= 45
            THEN SUM(COALESCE(bps, 0)) * 90.0 / SUM(minutes)
            ELSE NULL END AS bps_per90,
        -- Clean sheet percentage: fraction of window games with clean_sheets = 1
        CAST(SUM(COALESCE(clean_sheets, 0)) AS REAL) / COUNT(*) AS cs_pct
    FROM window_1
    GROUP BY as_of_gw, fpl_id, team_fpl_id
),

appearance_rows AS (
    SELECT
        as_of_gw,
        fpl_id,
        team_fpl_id,
        round,
        total_points,
        us_xgi,
        threat,
        creativity,
        ROW_NUMBER() OVER (
            PARTITION BY as_of_gw, fpl_id
            ORDER BY round DESC
        ) AS rn_app
    FROM int_player_gw_base
    WHERE minutes > 0
),

appearance_last_3 AS (
    SELECT *
    FROM appearance_rows
    WHERE rn_app <= 3
),

appearance_metrics AS (
    SELECT
        as_of_gw,
        fpl_id,
        team_fpl_id,
        SUM(COALESCE(total_points, 0)) AS points_total_last_3_apps,
        AVG(total_points) AS points_avg_last_3_apps,
        CASE WHEN COUNT(*) >= 2
            THEN SQRT(AVG(total_points * total_points) - AVG(total_points) * AVG(total_points))
            ELSE NULL END AS points_std_last_3_apps,
        SUM(COALESCE(us_xgi, 0)) AS xgi_total_last_3_apps,
        AVG(threat) AS threat_avg_last_3_apps,
        AVG(creativity) AS creativity_avg_last_3_apps
    FROM appearance_last_3
    GROUP BY as_of_gw, fpl_id, team_fpl_id
),

last_gw AS (
    SELECT
        as_of_gw,
        fpl_id,
        team_fpl_id,
        threat AS threat_last_gw,
        creativity AS creativity_last_gw,
        ict_index AS ict_last_gw
    FROM int_player_gw_base
    WHERE rn_calendar = 1
),

last_app AS (
    SELECT
        as_of_gw,
        fpl_id,
        total_points AS points_last_app
    FROM appearance_rows
    WHERE rn_app = 1
),

prev_two_apps AS (
    SELECT
        as_of_gw,
        fpl_id,
        AVG(total_points) AS points_avg_prev_2_apps
    FROM appearance_rows
    WHERE rn_app BETWEEN 2 AND 3
    GROUP BY as_of_gw, fpl_id
),

spine AS (
    SELECT DISTINCT as_of_gw, fpl_id, team_fpl_id
    FROM int_player_gw_base
)

SELECT
    s.as_of_gw,
    s.fpl_id,
    s.team_fpl_id,
    -- Per-90 rates (Window 1)
    p.xgi_per90,
    p.xg_per90,
    p.xa_per90,
    p.threat_per90,
    p.creativity_per90,
    p.ict_per90,
    p.cbi_per90,
    p.dc_per90,
    p.gc_per90,
    p.xgc_per90,
    p.bonus_per90,
    p.bps_per90,
    p.cs_pct,
    a.points_total_last_3_apps,
    a.points_avg_last_3_apps,
    a.points_std_last_3_apps,
    a.xgi_total_last_3_apps,
    lg.threat_last_gw,
    lg.creativity_last_gw,
    lg.ict_last_gw,
    la.points_last_app,
    p2.points_avg_prev_2_apps,
    a.threat_avg_last_3_apps,
    a.creativity_avg_last_3_apps
FROM spine s
LEFT JOIN per90 p
    ON p.as_of_gw = s.as_of_gw AND p.fpl_id = s.fpl_id
LEFT JOIN appearance_metrics a
    ON a.as_of_gw = s.as_of_gw AND a.fpl_id = s.fpl_id
LEFT JOIN last_gw lg
    ON lg.as_of_gw = s.as_of_gw AND lg.fpl_id = s.fpl_id
LEFT JOIN last_app la
    ON la.as_of_gw = s.as_of_gw AND la.fpl_id = s.fpl_id
LEFT JOIN prev_two_apps p2
    ON p2.as_of_gw = s.as_of_gw AND p2.fpl_id = s.fpl_id
