-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_player_gw_base
-- =============================================================================
--
-- Purpose:
--   Produces the foundational (player, gameweek, round) rows shared by the
--   availability, performance, and market pipelines. Performs only clean joins
--   across base tables — no feature engineering, no aggregations.
--
-- Grain:
--   One row per (as_of_gw, fpl_id, round). A player's round row is included
--   for gameweek N only if that round exists in fact_player_gw AND round <= N.
--
-- Window contract:
--   rn_calendar = 1 is the most recent round <= as_of_gw for that player.
--   fct_ layers filter by rn_calendar to define window size; they do not
--   derive window bounds from calendar arithmetic.
--
--   rn_appearance (appearance-based window) is NOT computed here due to
--   SQLite not supporting FILTER on window functions. fct_ layers that need
--   an appearance window derive it from a subquery over rows where minutes > 0.
--
-- PIT contract:
--   as_of_gw is derived internally from fact_fixtures.finished = 1.
--   No future round data is used in this layer.
--
-- Outputs (columns consumed by fct_ layers):
--   as_of_gw      INTEGER  — the finished GW boundary
--   fpl_id        INTEGER  — player FPL identifier
--   team_fpl_id   INTEGER  — player's current team FPL ID at warehouse build
--   round         INTEGER  — the GW round for this row
--   minutes       INTEGER  — minutes played (COALESCE 0)
--   starts        INTEGER  — started (COALESCE 0)
--   total_points  INTEGER  — FPL total points (NULL if not populated)
--   bonus         INTEGER  — FPL bonus points
--   bps           INTEGER  — FPL BPS
--   clean_sheets  INTEGER  — clean sheet indicator
--   goals_conceded INTEGER  — goals conceded
--   expected_goals_conceded REAL — FPL xGC
--   clearances_blocks_interceptions INTEGER — FPL CBI
--   defensive_contribution INTEGER  — FPL defensive contribution
--   us_xgi        REAL     — Understat xG+xA (NULL if no Understat coverage)
--   us_xg         REAL     — Understat xG only (NULL if no Understat coverage)
--   us_xa         REAL     — Understat xA only (NULL if no Understat coverage)
--   threat        REAL     — FPL threat score
--   creativity    REAL     — FPL creativity score
--   ict_index     REAL     — FPL ICT index
--   rn_calendar   INTEGER  — row number ordered by round DESC (1 = most recent)
--
-- Known limitation:
--   team_fpl_id reflects dim_players at warehouse build time, not the player's
--   team at as_of_gw. Players who transferred clubs mid-season will have
--   incorrect team assignment for rows predating the move. No historical
--   player-team mapping table exists to correct this in v1.
--
-- Source tables:
--   fact_fixtures    — ref: fact_fixtures (GW spine only)
--   fact_player_gw   — ref: fact_player_gw
--   dim_players      — ref: dim_players
--   dim_teams        — ref: dim_teams
--
-- Future dbt migration:
--   Replace this file with a dbt model. Swap table references with
--   {{ ref('fact_fixtures') }}, {{ ref('fact_player_gw') }}, etc.
--   Remove CREATE VIEW and config with materialized='view' or 'ephemeral'.
-- =============================================================================

CREATE VIEW IF NOT EXISTS int_player_gw_base AS

WITH

-- Spine: every finished gameweek.
all_gws AS (
    SELECT DISTINCT event AS as_of_gw
    FROM fact_fixtures           -- ref: fact_fixtures
    WHERE finished = 1
),

-- All (as_of_gw, player, round) combinations: one row per round <= as_of_gw
-- for each player tracked in fact_player_gw. rn_calendar is assigned here so
-- fct_ layers never re-derive window bounds from round arithmetic.
player_gw_rows AS (
    SELECT
        g.as_of_gw,
        pg.fpl_id,
        dt.fpl_id                               AS team_fpl_id,
        pg.round,
        COALESCE(pg.minutes, 0)                 AS minutes,
        COALESCE(pg.starts,  0)                 AS starts,
        pg.total_points,
        pg.bonus,
        pg.bps,
        pg.clean_sheets,
        pg.goals_conceded,
        pg.expected_goals_conceded,
        pg.clearances_blocks_interceptions,
        pg.defensive_contribution,
        pg.us_xgi,
        pg.us_xg,
        pg.us_xa,
        pg.threat,
        pg.creativity,
        pg.ict_index,
        ROW_NUMBER() OVER (
            PARTITION BY g.as_of_gw, pg.fpl_id
            ORDER BY pg.round DESC
        )                                       AS rn_calendar
    FROM all_gws g
    JOIN fact_player_gw pg       -- ref: fact_player_gw
        ON pg.round <= g.as_of_gw
    JOIN dim_players dp          -- ref: dim_players
        ON dp.fpl_id = pg.fpl_id
    JOIN dim_teams dt            -- ref: dim_teams
        ON dt.team_id = dp.team_id
)

SELECT
    as_of_gw,
    fpl_id,
    team_fpl_id,
    round,
    minutes,
    starts,
    total_points,
    bonus,
    bps,
    clean_sheets,
    goals_conceded,
    expected_goals_conceded,
    clearances_blocks_interceptions,
    defensive_contribution,
    us_xgi,
    us_xg,
    us_xa,
    threat,
    creativity,
    ict_index,
    rn_calendar
FROM player_gw_rows
