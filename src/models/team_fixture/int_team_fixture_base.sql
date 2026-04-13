-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_team_fixture_base
-- =============================================================================
--
-- Purpose:
--   Produces one row per (as_of_gw, team_fpl_id, match) from fact_match_stats,
--   giving each team a first-person view of its historical match output.
--   This is the foundation for all team recent-output feature derivations in
--   fct_team_fixture_features.
--
-- Grain:
--   One row per (as_of_gw, team_fpl_id, understat_match_id).
--   Rows are absent for teams with no Understat match coverage.
--
-- Window contract:
--   rn_match = 1 is the most recent completed match for that team up to as_of_gw.
--   fct_ layers filter by rn_match <= 3 to get the last-3 window.
--
-- PIT contract:
--   Only fact_match_stats rows with event <= as_of_gw are included.
--   The as_of_gw spine is derived from fact_fixtures.finished = 1.
--
-- Technique:
--   fact_match_stats has home/away columns. This view unpivots using UNION ALL
--   so each match produces one row per participating team, with stats already
--   expressed from that team's perspective (team_xg, team_xgc, etc.).
--
-- Outputs (columns consumed by fct_team_fixture_features):
--   as_of_gw          INTEGER  — the finished GW boundary
--   team_fpl_id       INTEGER  — team FPL identifier (perspective team)
--   opp_fpl_id        INTEGER  — opponent FPL identifier
--   event             INTEGER  — GW event number for this match
--   understat_match_id INTEGER — unique match identifier (used in secondary sort)
--   team_xg           REAL     — xG scored by this team
--   team_xgc          REAL     — xG conceded by this team (opponent's xG)
--   team_ppda         REAL     — PPDA for this team (lower = more pressing)
--   team_deep         INTEGER  — deep completions for this team
--   team_sot          INTEGER  — shots on target for this team
--   rn_match          INTEGER  — row number ordered by event DESC (1 = most recent)
--
-- Coverage dependency:
--   Teams without Understat coverage produce no rows. fct_ layers LEFT JOIN to
--   this view so NULL team output features are returned for uncovered teams.
--
-- Source tables:
--   fact_fixtures      — ref: fact_fixtures (GW spine only)
--   fact_match_stats   — ref: fact_match_stats
--
-- Future dbt migration:
--   Replace this file with a dbt model using {{ ref('fact_fixtures') }} and
--   {{ ref('fact_match_stats') }}.
-- =============================================================================

CREATE VIEW IF NOT EXISTS int_team_fixture_base AS

WITH

-- Spine: every finished gameweek.
all_gws AS (
    SELECT DISTINCT event AS as_of_gw
    FROM fact_fixtures                 -- ref: fact_fixtures
    WHERE finished = 1
),

cutoff_gws AS (
    SELECT
        g.as_of_gw,
        MAX(f.kickoff_time) AS cutoff_time
    FROM all_gws g
    JOIN fact_fixtures f
        ON f.finished = 1
       AND f.event <= g.as_of_gw
    GROUP BY g.as_of_gw
),

-- Unpivot: express each match from each participating team's perspective.
-- UNION ALL produces two rows per fact_match_stats row — one for home, one away.
match_by_team AS (
    SELECT
        home_fpl_id                 AS team_fpl_id,
        away_fpl_id                 AS opp_fpl_id,
        event,
        understat_match_id,
        datetime                    AS match_datetime,
        home_xg                     AS team_xg,
        away_xg                     AS team_xgc,
        home_ppda                   AS team_ppda,
        home_deep                   AS team_deep,
        home_sot                    AS team_sot
    FROM fact_match_stats           -- ref: fact_match_stats
    UNION ALL
    SELECT
        away_fpl_id                 AS team_fpl_id,
        home_fpl_id                 AS opp_fpl_id,
        event,
        understat_match_id,
        datetime                    AS match_datetime,
        away_xg                     AS team_xg,
        home_xg                     AS team_xgc,
        away_ppda                   AS team_ppda,
        away_deep                   AS team_deep,
        away_sot                    AS team_sot
    FROM fact_match_stats           -- ref: fact_match_stats
)

SELECT
    g.as_of_gw,
    m.team_fpl_id,
    m.opp_fpl_id,
    m.event,
    m.understat_match_id,
    m.team_xg,
    m.team_xgc,
    m.team_ppda,
    m.team_deep,
    m.team_sot,
    ROW_NUMBER() OVER (
        PARTITION BY g.as_of_gw, m.team_fpl_id
        ORDER BY m.event DESC, m.understat_match_id DESC
    )                               AS rn_match
FROM all_gws g
JOIN cutoff_gws c
    ON c.as_of_gw = g.as_of_gw
JOIN match_by_team m
    ON m.event <= g.as_of_gw
   AND julianday(m.match_datetime) <= julianday(c.cutoff_time)
