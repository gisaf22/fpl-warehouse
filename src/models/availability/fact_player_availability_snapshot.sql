-- =============================================================================
-- Layer: fact_ (mart)
-- Model: fact_player_availability_snapshot
-- =============================================================================
--
-- Purpose:
--   Final PIT-safe snapshot table at grain (as_of_gw, fpl_id). Selects from
--   fct_player_availability_features and
--   orders columns to match the canonical warehouse schema spec exactly.
--
--   This layer contains no feature logic. All derivations live in fct_.
--   Any column order or aliasing changes belong here, not in fct_.
--
-- Grain:
--   One row per (as_of_gw, fpl_id).
--   Primary key: (as_of_gw, fpl_id) — enforced by the persisted snapshot table DDL.
--
-- PIT contract:
--   All feature values are bounded to round <= as_of_gw, enforced by the
--   int_ layer.
--
-- This query is executed as:
--   INSERT INTO fact_player_availability_snapshot <this file>
--
-- Source:
--   fct_player_availability_features  — ref: fct_player_availability_features
--
-- Future dbt migration:
--   Replace this file with a dbt model configured as materialized='table'.
--   Replace the table reference with {{ ref('fct_player_availability_features') }}.
--   The INSERT is replaced by dbt's model write — remove it.
-- =============================================================================

SELECT
    as_of_gw,
    fpl_id,
    team_fpl_id,

    -- Recent usage
    last_gw_minutes AS minutes_last_gw,
    last_gw_started AS started_last_gw_flag,
    minutes_last_3gws AS minutes_total_last_3gws,
    minutes_last_5gws AS minutes_total_last_5gws,
    starts_last_3gws AS starts_count_last_3gws,
    starts_last_5gws AS starts_count_last_5gws,
    appearances_last_3gws AS appearances_count_last_3gws,
    appearances_last_5gws AS appearances_count_last_5gws,
    appearances_count_last_3_apps,
    avg_minutes_last_3gws AS minutes_avg_last_3gws,
    avg_minutes_last_5gws AS minutes_avg_last_5gws,
    minutes_volatility_5gws AS minutes_std_last_5gws,
    max_minutes_last_5gws AS minutes_max_last_5gws,
    min_minutes_when_in_squad_last_5gws AS minutes_min_when_in_squad_last_5gws,

    -- Rate / trend
    start_rate_last_3gws AS starts_rate_last_3gws,
    start_rate_last_5gws AS starts_rate_last_5gws,
    appearance_rate_last_5gws AS appearances_rate_last_5gws,
    starts_per_appearance_last_5gws,
    sub_appearances_last_5gws AS sub_appearances_count_last_5gws,
    sub_rate_last_5gws AS sub_appearances_rate_last_5gws,
    minutes_delta_3v5 AS minutes_avg_delta_last_3gws_vs_last_5gws,
    starts_delta_3v5 AS starts_rate_delta_last_3gws_vs_last_5gws

FROM fct_player_availability_features   -- ref: fct_player_availability_features
