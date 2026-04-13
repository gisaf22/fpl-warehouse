-- =============================================================================
-- Layer: fct_ (feature)
-- Model: fct_team_fixture_features
-- =============================================================================
--
-- Purpose:
--   Derives exogenous team-level fixture context features for each
--   (as_of_gw, team_fpl_id). One row per team per finished GW. Covers only
--   fixture schedule and schedule congestion.
--
-- Grain:
--   One row per (as_of_gw, team_fpl_id). Derived from dim_teams × finished_gws
--   spine, joined to fact_fixtures.
--
-- PIT contract:
--   - Fixture schedule features use fact_fixtures rows with event = as_of_gw + 1.
--   - Congestion features use fact_fixtures rows with event <= as_of_gw (history)
--     and any event (future lookup for next kickoff).
--   No feature in a row uses information from event > as_of_gw + 1.
--
-- Feature groups:
--   1. Fixture schedule (target_gw = as_of_gw + 1)
--      fixture_count, upcoming_dgw_flag, upcoming_bgw_flag,
--      has_home_fixture, has_away_fixture, fixture_difficulty, opp_team_fpl_id
--
--   2. Schedule congestion
--      team_days_since_last_fixture, team_matches_last_7d, team_matches_last_14d,
--      team_days_until_next_fixture, team_days_between_last_and_next_fixture,
--      midweek_turnaround_flag
--
-- Congestion anchor:
--   global_cutoff = MAX kickoff_time across ALL finished fixtures at event <= as_of_gw.
--   team_days_since_last_fixture = floor(global_cutoff - team's last kickoff) in days.
--   team_days_until_next_fixture = floor(team's next kickoff - global_cutoff) in days.
--   team_days_between = days_since + days_until = floor(next - last) in days.
--   midweek_turnaround_flag = 1 when team_days_between <= 4.
--
-- BGW policy (fixture_count = 0):
--   upcoming_bgw_flag = 1. has_home_fixture = has_away_fixture = 0.
--   fixture_difficulty = opp_team_fpl_id = NULL.
--
-- DGW policy (fixture_count = 2):
--   upcoming_dgw_flag = 1. fixture_difficulty = opp_team_fpl_id = NULL.
--
-- Null policy:
--   0 is not used as a default for any feature column. fixture_count,
--   has_home_fixture, has_away_fixture, upcoming_dgw_flag, upcoming_bgw_flag
--   are structural integers (never NULL). All other columns may be NULL.
--
-- Source tables:
--   dim_teams      — ref: dim_teams (team spine)
--   fact_fixtures  — ref: fact_fixtures (schedule + congestion)
--
-- Future dbt migration:
--   Replace with a dbt model. Swap references with {{ ref(...) }}.
-- =============================================================================

CREATE VIEW IF NOT EXISTS fct_team_fixture_features AS

WITH

-- Spine: every finished gameweek.
all_gws AS (
    SELECT DISTINCT event AS as_of_gw
    FROM fact_fixtures              -- ref: fact_fixtures
    WHERE finished = 1
),

-- Full team/GW spine: every (as_of_gw, team_fpl_id) combination.
team_spine AS (
    SELECT g.as_of_gw, dt.fpl_id AS team_fpl_id
    FROM all_gws g
    CROSS JOIN dim_teams dt         -- ref: dim_teams
),

-- Unpivot fact_fixtures to team perspective.
-- is_home = 1 when this team is the home side in this fixture.
fixture_by_team AS (
    SELECT
        event,
        home_team_id    AS team_fpl_id,
        away_team_id    AS opp_fpl_id,
        kickoff_time,
        finished,
        home_difficulty AS difficulty,
        1               AS is_home
    FROM fact_fixtures              -- ref: fact_fixtures
    UNION ALL
    SELECT
        event,
        away_team_id    AS team_fpl_id,
        home_team_id    AS opp_fpl_id,
        kickoff_time,
        finished,
        away_difficulty AS difficulty,
        0               AS is_home
    FROM fact_fixtures              -- ref: fact_fixtures
),

-- Upcoming fixture schedule for target_gw = as_of_gw + 1.
-- BGW teams: no matching rows in fixture_by_team → COUNT = 0 via LEFT JOIN.
-- DGW teams: two rows → COUNT = 2, difficulty/opp_team_fpl_id set to NULL.
upcoming AS (
    SELECT
        s.as_of_gw,
        s.team_fpl_id,
        COUNT(fbt.event)                                        AS fixture_count,
        CASE WHEN COUNT(fbt.event) > 1 THEN 1 ELSE 0 END       AS upcoming_dgw_flag,
        CASE WHEN COUNT(fbt.event) = 0 THEN 1 ELSE 0 END       AS upcoming_bgw_flag,
        MAX(CASE WHEN fbt.is_home = 1 THEN 1 ELSE 0 END)       AS has_home_fixture,
        MAX(CASE WHEN fbt.is_home = 0
                  AND fbt.event IS NOT NULL THEN 1 ELSE 0 END) AS has_away_fixture,
        -- NULL for BGW (no row) and DGW (two rows = ambiguous)
        CASE WHEN COUNT(fbt.event) = 1
            THEN MAX(fbt.difficulty)
            ELSE NULL END                                       AS fixture_difficulty,
        CASE WHEN COUNT(fbt.event) = 1
            THEN MAX(fbt.opp_fpl_id)
            ELSE NULL END                                       AS opp_team_fpl_id
    FROM team_spine s
    LEFT JOIN fixture_by_team fbt
        ON fbt.team_fpl_id = s.team_fpl_id
        AND fbt.event = s.as_of_gw + 1
    GROUP BY s.as_of_gw, s.team_fpl_id
),

-- Global cutoff: latest kickoff across ALL finished fixtures up to as_of_gw.
-- Used as the congestion reference anchor.
global_cutoff AS (
    SELECT
        g.as_of_gw,
        MAX(f.kickoff_time) AS cutoff_time
    FROM all_gws g
    JOIN fact_fixtures f         -- ref: fact_fixtures
        ON f.event <= g.as_of_gw AND f.finished = 1
    GROUP BY g.as_of_gw
),

-- Team's last completed fixture kickoff up to as_of_gw.
team_last_fixture AS (
    SELECT
        g.as_of_gw,
        fbt.team_fpl_id,
        MAX(fbt.kickoff_time) AS last_kickoff
    FROM all_gws g
    JOIN fixture_by_team fbt
        ON fbt.event <= g.as_of_gw AND fbt.finished = 1
    GROUP BY g.as_of_gw, fbt.team_fpl_id
),

-- Team's next scheduled kickoff after the global cutoff (regardless of GW).
-- Teams with no future fixture produce no row here.
team_next_fixture AS (
    SELECT
        ts.as_of_gw,
        ts.team_fpl_id,
        MIN(fbt.kickoff_time) AS next_kickoff
    FROM team_spine ts
    JOIN global_cutoff gc   ON gc.as_of_gw = ts.as_of_gw
    JOIN fixture_by_team fbt
        ON fbt.team_fpl_id = ts.team_fpl_id
        AND fbt.kickoff_time > gc.cutoff_time
    GROUP BY ts.as_of_gw, ts.team_fpl_id
),

-- Schedule congestion features derived from kickoff timestamps.
-- CAST(... AS INTEGER) floors the Julian day difference to whole days.
congestion AS (
    SELECT
        ts.as_of_gw,
        ts.team_fpl_id,
        -- Days since team's last fixture relative to global cutoff
        CASE WHEN tlf.last_kickoff IS NOT NULL
            THEN CAST(julianday(gc.cutoff_time) - julianday(tlf.last_kickoff) AS INTEGER)
            ELSE NULL END                                   AS team_days_since_last_fixture,
        -- Finished fixtures for this team with kickoff in the 7 days ending at global cutoff
        (
            SELECT COUNT(*)
            FROM fixture_by_team f2
            WHERE f2.team_fpl_id = ts.team_fpl_id
              AND f2.finished = 1
              AND f2.event <= ts.as_of_gw
              AND julianday(f2.kickoff_time) >= julianday(gc.cutoff_time) - 7
              AND f2.kickoff_time <= gc.cutoff_time
        )                                                   AS team_matches_last_7d,
        -- Same, 14-day window
        (
            SELECT COUNT(*)
            FROM fixture_by_team f2
            WHERE f2.team_fpl_id = ts.team_fpl_id
              AND f2.finished = 1
              AND f2.event <= ts.as_of_gw
              AND julianday(f2.kickoff_time) >= julianday(gc.cutoff_time) - 14
              AND f2.kickoff_time <= gc.cutoff_time
        )                                                   AS team_matches_last_14d,
        -- Days from global cutoff to team's next fixture kickoff
        CASE WHEN tnf.next_kickoff IS NOT NULL
            THEN CAST(julianday(tnf.next_kickoff) - julianday(gc.cutoff_time) AS INTEGER)
            ELSE NULL END                                   AS team_days_until_next_fixture
    FROM team_spine ts
    LEFT JOIN global_cutoff gc
        ON gc.as_of_gw = ts.as_of_gw
    LEFT JOIN team_last_fixture tlf
        ON tlf.as_of_gw = ts.as_of_gw AND tlf.team_fpl_id = ts.team_fpl_id
    LEFT JOIN team_next_fixture tnf
        ON tnf.as_of_gw = ts.as_of_gw AND tnf.team_fpl_id = ts.team_fpl_id
)

SELECT
    ts.as_of_gw,
    ts.team_fpl_id,
    -- Fixture schedule
    u.fixture_count,
    u.upcoming_dgw_flag,
    u.upcoming_bgw_flag,
    u.has_home_fixture,
    u.has_away_fixture,
    u.fixture_difficulty,
    u.opp_team_fpl_id,
    -- Schedule congestion
    c.team_days_since_last_fixture,
    c.team_matches_last_7d,
    c.team_matches_last_14d,
    c.team_days_until_next_fixture,
    CASE WHEN c.team_days_since_last_fixture IS NOT NULL
              AND c.team_days_until_next_fixture IS NOT NULL
        THEN c.team_days_since_last_fixture + c.team_days_until_next_fixture
        ELSE NULL END                           AS team_days_between_last_and_next_fixture,
    CASE WHEN c.team_days_since_last_fixture IS NOT NULL
              AND c.team_days_until_next_fixture IS NOT NULL
        THEN CASE WHEN c.team_days_since_last_fixture
                       + c.team_days_until_next_fixture <= 4
            THEN 1 ELSE 0 END
        ELSE NULL END                           AS midweek_turnaround_flag
FROM team_spine ts
JOIN upcoming u
    ON u.as_of_gw = ts.as_of_gw AND u.team_fpl_id = ts.team_fpl_id
LEFT JOIN congestion c
    ON c.as_of_gw = ts.as_of_gw AND c.team_fpl_id = ts.team_fpl_id
