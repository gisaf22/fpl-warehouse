-- =============================================================================
-- Layer: fct_ (feature)
-- Model: fct_player_market_features
-- =============================================================================
--
-- Purpose:
--   Derives FPL market signals — price, ownership, and transfer activity —
--   for each (as_of_gw, fpl_id) combination. One row per player per finished GW.
--
-- Grain:
--   One row per (as_of_gw, fpl_id). Derived from int_player_gw_base spine
--   joined to fact_player_gw for market columns.
--
-- PIT contract:
--   All features use fact_player_gw rows anchored at fixed rounds (as_of_gw
--   and as_of_gw - 3). No feature references round > as_of_gw.
--   The GW spine is inherited from int_player_gw_base (fact_fixtures.finished=1).
--
-- Feature groups:
--   1. Point-in-time state at as_of_gw
--      now_cost, selected_by, transfer_delta
--
--   2. Market velocity over last 3 GWs
--      price_velocity_3gw, ownership_velocity_3gw
--
-- Null policy:
--   now_cost, selected_by, transfer_delta: NULL when player has no
--     fact_player_gw row for round = as_of_gw.
--   price_velocity_3gw, ownership_velocity_3gw: NULL when as_of_gw < 4
--     or when either anchor round is missing from fact_player_gw.
--   0 is never used as a default for any column.
--
-- Source tables:
--   int_player_gw_base  — ref: int_player_gw_base (int_ layer, spine only)
--   fact_player_gw      — ref: fact_player_gw (value, selected, transfers)
--
-- Future dbt migration:
--   Replace this file with a dbt model. Swap table references with
--   {{ ref('int_player_gw_base') }} and {{ ref('fact_player_gw') }}.
--   Remove CREATE VIEW and configure with materialized='view' or 'ephemeral'.
-- =============================================================================

CREATE VIEW IF NOT EXISTS fct_player_market_features AS

WITH

-- Spine: one row per (as_of_gw, fpl_id) from the shared int_ layer.
-- Avoids re-deriving the finished-GW boundary and player/round filtering.
spine AS (
    SELECT DISTINCT as_of_gw, fpl_id
    FROM int_player_gw_base
),

-- Point-in-time anchor: fact_player_gw row at round = as_of_gw.
-- LEFT JOIN — NULL columns when the player has no row at that exact round.
anchor_now AS (
    SELECT
        s.as_of_gw,
        s.fpl_id,
        pg.value,
        pg.selected,
        pg.transfers_in,
        pg.transfers_out
    FROM spine s
    LEFT JOIN fact_player_gw pg   -- ref: fact_player_gw
        ON pg.fpl_id = s.fpl_id AND pg.round = s.as_of_gw
),

-- Lag anchor: fact_player_gw row at round = as_of_gw - 3.
-- Only produced for as_of_gw >= 4 — velocity is undefined before GW 4.
-- LEFT JOIN — NULL columns when the player has no row at that exact round.
anchor_lag AS (
    SELECT
        s.as_of_gw,
        s.fpl_id,
        pg.value    AS value_lag3,
        pg.selected AS selected_lag3
    FROM spine s
    LEFT JOIN fact_player_gw pg   -- ref: fact_player_gw
        ON pg.fpl_id = s.fpl_id AND pg.round = s.as_of_gw - 3
    WHERE s.as_of_gw >= 4
)

SELECT
    n.as_of_gw,
    n.fpl_id,
    -- Point-in-time state at as_of_gw
    CASE WHEN n.value IS NOT NULL
        THEN n.value / 10.0
        ELSE NULL END                                       AS now_cost,
    n.selected                                              AS selected_by,
    n.transfers_in                                           AS transfers_in,
    n.transfers_out                                          AS transfers_out,
    CASE WHEN n.transfers_in IS NOT NULL AND n.transfers_out IS NOT NULL
        THEN n.transfers_in - n.transfers_out
        ELSE NULL END                                       AS transfer_delta,
    -- Velocity features: NULL when as_of_gw < 4 (no anchor_lag row produced)
    -- or when either anchor round is missing from fact_player_gw.
    CASE WHEN l.value_lag3 IS NOT NULL AND n.value IS NOT NULL
        THEN (n.value - l.value_lag3) / 10.0
        ELSE NULL END                                       AS price_velocity_3gw,
    CASE WHEN l.selected_lag3 IS NOT NULL AND n.selected IS NOT NULL
        THEN n.selected - l.selected_lag3
        ELSE NULL END                                       AS ownership_velocity_3gw
FROM anchor_now n
LEFT JOIN anchor_lag l
    ON l.as_of_gw = n.as_of_gw AND l.fpl_id = n.fpl_id
