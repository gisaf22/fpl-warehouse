-- =============================================================================
-- Layer: fact_ (mart)
-- Model: fact_player_market_snapshot
-- =============================================================================
--
-- Purpose:
--   Final SELECT from fct_player_market_features. This layer adds no
--   logic — it projects the fct_ view columns into the materialised table.
--
-- Grain:
--   One row per (as_of_gw, fpl_id). Primary key defined in DDL.
--
-- Orchestration:
--   Executed via INSERT INTO fact_player_market_snapshot <this file>
--   by the snapshot materializer after the table is created from the canonical
--   warehouse schema spec.
--
-- Future dbt migration:
--   Replace with a dbt model using {{ ref('fct_player_market_features') }}.
-- =============================================================================

SELECT
    as_of_gw,
    fpl_id,
    now_cost,
    selected_by,
    transfers_in,
    transfers_out,
    transfer_delta AS transfers_net,
    price_velocity_3gw AS price_delta_last_3gws,
    ownership_velocity_3gw AS ownership_delta_last_3gws
FROM fct_player_market_features
