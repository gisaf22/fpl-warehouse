"""SQL view definitions for the FPL warehouse.

Views are created/replaced during each warehouse build so they always
reflect the latest schema.  They answer the key weekly FPL questions
using only the data already in master.db.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

# ── Season-level player summary ─────────────────────────────────────────
# Aggregates all GW stats per player for the season so far.
V_PLAYER_SEASON = """
CREATE VIEW IF NOT EXISTS v_player_season AS
SELECT
    dp.player_id,
    dp.fpl_id,
    dp.understat_id,
    dp.web_name,
    dp.fpl_name,
    dt.fpl_name       AS team,
    dt.short_name      AS team_short,
    SUM(g.minutes)     AS minutes,
    SUM(g.starts)      AS starts,
    COUNT(CASE WHEN g.minutes > 0 THEN 1 END) AS appearances,
    SUM(g.goals_scored) AS goals,
    SUM(g.assists)     AS assists,
    SUM(g.clean_sheets) AS clean_sheets,
    SUM(g.total_points) AS total_points,
    SUM(g.bonus)       AS bonus,
    SUM(g.bps)         AS bps,
    ROUND(SUM(g.fpl_xg), 2)  AS fpl_xg,
    ROUND(SUM(g.fpl_xa), 2)  AS fpl_xa,
    ROUND(SUM(g.fpl_xgi), 2) AS fpl_xgi,
    ROUND(SUM(g.us_xg), 2)   AS us_xg,
    ROUND(SUM(g.us_xa), 2)   AS us_xa,
    ROUND(SUM(g.us_xgi), 2)  AS us_xgi,
    ROUND(SUM(g.xg_chain), 2)   AS xg_chain,
    ROUND(SUM(g.xg_buildup), 2) AS xg_buildup,
    -- Latest value (price) from most recent GW played
    (SELECT g2.value FROM fact_player_gw g2
     WHERE g2.fpl_id = dp.fpl_id AND g2.minutes > 0
     ORDER BY g2.round DESC LIMIT 1) AS current_value,
    -- Latest selected count
    (SELECT g2.selected FROM fact_player_gw g2
     WHERE g2.fpl_id = dp.fpl_id AND g2.minutes > 0
     ORDER BY g2.round DESC LIMIT 1) AS selected
FROM dim_players dp
JOIN dim_teams dt ON dt.team_id = dp.team_id
JOIN fact_player_gw g ON g.fpl_id = dp.fpl_id
GROUP BY dp.player_id
HAVING SUM(g.minutes) > 0
"""

# ── xG over/under-performers ────────────────────────────────────────────
# Players whose actual goals differ most from xG.
# Positive xg_diff = overperforming (sell risk), negative = underperforming (buy).
V_XG_DIVERGENCE = """
CREATE VIEW IF NOT EXISTS v_xg_divergence AS
SELECT
    dp.web_name,
    dp.fpl_name,
    dt.short_name            AS team,
    SUM(g.minutes)           AS minutes,
    SUM(g.goals_scored)      AS goals,
    ROUND(SUM(g.us_xg), 2)  AS us_xg,
    SUM(g.goals_scored) - ROUND(SUM(g.us_xg), 2) AS xg_diff,
    SUM(g.assists)           AS assists,
    ROUND(SUM(g.us_xa), 2)  AS us_xa,
    SUM(g.assists) - ROUND(SUM(g.us_xa), 2) AS xa_diff,
    SUM(g.total_points)      AS total_points,
    (SELECT g2.value FROM fact_player_gw g2
     WHERE g2.fpl_id = dp.fpl_id AND g2.minutes > 0
     ORDER BY g2.round DESC LIMIT 1) AS current_value
FROM dim_players dp
JOIN dim_teams dt ON dt.team_id = dp.team_id
JOIN fact_player_gw g ON g.fpl_id = dp.fpl_id
GROUP BY dp.player_id
HAVING SUM(g.minutes) >= 450
ORDER BY xg_diff DESC
"""

# ── Rolling form (last 5 GWs with minutes) ──────────────────────────────
# Recent form window — more relevant than season totals for transfers.
V_FORM = """
CREATE VIEW IF NOT EXISTS v_form AS
SELECT
    dp.web_name,
    dp.fpl_name,
    dt.short_name        AS team,
    SUM(r.minutes)       AS minutes,
    SUM(r.goals_scored)  AS goals,
    SUM(r.assists)       AS assists,
    SUM(r.total_points)  AS points,
    ROUND(AVG(r.total_points), 1) AS ppg,
    SUM(r.bonus)         AS bonus,
    ROUND(SUM(r.fpl_xg), 2)  AS fpl_xg,
    ROUND(SUM(r.fpl_xa), 2)  AS fpl_xa,
    ROUND(SUM(r.us_xg), 2)   AS us_xg,
    ROUND(SUM(r.us_xa), 2)   AS us_xa,
    ROUND(SUM(r.us_xgi), 2)  AS us_xgi,
    (SELECT g2.value FROM fact_player_gw g2
     WHERE g2.fpl_id = dp.fpl_id AND g2.minutes > 0
     ORDER BY g2.round DESC LIMIT 1) AS current_value
FROM dim_players dp
JOIN dim_teams dt ON dt.team_id = dp.team_id
JOIN (
    SELECT fpl_id, round, minutes, goals_scored, assists,
           total_points, bonus, fpl_xg, fpl_xa, us_xg, us_xa, us_xgi,
           ROW_NUMBER() OVER (PARTITION BY fpl_id ORDER BY round DESC) AS rn
    FROM fact_player_gw
    WHERE minutes > 0
) r ON r.fpl_id = dp.fpl_id AND r.rn <= 5
GROUP BY dp.player_id
HAVING SUM(r.minutes) > 0
ORDER BY points DESC
"""

# ── Upcoming fixture difficulty ──────────────────────────────────────────
# Next 5 unplayed GWs per team with opponent and difficulty rating.
V_FIXTURE_TICKER = """
CREATE VIEW IF NOT EXISTS v_fixture_ticker AS
SELECT
    dt.fpl_name   AS team,
    dt.short_name AS team_short,
    f.event       AS gw,
    CASE WHEN f.home_team_id = dt.fpl_id THEN opp.short_name || ' (H)'
         ELSE opp.short_name || ' (A)'
    END AS fixture,
    CASE WHEN f.home_team_id = dt.fpl_id THEN f.home_difficulty
         ELSE f.away_difficulty
    END AS fdr
FROM dim_teams dt
JOIN fact_fixtures f ON f.home_team_id = dt.fpl_id OR f.away_team_id = dt.fpl_id
JOIN dim_teams opp ON opp.fpl_id = CASE
    WHEN f.home_team_id = dt.fpl_id THEN f.away_team_id
    ELSE f.home_team_id
END
WHERE f.finished = 0 AND f.event IS NOT NULL
ORDER BY dt.fpl_name, f.event
"""

# ── Fixture opponents (all GWs) ──────────────────────────────────────────
# Unpivots every fixture into per-team rows with opponent ID and home flag.
# Unlike v_fixture_ticker this includes finished AND unfinished fixtures.
V_FIXTURE_OPPONENTS = """
CREATE VIEW IF NOT EXISTS v_fixture_opponents AS
SELECT
    dt.fpl_id       AS team_fpl_id,
    f.event         AS gw,
    CASE WHEN f.home_team_id = dt.fpl_id
         THEN f.away_team_id
         ELSE f.home_team_id
    END AS opponent_team_id,
    CASE WHEN f.home_team_id = dt.fpl_id THEN 1 ELSE 0 END AS is_home,
    f.finished
FROM dim_teams dt
JOIN fact_fixtures f
    ON f.home_team_id = dt.fpl_id OR f.away_team_id = dt.fpl_id
WHERE f.event IS NOT NULL
ORDER BY f.event, dt.fpl_id
"""

# ── Differentials ────────────────────────────────────────────────────────
# High-performing players with low ownership — potential rank climbers.
V_DIFFERENTIALS = """
CREATE VIEW IF NOT EXISTS v_differentials AS
SELECT
    dp.web_name,
    dp.fpl_name,
    dt.short_name     AS team,
    latest.selected   AS selected,
    latest.value      AS current_value,
    SUM(g.total_points)   AS total_points,
    ROUND(AVG(g.total_points), 1) AS ppg,
    SUM(g.minutes)    AS minutes,
    ROUND(SUM(g.us_xgi), 2) AS us_xgi,
    ROUND(SUM(g.us_xg), 2)  AS us_xg
FROM dim_players dp
JOIN dim_teams dt ON dt.team_id = dp.team_id
JOIN fact_player_gw g ON g.fpl_id = dp.fpl_id
JOIN (
    SELECT fpl_id, selected, value,
           ROW_NUMBER() OVER (PARTITION BY fpl_id ORDER BY round DESC) AS rn
    FROM fact_player_gw
    WHERE minutes > 0
) latest ON latest.fpl_id = dp.fpl_id AND latest.rn = 1
GROUP BY dp.player_id
HAVING SUM(g.minutes) >= 450 AND latest.selected < 100000
ORDER BY ppg DESC
"""

# ── Team strength (attack & defence) ────────────────────────────────────
# Aggregated team-level xG for and against from match stats.
V_TEAM_STRENGTH = """
CREATE VIEW IF NOT EXISTS v_team_strength AS
SELECT
    dt.fpl_name    AS team,
    dt.short_name  AS team_short,
    COUNT(*)       AS matches,
    -- Attack
    ROUND(SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_xg
                   ELSE ms.away_xg END), 2) AS xg_for,
    SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_goals
             ELSE ms.away_goals END) AS goals_for,
    -- Defence
    ROUND(SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.away_xg
                   ELSE ms.home_xg END), 2) AS xg_against,
    SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.away_goals
             ELSE ms.home_goals END) AS goals_against,
    -- Per-match averages
    ROUND(SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_xg
                   ELSE ms.away_xg END) / COUNT(*), 2) AS xg_for_avg,
    ROUND(SUM(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.away_xg
                   ELSE ms.home_xg END) / COUNT(*), 2) AS xg_against_avg,
    -- PPDA (pressing intensity — lower = more press)
    ROUND(AVG(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_ppda
                   ELSE ms.away_ppda END), 1) AS ppda_avg,
    -- Deep completions
    ROUND(AVG(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_deep
                   ELSE ms.away_deep END), 1) AS deep_avg
FROM dim_teams dt
JOIN fact_match_stats ms ON ms.home_fpl_id = dt.fpl_id
                         OR ms.away_fpl_id = dt.fpl_id
GROUP BY dt.team_id
ORDER BY xg_for_avg DESC
"""

# ── Per-GW team xG ──────────────────────────────────────────────────────
# For each team and gameweek: xG created and xG conceded.
# Automatically reflects new data when fact_match_stats is refreshed.
V_TEAM_XG_GW = """
CREATE VIEW IF NOT EXISTS v_team_xg_gw AS
SELECT
    dt.fpl_id,
    dt.fpl_name          AS team,
    dt.short_name        AS team_short,
    ms.event             AS gw,
    CASE WHEN ms.home_fpl_id = dt.fpl_id THEN 1 ELSE 0 END AS is_home,
    ROUND(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_xg
               ELSE ms.away_xg END, 2) AS xg_for,
    ROUND(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.away_xg
               ELSE ms.home_xg END, 2) AS xg_against,
    CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_goals
         ELSE ms.away_goals END AS goals_for,
    CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.away_goals
         ELSE ms.home_goals END AS goals_against,
    ROUND(CASE WHEN ms.home_fpl_id = dt.fpl_id THEN ms.home_ppda
               ELSE ms.away_ppda END, 2) AS ppda
FROM dim_teams dt
JOIN fact_match_stats ms
    ON ms.home_fpl_id = dt.fpl_id
    OR ms.away_fpl_id = dt.fpl_id
WHERE ms.event IS NOT NULL
ORDER BY dt.fpl_id, ms.event
"""

# ── Captain picks ────────────────────────────────────────────────────────
# Best captain options: high xGI + good upcoming fixture.
V_CAPTAIN_PICKS = """
CREATE VIEW IF NOT EXISTS v_captain_picks AS
SELECT
    dp.web_name,
    dp.fpl_name,
    dt.short_name     AS team,
    -- Recent form (last 5 GWs played)
    ROUND(form.ppg, 1)    AS form_ppg,
    ROUND(form.xgi, 2)    AS form_xgi,
    form.points            AS form_pts,
    -- Next fixture
    nxt.gw                 AS next_gw,
    nxt.fixture            AS next_fixture,
    nxt.fdr                AS next_fdr,
    -- Season totals
    ROUND(SUM(g.us_xgi), 2) AS season_xgi,
    SUM(g.total_points)    AS season_pts
FROM dim_players dp
JOIN dim_teams dt ON dt.team_id = dp.team_id
JOIN fact_player_gw g ON g.fpl_id = dp.fpl_id
-- Recent form subquery
JOIN (
    SELECT
        fpl_id,
        AVG(total_points) AS ppg,
        SUM(us_xgi)       AS xgi,
        SUM(total_points)  AS points
    FROM (
        SELECT fpl_id, total_points, us_xgi,
               ROW_NUMBER() OVER (PARTITION BY fpl_id ORDER BY round DESC) AS rn
        FROM fact_player_gw WHERE minutes > 0
    ) WHERE rn <= 5
    GROUP BY fpl_id
) form ON form.fpl_id = dp.fpl_id
-- Next fixture subquery
LEFT JOIN (
    SELECT
        dt2.fpl_id AS team_fpl_id,
        f.event AS gw,
        CASE WHEN f.home_team_id = dt2.fpl_id
             THEN opp.short_name || ' (H)'
             ELSE opp.short_name || ' (A)'
        END AS fixture,
        CASE WHEN f.home_team_id = dt2.fpl_id
             THEN f.home_difficulty
             ELSE f.away_difficulty
        END AS fdr
    FROM dim_teams dt2
    JOIN fact_fixtures f ON (f.home_team_id = dt2.fpl_id OR f.away_team_id = dt2.fpl_id)
                        AND f.finished = 0 AND f.event IS NOT NULL
    JOIN dim_teams opp ON opp.fpl_id = CASE
        WHEN f.home_team_id = dt2.fpl_id THEN f.away_team_id
        ELSE f.home_team_id
    END
    GROUP BY dt2.fpl_id
    HAVING f.event = MIN(f.event)
) nxt ON nxt.team_fpl_id = dt.fpl_id
GROUP BY dp.player_id
HAVING SUM(g.minutes) >= 450
ORDER BY form_ppg DESC
"""

# ── Decision-ready feature view ─────────────────────────────────────────
# One row per (player, GW) with all features needed by fpl-transfers decision engine.
# Point-in-time safe: rolling stats use only data from GWs before the
# target GW.  Opponent context is rolling (last 5 team matches).
# Only emitted for players with ≥ 1 appearance in the rolling window.
V_DECISION_READY = """
CREATE VIEW IF NOT EXISTS v_decision_ready AS
WITH max_finished AS (
    -- Latest finished GW, used as the default as_of_gw
    SELECT MAX(event) AS gw FROM fact_fixtures WHERE finished = 1
),

-- All player GW rows in the last 5 calendar GWs (including 0-minute)
player_recent AS (
    SELECT
        fpl_id, round, minutes, starts, total_points, bonus,
        us_xgi, us_xg, us_xa, ict_index, fpl_xgi,
        clean_sheets, goals_conceded, expected_goals_conceded,
        clearances_blocks_interceptions, defensive_contribution,
        value, selected, transfers_in, transfers_out,
        ROW_NUMBER() OVER (PARTITION BY fpl_id ORDER BY round DESC) AS rn
    FROM fact_player_gw, max_finished mf
    WHERE round > mf.gw - 5 AND round <= mf.gw
),

-- Rolling features anchored to calendar GWs
player_features AS (
    SELECT
        r.fpl_id,
        -- Per-90 stats (≥45 total rolling-window minutes to avoid cameo inflation)
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.us_xgi ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS xgi_per90,
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.bonus ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 2) AS bonus_per_app,
        -- Defensive stats (per-90, ≥45 min guard; cs_pct requires ≥60 min appearances)
        COALESCE(ROUND(
            SUM(CASE WHEN r.minutes >= 60 THEN r.clean_sheets ELSE 0 END) * 1.0
            / NULLIF(SUM(CASE WHEN r.minutes >= 60 THEN 1 ELSE 0 END), 0),
        2), 0) AS cs_pct,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.goals_conceded ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS gc_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.expected_goals_conceded ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS xgc_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.clearances_blocks_interceptions ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS cbi_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.defensive_contribution ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS def_per90,
        -- Participation: fraction of calendar GWs played / started
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 2) AS p_play,
        ROUND(SUM(r.starts) * 1.0 / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 2) AS p_start,
        -- Points std dev (only GWs with minutes)
        ROUND(SQRT(
            AVG(CASE WHEN r.minutes > 0 THEN r.total_points * r.total_points END)
          - AVG(CASE WHEN r.minutes > 0 THEN r.total_points END)
          * AVG(CASE WHEN r.minutes > 0 THEN r.total_points END)
        ), 2) AS pts_std,
        -- Latest cost & ownership (from most recent calendar GW, rn=1)
        MAX(CASE WHEN r.rn = 1 THEN r.value END) AS now_cost,
        MAX(CASE WHEN r.rn = 1 THEN r.selected END) AS selected_by,
        -- Rolling form sums (last 3 calendar GWs, only minutes > 0 contribute)
        SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.total_points ELSE 0 END) AS pts_last_3,
        ROUND(SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.us_xgi ELSE 0 END), 2) AS xgi_last_3,
        ROUND(SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.us_xg ELSE 0 END), 2) AS us_xg_last3,
        -- Transfer momentum (latest GW net transfers)
        MAX(CASE WHEN r.rn = 1 THEN r.transfers_in - r.transfers_out END) AS transfer_delta,
        -- Average minutes per appearance (only GWs with minutes > 0)
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.minutes ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 1) AS avg_minutes,
        -- How many of the calendar GWs the player actually played
        SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END) AS num_gwks_played
    FROM player_recent r
    GROUP BY r.fpl_id
),

-- Fixture tracker: one row per (team, next GW) with opponent context
next_fixtures AS (
    SELECT
        dt.fpl_id AS team_fpl_id,
        f.event AS gw,
        COUNT(*) AS fixture_count,
        CASE WHEN f.home_team_id = dt.fpl_id THEN 1 ELSE 0 END AS is_home,
        CASE WHEN f.home_team_id = dt.fpl_id THEN f.away_team_id
             ELSE f.home_team_id END AS opponent_team_id,
        CASE WHEN f.home_team_id = dt.fpl_id THEN f.home_difficulty
             ELSE f.away_difficulty END AS fdr
    FROM dim_teams dt
    JOIN fact_fixtures f ON (f.home_team_id = dt.fpl_id OR f.away_team_id = dt.fpl_id)
    WHERE f.finished = 0 AND f.event IS NOT NULL
      AND f.event = (
          SELECT MIN(f2.event) FROM fact_fixtures f2
          WHERE f2.finished = 0 AND f2.event IS NOT NULL
      )
    GROUP BY dt.fpl_id, f.fixture_id
)

SELECT
    (SELECT gw FROM max_finished) AS as_of_gw,
    nf.gw AS target_gw,
    dp.fpl_id,
    dp.web_name,
    dp.fpl_name,
    dt.short_name AS team,
    dt.fpl_id AS team_fpl_id,
    CASE dp.element_type
        WHEN 1 THEN 'GKP'
        WHEN 2 THEN 'DEF'
        WHEN 3 THEN 'MID'
        WHEN 4 THEN 'FWD'
    END AS position,
    -- Per-90 stats (rolling 5 GWs)
    pf.xgi_per90,
    pf.bonus_per_app,
    -- Defensive stats (rolling 5 GWs)
    pf.cs_pct,
    pf.gc_per90,
    pf.xgc_per90,
    pf.cbi_per90,
    pf.def_per90,
    -- Participation
    pf.p_play,
    pf.p_start,
    -- Uncertainty
    pf.pts_std,
    -- Cost & ownership
    pf.now_cost,
    pf.selected_by,
    -- Fixture context
    nf.fixture_count,
    nf.is_home,
    -- Rolling form sums
    pf.pts_last_3,
    pf.xgi_last_3,
    pf.us_xg_last3,
    -- Transfer momentum
    pf.transfer_delta,
    -- Availability
    pf.avg_minutes,
    -- Form window size
    pf.num_gwks_played
FROM player_features pf
JOIN dim_players dp ON dp.fpl_id = pf.fpl_id
JOIN dim_teams dt ON dt.team_id = dp.team_id
LEFT JOIN next_fixtures nf ON nf.team_fpl_id = dt.fpl_id
WHERE nf.gw IS NOT NULL        -- exclude players with no upcoming fixture (BGW)
  AND pf.num_gwks_played > 0          -- exclude players with no minutes in last 5 calendar GWs
ORDER BY pf.pts_last_3 DESC
"""

# ── All view definitions ────────────────────────────────────────────────
VIEWS = [
    ("v_player_season", V_PLAYER_SEASON),
    ("v_xg_divergence", V_XG_DIVERGENCE),
    ("v_form", V_FORM),
    ("v_fixture_ticker", V_FIXTURE_TICKER),
    ("v_fixture_opponents", V_FIXTURE_OPPONENTS),
    ("v_differentials", V_DIFFERENTIALS),
    ("v_team_strength", V_TEAM_STRENGTH),
    ("v_team_xg_gw", V_TEAM_XG_GW),
    ("v_captain_picks", V_CAPTAIN_PICKS),
    ("v_decision_ready", V_DECISION_READY),
]


def create_views(warehouse_db: str) -> int:
    """Create or replace all analytics views. Returns view count."""
    conn = sqlite3.connect(warehouse_db)
    conn.execute("PRAGMA journal_mode=WAL")
    for name, ddl in VIEWS:
        conn.execute(f"DROP VIEW IF EXISTS {name}")
        conn.execute(ddl)
    conn.commit()
    conn.close()
    logger.info("Analytics views created: %d", len(VIEWS))
    return len(VIEWS)


# ── Snapshot materialization ────────────────────────────────────────────

CREATE_SNAPSHOT_TABLE = """
CREATE TABLE IF NOT EXISTS fact_decision_snapshot (
    as_of_gw      INTEGER NOT NULL,
    target_gw     INTEGER NOT NULL,
    fpl_id        INTEGER NOT NULL,
    web_name      TEXT,
    fpl_name      TEXT,
    team          TEXT,
    -- team_fpl_id is the FPL integer team ID, NOT the warehouse surrogate.
    -- See dim_players.team_id for the warehouse surrogate key.
    team_fpl_id   INTEGER,
    position      TEXT,
    xgi_per90     REAL,
    bonus_per_app REAL,
    cs_pct        REAL,
    gc_per90      REAL,
    xgc_per90     REAL,
    cbi_per90     REAL,
    def_per90     REAL,
    p_play        REAL,
    p_start       REAL,
    pts_std       REAL,
    now_cost      REAL,
    selected_by   REAL,
    fixture_count INTEGER,
    is_home       INTEGER,
    pts_last_3    REAL,
    xgi_last_3    REAL,
    us_xg_last3   REAL,
    transfer_delta INTEGER,
    avg_minutes   REAL,
    num_gwks_played     INTEGER,
    PRIMARY KEY (as_of_gw, fpl_id)
)
"""

# Parameterised version of v_decision_ready: features built from data
# up to :as_of_gw, fixtures looked up for :as_of_gw + 1.
SNAPSHOT_SQL = """
WITH
player_recent AS (
    SELECT
        fpl_id, round, minutes, starts, total_points, bonus,
        us_xgi, us_xg, us_xa, ict_index, fpl_xgi,
        clean_sheets, goals_conceded, expected_goals_conceded,
        clearances_blocks_interceptions, defensive_contribution,
        value, selected, transfers_in, transfers_out,
        ROW_NUMBER() OVER (PARTITION BY fpl_id ORDER BY round DESC) AS rn
    FROM fact_player_gw
    WHERE round > :as_of_gw - 5 AND round <= :as_of_gw
),

player_features AS (
    SELECT
        r.fpl_id,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.us_xgi ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS xgi_per90,
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.bonus ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 2) AS bonus_per_app,
        COALESCE(ROUND(
            SUM(CASE WHEN r.minutes >= 60 THEN r.clean_sheets ELSE 0 END) * 1.0
            / NULLIF(SUM(CASE WHEN r.minutes >= 60 THEN 1 ELSE 0 END), 0),
        2), 0) AS cs_pct,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.goals_conceded ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS gc_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.expected_goals_conceded ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS xgc_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.clearances_blocks_interceptions ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS cbi_per90,
        CASE WHEN SUM(r.minutes) >= 45 THEN
            ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.defensive_contribution ELSE 0 END) * 90.0
                  / SUM(r.minutes), 2)
        ELSE 0 END AS def_per90,
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 2) AS p_play,
        ROUND(SUM(r.starts) * 1.0 / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 2) AS p_start,
        ROUND(SQRT(
            AVG(CASE WHEN r.minutes > 0 THEN r.total_points * r.total_points END)
          - AVG(CASE WHEN r.minutes > 0 THEN r.total_points END)
          * AVG(CASE WHEN r.minutes > 0 THEN r.total_points END)
        ), 2) AS pts_std,
        MAX(CASE WHEN r.rn = 1 THEN r.value END) AS now_cost,
        MAX(CASE WHEN r.rn = 1 THEN r.selected END) AS selected_by,
        SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.total_points ELSE 0 END) AS pts_last_3,
        ROUND(SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.us_xgi ELSE 0 END), 2) AS xgi_last_3,
        ROUND(SUM(CASE WHEN r.rn <= 3 AND r.minutes > 0 THEN r.us_xg ELSE 0 END), 2) AS us_xg_last3,
        MAX(CASE WHEN r.rn = 1 THEN r.transfers_in - r.transfers_out END) AS transfer_delta,
        ROUND(SUM(CASE WHEN r.minutes > 0 THEN r.minutes ELSE 0 END) * 1.0
              / NULLIF(SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END), 0), 1) AS avg_minutes,
        SUM(CASE WHEN r.minutes > 0 THEN 1 ELSE 0 END) AS num_gwks_played
    FROM player_recent r
    GROUP BY r.fpl_id
),

next_fixtures AS (
    SELECT
        dt.fpl_id AS team_fpl_id,
        :as_of_gw + 1 AS gw,
        COUNT(DISTINCT f.fixture_id) AS fixture_count,
        MAX(CASE WHEN f.home_team_id = dt.fpl_id THEN 1 ELSE 0 END) AS is_home
    FROM dim_teams dt
    JOIN fact_fixtures f ON (f.home_team_id = dt.fpl_id OR f.away_team_id = dt.fpl_id)
    WHERE f.event = :as_of_gw + 1 AND f.event IS NOT NULL
    GROUP BY dt.fpl_id
)

SELECT
    :as_of_gw AS as_of_gw,
    nf.gw AS target_gw,
    dp.fpl_id,
    dp.web_name,
    dp.fpl_name,
    dt.short_name AS team,
    dt.fpl_id AS team_fpl_id,
    CASE dp.element_type
        WHEN 1 THEN 'GKP'
        WHEN 2 THEN 'DEF'
        WHEN 3 THEN 'MID'
        WHEN 4 THEN 'FWD'
    END AS position,
    pf.xgi_per90,
    pf.bonus_per_app,
    pf.cs_pct,
    pf.gc_per90,
    pf.xgc_per90,
    pf.cbi_per90,
    pf.def_per90,
    pf.p_play,
    pf.p_start,
    pf.pts_std,
    pf.now_cost,
    pf.selected_by,
    nf.fixture_count,
    nf.is_home,
    pf.pts_last_3,
    pf.xgi_last_3,
    pf.us_xg_last3,
    pf.transfer_delta,
    pf.avg_minutes,
    pf.num_gwks_played
FROM player_features pf
JOIN dim_players dp ON dp.fpl_id = pf.fpl_id
JOIN dim_teams dt ON dt.team_id = dp.team_id
LEFT JOIN next_fixtures nf ON nf.team_fpl_id = dt.fpl_id
WHERE nf.gw IS NOT NULL
  AND pf.num_gwks_played > 0
"""


def materialize_snapshots(warehouse_db: str) -> int:
    """Build fact_decision_snapshot: one point-in-time row per (as_of_gw, player).

    Replays v_decision_ready logic for every finished GW so EDA and
    back-testing can read pre-computed, leak-free feature snapshots.
    """
    conn = sqlite3.connect(warehouse_db)
    conn.execute("PRAGMA journal_mode=WAL")

    max_gw = conn.execute(
        "SELECT MAX(event) FROM fact_fixtures WHERE finished = 1"
    ).fetchone()[0]

    if max_gw is None or max_gw < 1:
        logger.warning("No finished GWs — skipping snapshot materialization")
        conn.close()
        return 0

    conn.execute("DROP TABLE IF EXISTS fact_decision_snapshot")
    conn.execute(CREATE_SNAPSHOT_TABLE)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_gw ON fact_decision_snapshot(as_of_gw)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_player ON fact_decision_snapshot(fpl_id)")

    total_rows = 0
    for gw in range(1, max_gw + 1):  # as_of_gw 1 … max_gw
        cursor = conn.execute(
            f"INSERT INTO fact_decision_snapshot {SNAPSHOT_SQL}",
            {"as_of_gw": gw},
        )
        total_rows += cursor.rowcount

    conn.commit()
    conn.close()
    logger.info(
        "Materialized fact_decision_snapshot: %d rows across GWs 1-%d",
        total_rows,
        max_gw,
    )
    return total_rows
