-- =============================================================================
-- Layer: fct_ (feature)
-- Model: fct_team_performance_context_features
-- =============================================================================
--
-- Purpose:
--   Derives team and opponent recent-form features for each
--   (as_of_gw, team_fpl_id). One row per team per finished GW. Covers
--   team xG, xGC, PPDA, deep completions, and shots on target over the
--   last 3 matches, plus the upcoming opponent identity.
--
-- Grain:
--   One row per (as_of_gw, team_fpl_id). Derived from dim_teams ×
--   finished_gws spine.
--
-- PIT contract:
--   All team and opponent form metrics are derived from int_team_fixture_base
--   rows with rn_match <= 3 (i.e. the 3 matches completed before as_of_gw).
--   Opponent identity uses fact_fixtures with event = as_of_gw + 1.
--   No feature uses information from event > as_of_gw + 1.
--
-- Null policy:
--   opponent_team_fpl_id is NULL for DGW teams (ambiguous opponent) and
--   for teams with no upcoming fixture. All form metrics may be NULL for
--   teams with fewer than 1 completed match.
--
-- Source tables:
--   dim_teams            — ref: dim_teams (team spine)
--   fact_fixtures        — ref: fact_fixtures (upcoming opponent lookup)
--   int_team_fixture_base — ref: int_team_fixture_base (rolling form window)
--
-- Future dbt migration:
--   Replace with a dbt model. Swap references with {{ ref(...) }}.
-- =============================================================================

CREATE VIEW IF NOT EXISTS fct_team_performance_context_features AS

WITH

all_gws AS (
    SELECT DISTINCT event AS as_of_gw
    FROM fact_fixtures
    WHERE finished = 1
),

team_spine AS (
    SELECT g.as_of_gw, dt.fpl_id AS team_fpl_id
    FROM all_gws g
    CROSS JOIN dim_teams dt
),

fixture_by_team AS (
    SELECT
        event,
        home_team_id AS team_fpl_id,
        away_team_id AS opp_fpl_id
    FROM fact_fixtures
    UNION ALL
    SELECT
        event,
        away_team_id AS team_fpl_id,
        home_team_id AS opp_fpl_id
    FROM fact_fixtures
),

upcoming AS (
    SELECT
        s.as_of_gw,
        s.team_fpl_id,
        CASE WHEN COUNT(fbt.event) = 1 THEN MAX(fbt.opp_fpl_id) ELSE NULL END AS opponent_team_fpl_id
    FROM team_spine s
    LEFT JOIN fixture_by_team fbt
        ON fbt.team_fpl_id = s.team_fpl_id
       AND fbt.event = s.as_of_gw + 1
    GROUP BY s.as_of_gw, s.team_fpl_id
),

team_recent AS (
    SELECT
        as_of_gw,
        team_fpl_id,
        SUM(COALESCE(team_xg, 0)) AS team_xg_total_last_3gws,
        SUM(COALESCE(team_xgc, 0)) AS team_xgc_total_last_3gws,
        AVG(team_ppda) AS team_ppda_avg_last_3gws,
        SUM(COALESCE(team_deep, 0)) AS team_deep_total_last_3gws,
        SUM(COALESCE(team_sot, 0)) AS team_sot_total_last_3gws
    FROM int_team_fixture_base
    WHERE rn_match <= 3
    GROUP BY as_of_gw, team_fpl_id
),

opponent_recent AS (
    SELECT
        as_of_gw,
        team_fpl_id,
        SUM(COALESCE(team_xg, 0)) AS opponent_xg_total_last_3gws,
        SUM(COALESCE(team_xgc, 0)) AS opponent_xgc_total_last_3gws,
        AVG(team_xgc) AS opponent_xgc_avg_last_3gws,
        AVG(team_ppda) AS opponent_ppda_avg_last_3gws,
        SUM(COALESCE(team_sot, 0)) AS opponent_sot_total_last_3gws
    FROM int_team_fixture_base
    WHERE rn_match <= 3
    GROUP BY as_of_gw, team_fpl_id
)

SELECT
    ts.as_of_gw,
    ts.team_fpl_id,
    u.opponent_team_fpl_id,
    tr.team_xg_total_last_3gws,
    tr.team_xgc_total_last_3gws,
    tr.team_ppda_avg_last_3gws,
    tr.team_deep_total_last_3gws,
    tr.team_sot_total_last_3gws,
    opr.opponent_xg_total_last_3gws,
    opr.opponent_xgc_total_last_3gws,
    opr.opponent_xgc_avg_last_3gws,
    opr.opponent_ppda_avg_last_3gws,
    opr.opponent_sot_total_last_3gws
FROM team_spine ts
LEFT JOIN upcoming u
    ON u.as_of_gw = ts.as_of_gw AND u.team_fpl_id = ts.team_fpl_id
LEFT JOIN team_recent tr
    ON tr.as_of_gw = ts.as_of_gw AND tr.team_fpl_id = ts.team_fpl_id
LEFT JOIN opponent_recent opr
    ON opr.as_of_gw = ts.as_of_gw AND opr.team_fpl_id = u.opponent_team_fpl_id
