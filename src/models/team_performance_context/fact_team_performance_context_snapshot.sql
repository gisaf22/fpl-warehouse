-- =============================================================================
-- Layer: fact_ (mart)
-- Model: fact_team_performance_context_snapshot
-- =============================================================================
--
-- Purpose:
--   Final PIT-safe snapshot table at grain (as_of_gw, team_fpl_id). Selects
--   from fct_team_performance_context_features and orders columns to match
--   the canonical warehouse schema spec exactly.
--
--   This layer contains no feature logic. All derivations live in fct_.
--   Any column order or aliasing changes belong here, not in fct_.
--
-- Grain:
--   One row per (as_of_gw, team_fpl_id).
--   Primary key: (as_of_gw, team_fpl_id) — enforced by the persisted snapshot
--   table DDL.
--
-- PIT contract:
--   Inherited from fct_team_performance_context_features. No feature uses
--   information from event > as_of_gw + 1.
--
-- This query is executed as:
--   INSERT INTO fact_team_performance_context_snapshot <this file>
--
-- Source:
--   fct_team_performance_context_features — ref: fct_ view (team form + opponent)
-- =============================================================================

SELECT
    as_of_gw,
    team_fpl_id,
    opponent_team_fpl_id,
    team_xg_total_last_3gws,
    team_xgc_total_last_3gws,
    team_ppda_avg_last_3gws,
    team_deep_total_last_3gws,
    team_sot_total_last_3gws,
    opponent_xg_total_last_3gws,
    opponent_xgc_total_last_3gws,
    opponent_xgc_avg_last_3gws,
    opponent_ppda_avg_last_3gws,
    opponent_sot_total_last_3gws
FROM fct_team_performance_context_features