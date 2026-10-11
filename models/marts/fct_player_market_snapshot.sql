-- =============================================================================
-- Layer: fct_ (fact)
-- Model: fct_player_market_snapshot
-- =============================================================================
--
-- Purpose:
--   Each player's market state at every admitted bootstrap-static capture:
--   price, ownership and the gameweek's transfer flow, as FPL published them
--   (#141, Feature #138).
--
-- Grain:
--   (season, fpl_id, capture_key): one row per player per capture (#138 M1).
--   Ownership moves at nearly every capture, so a change-only table would be
--   almost the same size; this is a fact, not SCD2.
--
-- Columns:
--   capture_key and observed_at come from the capture itself (#104).
--   now_cost, selected_by_percent, transfers_in_event and transfers_out_event
--   are stg_player's, typed only. Nothing is derived: no owner count, price
--   change or net transfers (#138 M2).
--
--   total_players is not here. It is the capture's player count, one value per
--   capture rather than per player, so it is not part of this per-player
--   served contract; it stays on stg_player (#143 P3).
--
-- Served:
--   Public with an enforced contract, published to
--   served/fct_player_market_snapshot.parquet (#143).
--
-- No backdating:
--   A row exists only for a capture. 2026-27 history begins 2026-08-29, and
--   2025-26 has one end-of-season capture.
--
-- Season:
--   Part of the key and nothing more. fpl_id is reassigned each season, and
--   no row is related to another season's.
-- =============================================================================

select
    season,
    fpl_id,
    capture_key,
    observed_at,
    now_cost,
    selected_by_percent,
    transfers_in_event,
    transfers_out_event
from {{ ref('stg_player') }}
