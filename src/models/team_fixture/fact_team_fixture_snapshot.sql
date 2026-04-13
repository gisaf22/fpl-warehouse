-- =============================================================================
-- Layer: fact_ (mart)
-- Model: fact_team_fixture_snapshot
-- =============================================================================
--
-- Purpose:
--   Final SELECT from fct_team_fixture_features. This layer adds no
--   logic — it projects the fct_ view columns into the materialised table.
--
-- Grain:
--   One row per (as_of_gw, team_fpl_id). Primary key defined in DDL.
--
-- Orchestration:
--   Executed via INSERT INTO fact_team_fixture_snapshot <this file>
--   by the snapshot materializer after the table is created from the canonical
--   warehouse schema spec.
--
-- Future dbt migration:
--   Replace with a dbt model using {{ ref('fct_team_fixture_features') }}.
-- =============================================================================

SELECT
    as_of_gw,
    team_fpl_id,
    fixture_count,
    upcoming_dgw_flag,
    upcoming_bgw_flag,
    has_home_fixture AS has_home_fixture_flag,
    has_away_fixture AS has_away_fixture_flag,
    fixture_difficulty,
    opp_team_fpl_id AS opponent_team_fpl_id,
    team_days_since_last_fixture AS days_since_last_fixture,
    team_matches_last_7d AS matches_count_last_7d,
    team_matches_last_14d AS matches_count_last_14d,
    team_days_until_next_fixture AS days_until_next_fixture,
    team_days_between_last_and_next_fixture AS days_between_last_and_next_fixture,
    midweek_turnaround_flag
FROM fct_team_fixture_features
