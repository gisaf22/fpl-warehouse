-- =============================================================================
-- Layer: fact_ (mart)
-- Model: fact_player_performance_snapshot
-- =============================================================================
--
-- Purpose:
--   Final SELECT from fct_player_performance_features. This layer adds no
--   logic — it projects the fct_ view columns into the materialised table.
--
-- Grain:
--   One row per (as_of_gw, fpl_id). Primary key defined in DDL.
--
-- Orchestration:
--   Executed via INSERT INTO fact_player_performance_snapshot <this file>
--   by the snapshot materializer after the table is created from the canonical
--   warehouse schema spec.
--
-- Future dbt migration:
--   Replace with a dbt model using {{ ref('fct_player_performance_features') }}.
-- =============================================================================

SELECT
    as_of_gw,
    fpl_id,
    team_fpl_id,
    xgi_per90 AS xgi_per90_last_5gws,
    xg_per90 AS xg_per90_last_5gws,
    xa_per90 AS xa_per90_last_5gws,
    threat_per90 AS threat_per90_last_5gws,
    creativity_per90 AS creativity_per90_last_5gws,
    ict_per90 AS ict_per90_last_5gws,
    cbi_per90 AS cbi_per90_last_5gws,
    dc_per90 AS dc_per90_last_5gws,
    gc_per90 AS gc_per90_last_5gws,
    xgc_per90 AS xgc_per90_last_5gws,
    cs_pct AS clean_sheet_rate_last_5gws,
    bonus_per90 AS bonus_per90_last_5gws,
    bps_per90 AS bps_per90_last_5gws,
    points_total_last_3_apps,
    points_avg_last_3_apps,
    points_std_last_3_apps,
    xgi_total_last_3_apps,
    threat_last_gw,
    creativity_last_gw,
    ict_last_gw,
    points_last_app,
    points_avg_prev_2_apps,
    threat_avg_last_3_apps,
    creativity_avg_last_3_apps
FROM fct_player_performance_features
