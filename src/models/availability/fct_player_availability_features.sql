-- =============================================================================
-- Layer: fct_ (feature)
-- Model: fct_player_availability_features
-- =============================================================================
--
-- Purpose:
--   Derives all availability and playing-time features for each
--   (as_of_gw, fpl_id) combination. Reads from int_player_gw_base and
--   base tables. Produces one row per (as_of_gw, fpl_id) with all rolling
--   usage windows.
--
-- Grain:
--   One row per (as_of_gw, fpl_id). Aggregated from int_player_gw_base rows.
--
-- PIT contract:
--   All usage features use fact_player_gw rows with round <= as_of_gw,
--   inherited from int_player_gw_base.
--   Window bounds are enforced by rn_calendar filters, not calendar arithmetic.
--   No feature may reference round > as_of_gw.
--
-- Feature groups:
--   1. Recent usage    — last_gw_minutes, last_gw_started, rolling 3/5 GW
--                        minutes, starts, appearances, averages, volatility,
--                        max/min minutes when in squad
--   2. Rate / trend    — start rates, appearance rate, sub rate, delta features,
--                        starts_per_appearance
--
-- Window contract (from int_player_gw_base):
--   rn_calendar = 1: most recent round. Used for last_gw_* features.
--   rn_calendar <= 3: last 3 rounds. Used for 3-GW window features.
--   rn_calendar <= 5: last 5 rounds. Used for 5-GW window features.
--   All filters are on rn_calendar, not round arithmetic.
--
-- Source tables:
--   int_player_gw_base  — ref: int_player_gw_base (int_ layer)
--   fact_fixtures           — ref: fact_fixtures (rate denominators only)
--
-- Null/default policy (inherited from snapshot spec):
--   NULL  when underlying information is unknown or unavailable historically.
--   0     for count features when the count is structurally zero from known data.
--   Rate features are nullable when the denominator is zero (no games played).
--
-- Upstream design constraints and assumptions:
--   fact_player_gw grain: UNIQUE(fpl_id, round). DGW fixtures are aggregated
--   into one row per player per GW. Rate denominators must align to GWs played,
--   not fixtures played.
--
--   Absence = unknown: a player absent from fact_player_gw in a round has no
--   row in int_player_gw_base for that round. Conditional features (AVG, MIN,
--   MAX) exclude absent rounds. This conflates injury, suspension, and tactical
--   non-selection — an accepted limitation for v1.
--
--   Rate denominator: team GWs actually played (COUNT DISTINCT event with
--   finished = 1) within the rolling window. This correctly handles BGWs (no
--   denominator inflation) and DGWs (one GW regardless of fixture count), and
--   aligns with the fact_player_gw grain.
--
--   Three-way identity (by construction):
--     start_rate ≈ appearance_rate × starts_per_appearance
--   All three are exposed as independent features. This is intentional —
--   structured redundancy for the model layer, not accidental duplication.
--
-- Future dbt migration:
--   Replace CREATE VIEW with a dbt model file.
--   Replace table references with {{ ref('int_player_gw_base') }},
--   {{ ref('fact_fixtures') }}.
-- =============================================================================

CREATE VIEW IF NOT EXISTS fct_player_availability_features AS

WITH

appearance_rows AS (
    SELECT
        as_of_gw,
        fpl_id,
        ROW_NUMBER() OVER (
            PARTITION BY as_of_gw, fpl_id
            ORDER BY round DESC
        ) AS rn_app
    FROM int_player_gw_base
    WHERE minutes > 0
),

appearance_counts AS (
    SELECT
        as_of_gw,
        fpl_id,
        COUNT(*) AS appearances_last_3_apps
    FROM appearance_rows
    WHERE rn_app <= 3
    GROUP BY as_of_gw, fpl_id
),

-- ---------------------------------------------------------------------------
-- Feature group 1: recent usage
-- Filters int_player_gw_base to the 5-GW window (rn_calendar <= 5).
-- Aggregations split into 3-GW (rn_calendar <= 3) and 5-GW sub-windows.
-- ---------------------------------------------------------------------------

-- ref: int_player_gw_base
-- 5-GW window: rn_calendar = 1 (most recent) through rn_calendar = 5.
window_rows AS (
    SELECT *
    FROM int_player_gw_base    -- ref: int_player_gw_base
    WHERE rn_calendar <= 5
),

-- Rolling aggregations over 3-GW and 5-GW windows.
-- minutes_volatility_5gws uses the population standard deviation formula
-- SQRT(AVG(x²) - AVG(x)²) across up to 5 rows. NULL when fewer than 3 rows
-- exist (insufficient sample to be meaningful).
player_usage AS (
    SELECT
        as_of_gw,
        fpl_id,
        team_fpl_id,

        -- Last GW only (rn_calendar = 1 is the most recent round)
        MAX(CASE WHEN rn_calendar = 1 THEN minutes END) AS last_gw_minutes,
        MAX(CASE WHEN rn_calendar = 1 THEN starts  END) AS last_gw_started,

        -- Rolling 3-GW window (rn_calendar <= 3)
        COALESCE(SUM(CASE WHEN rn_calendar <= 3 THEN minutes ELSE 0 END), 0)
            AS minutes_last_3gws,
        COALESCE(SUM(CASE WHEN rn_calendar <= 3 THEN starts  ELSE 0 END), 0)
            AS starts_last_3gws,
        COALESCE(SUM(CASE WHEN rn_calendar <= 3 AND minutes > 0 THEN 1 ELSE 0 END), 0)
            AS appearances_last_3gws,
        ROUND(AVG(CASE WHEN rn_calendar <= 3 THEN minutes END), 1)
            AS avg_minutes_last_3gws,

        -- Rolling 5-GW window (all rows in window_rows, rn_calendar <= 5)
        COALESCE(SUM(minutes), 0)                                   AS minutes_last_5gws,
        COALESCE(SUM(starts),  0)                                   AS starts_last_5gws,
        COALESCE(SUM(CASE WHEN minutes > 0 THEN 1 ELSE 0 END), 0)  AS appearances_last_5gws,
        ROUND(AVG(minutes), 1)                                      AS avg_minutes_last_5gws,

        -- Volatility: population std dev of minutes over the 5-GW window.
        -- NULL when fewer than 3 observations exist (not enough signal).
        CASE WHEN COUNT(minutes) >= 3 THEN
            ROUND(
                SQRT(AVG(minutes * minutes) - AVG(minutes) * AVG(minutes)),
                2
            )
        END AS minutes_volatility_5gws,

        -- Ceiling / floor: conditional on squad inclusion (absence = unknown).
        -- NULL when no game rows exist in the window.
        MAX(minutes) AS max_minutes_last_5gws,
        MIN(minutes) AS min_minutes_when_in_squad_last_5gws

    FROM window_rows
    GROUP BY as_of_gw, fpl_id, team_fpl_id
),

-- ---------------------------------------------------------------------------
-- Rate denominators: team GWs played within the rolling windows.
-- Uses fact_fixtures (finished = 1) via team_fixture_rows to count distinct
-- events the team played, correctly handling BGWs and DGWs.
-- ---------------------------------------------------------------------------

-- Unpivot: one row per team per fixture (home and away treated identically).
-- ref: fact_fixtures
team_fixture_rows AS (
    SELECT home_team_id AS team_fpl_id, fixture_id, event, finished
    FROM fact_fixtures              -- ref: fact_fixtures
    UNION ALL
    SELECT away_team_id AS team_fpl_id, fixture_id, event, finished
    FROM fact_fixtures              -- ref: fact_fixtures
),

-- GWs the team actually played in the 3-GW and 5-GW windows.
-- Uses COUNT(DISTINCT event) to align with fact_player_gw grain (one row per
-- player per GW). In DGWs, two fixtures share one event — counted once here
-- and once in fact_player_gw. In BGWs, no event → denominator not inflated.
-- Deduplicates int_player_gw_base to distinct (as_of_gw, team_fpl_id) pairs
-- since int_ now has one row per round.
team_window_counts AS (
    SELECT
        base.as_of_gw,
        base.team_fpl_id,
        COUNT(DISTINCT CASE
            WHEN tfr.event > base.as_of_gw - 3
             AND tfr.event <= base.as_of_gw
            THEN tfr.event
        END) AS team_gws_played_last_3gws,
        COUNT(DISTINCT CASE
            WHEN tfr.event > base.as_of_gw - 5
             AND tfr.event <= base.as_of_gw
            THEN tfr.event
        END) AS team_gws_played_last_5gws
    FROM (SELECT DISTINCT as_of_gw, team_fpl_id FROM int_player_gw_base) base  -- ref: int_player_gw_base
    JOIN team_fixture_rows tfr
        ON  tfr.team_fpl_id = base.team_fpl_id
        AND tfr.finished = 1
        AND tfr.event  > base.as_of_gw - 5
        AND tfr.event <= base.as_of_gw
    GROUP BY base.as_of_gw, base.team_fpl_id
)

-- ---------------------------------------------------------------------------
-- Final assembly: join rate denominators onto the player-GW spine.
-- LEFT JOIN preserves all players; missing team data resolves to NULL.
-- ---------------------------------------------------------------------------
SELECT
    pu.as_of_gw,
    pu.fpl_id,
    pu.team_fpl_id,

    -- Recent usage features
    pu.last_gw_minutes,
    pu.last_gw_started,
    pu.minutes_last_3gws,
    pu.minutes_last_5gws,
    pu.starts_last_3gws,
    pu.starts_last_5gws,
    pu.appearances_last_3gws,
    pu.appearances_last_5gws,
    COALESCE(ac.appearances_last_3_apps, 0) AS appearances_count_last_3_apps,
    pu.avg_minutes_last_3gws,
    pu.avg_minutes_last_5gws,
    pu.minutes_volatility_5gws,
    pu.max_minutes_last_5gws,
    pu.min_minutes_when_in_squad_last_5gws,

    -- Rate features
    -- Denominator: team GWs played (COUNT DISTINCT event, finished = 1).
    -- Handles BGWs (no inflation) and DGWs (one GW per event, matching
    -- fact_player_gw grain). NULL when denominator = 0 (team had no games).
    ROUND(1.0 * pu.starts_last_3gws / NULLIF(twc.team_gws_played_last_3gws, 0), 3)
        AS start_rate_last_3gws,
    ROUND(1.0 * pu.starts_last_5gws / NULLIF(twc.team_gws_played_last_5gws, 0), 3)
        AS start_rate_last_5gws,
    ROUND(1.0 * pu.appearances_last_5gws / NULLIF(twc.team_gws_played_last_5gws, 0), 3)
        AS appearance_rate_last_5gws,
    ROUND(1.0 * pu.starts_last_5gws / NULLIF(pu.appearances_last_5gws, 0), 3)
        AS starts_per_appearance_last_5gws,
    pu.appearances_last_5gws - pu.starts_last_5gws
        AS sub_appearances_last_5gws,
    ROUND(
        1.0 * (pu.appearances_last_5gws - pu.starts_last_5gws)
        / NULLIF(twc.team_gws_played_last_5gws, 0),
        3
    ) AS sub_rate_last_5gws,
    ROUND(pu.avg_minutes_last_3gws - pu.avg_minutes_last_5gws, 1)
        AS minutes_delta_3v5,
    ROUND(
        1.0 * pu.starts_last_3gws / NULLIF(twc.team_gws_played_last_3gws, 0)
      - 1.0 * pu.starts_last_5gws / NULLIF(twc.team_gws_played_last_5gws, 0),
        3
    ) AS starts_delta_3v5
FROM player_usage pu
LEFT JOIN team_window_counts twc
    ON twc.team_fpl_id = pu.team_fpl_id
   AND twc.as_of_gw = pu.as_of_gw
LEFT JOIN appearance_counts ac
    ON ac.as_of_gw = pu.as_of_gw
   AND ac.fpl_id = pu.fpl_id
