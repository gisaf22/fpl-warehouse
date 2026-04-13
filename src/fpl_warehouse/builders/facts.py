"""Fact table builders: player GW stats, shots, fixtures, match stats, xG enrichment."""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from typing import Dict

from ..integration.matching import (
    FPL_TO_UNDERSTAT_TEAM,
    invert_team_mapping,
    load_fpl_teams,
)
from ..warehouse.db import connect_db, connect_warehouse
from ..integration.exceptions import TeamResolutionError

logger = logging.getLogger(__name__)


def build_fact_player_gw(fpl_db: str, warehouse_db: str) -> int:
    """Copy gameweek data from FPL into fact_player_gw."""
    fpl = connect_db(fpl_db)
    rows = fpl.execute("""
        SELECT element_id, round, minutes, goals_scored, assists,
               clean_sheets, goals_conceded, bonus, bps, total_points,
               value, selected, transfers_in, transfers_out,
               expected_goals, expected_assists, expected_goal_involvements,
               expected_goals_conceded, influence, creativity, threat,
               ict_index, starts,
               tackles, recoveries, clearances_blocks_interceptions,
               defensive_contribution
        FROM gameweeks
    """).fetchall()
    fpl.close()

    wh = connect_warehouse(warehouse_db)
    count = 0
    for row in rows:
        wh.execute(
            """INSERT INTO fact_player_gw
               (fpl_id, round, minutes, goals_scored, assists, clean_sheets,
                goals_conceded, bonus, bps, total_points, value, selected,
                transfers_in, transfers_out, fpl_xg, fpl_xa,
                fpl_xgi, expected_goals_conceded,
                influence, creativity, threat, ict_index, starts,
                tackles, recoveries, clearances_blocks_interceptions,
                defensive_contribution)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(fpl_id, round) DO UPDATE SET
                   minutes=excluded.minutes, goals_scored=excluded.goals_scored,
                   assists=excluded.assists, total_points=excluded.total_points,
                   value=excluded.value, selected=excluded.selected,
                   fpl_xg=excluded.fpl_xg,
                   fpl_xa=excluded.fpl_xa,
                   tackles=excluded.tackles, recoveries=excluded.recoveries,
                   clearances_blocks_interceptions=excluded.clearances_blocks_interceptions,
                   defensive_contribution=excluded.defensive_contribution""",
            tuple(row),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_player_gw: %d rows", count)
    return count


def build_fact_shots(understat_db: str, warehouse_db: str) -> int:
    """Copy shot data from Understat into fact_shots."""
    us = connect_db(understat_db)
    rows = us.execute("""
        SELECT id, match_id, player_id, minute, result,
               X, Y, xG, situation, shotType,
               player, h_a, player_assisted, lastAction, season
        FROM shots
    """).fetchall()
    us.close()

    wh = connect_warehouse(warehouse_db)
    count = 0
    for row in rows:
        clean_row = list(row)
        clean_row[10] = html.unescape(clean_row[10]) if clean_row[10] else clean_row[10]
        clean_row[12] = html.unescape(clean_row[12]) if clean_row[12] else clean_row[12]
        wh.execute(
            """INSERT INTO fact_shots
               (shot_id, match_id, understat_player_id, minute, result,
                x, y, xg, situation, shot_type,
                player, h_a, player_assisted, last_action, season)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(shot_id) DO UPDATE SET
                   xg=excluded.xg, result=excluded.result""",
            tuple(clean_row),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_shots: %d rows", count)
    return count


def build_fact_fixtures(fpl_db: str, warehouse_db: str) -> int:
    """Copy fixture data from FPL into fact_fixtures."""
    fpl = connect_db(fpl_db)
    rows = fpl.execute("""
        SELECT id, event, team_h, team_a,
               team_h_score, team_a_score, kickoff_time, finished,
               team_h_difficulty, team_a_difficulty
        FROM fixtures
    """).fetchall()
    fpl.close()

    wh = connect_warehouse(warehouse_db)
    count = 0
    for row in rows:
        wh.execute(
            """INSERT INTO fact_fixtures
               (fixture_id, event, home_team_id, away_team_id,
                home_score, away_score, kickoff_time, finished,
                home_difficulty, away_difficulty)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(fixture_id) DO UPDATE SET
                   home_score=excluded.home_score,
                   away_score=excluded.away_score,
                   finished=excluded.finished""",
            tuple(row),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_fixtures: %d rows", count)
    return count


def build_fixture_bridge(fpl_db: str, understat_db: str) -> Dict[int, tuple]:
    """Match Understat match_id to (fpl_fixture_id, event) via teams and date."""
    fpl_teams = load_fpl_teams(fpl_db)
    fpl_id_to_us_name = {
        team_id: FPL_TO_UNDERSTAT_TEAM.get(info["name"], info["name"])
        for team_id, info in fpl_teams.items()
    }

    fpl_conn = connect_db(fpl_db)
    fpl_fixtures = fpl_conn.execute(
        "SELECT id, event, team_h, team_a, kickoff_time FROM fixtures"
    ).fetchall()
    fpl_conn.close()

    fpl_lookup: Dict[tuple, tuple] = {}
    for fixture in fpl_fixtures:
        home_us = fpl_id_to_us_name.get(fixture["team_h"], "")
        away_us = fpl_id_to_us_name.get(fixture["team_a"], "")
        date_str = (fixture["kickoff_time"] or "")[:10]
        fpl_lookup[(home_us, away_us, date_str)] = (fixture["id"], fixture["event"])

    us_conn = connect_db(understat_db)
    us_matches = us_conn.execute(
        "SELECT match_id, home_team, away_team, datetime FROM match_info"
    ).fetchall()
    us_conn.close()

    bridge: Dict[int, tuple] = {}
    for match in us_matches:
        date_str = (match["datetime"] or "")[:10]
        key = (match["home_team"], match["away_team"], date_str)
        if key in fpl_lookup:
            bridge[match["match_id"]] = fpl_lookup[key]

    logger.info(
        "Fixture bridge: %d/%d Understat matches mapped to FPL fixtures",
        len(bridge), len(us_matches),
    )
    return bridge


def build_fact_match_stats(
    fpl_db: str, understat_db: str, warehouse_db: str,
    bridge: Dict[int, tuple],
) -> int:
    """Build fact_match_stats from Understat match_info with FPL fixture bridge.

    Raises TeamResolutionError if any Understat team name cannot be resolved to an fpl_id.
    """
    fpl_teams = load_fpl_teams(fpl_db)
    us_to_fpl_id = invert_team_mapping(fpl_teams)

    us = connect_db(understat_db)
    rows = us.execute("""
        SELECT match_id, home_team, away_team, home_goals, away_goals,
               home_xg, away_xg, home_ppda, away_ppda,
               home_deep, away_deep, home_shots, away_shots,
               home_sot, away_sot, prob_home, prob_draw, prob_away, datetime
        FROM match_info
    """).fetchall()
    us.close()

    wh = connect_warehouse(warehouse_db)
    count = 0
    for row in rows:
        match_id = row["match_id"]
        fpl_fixture_id, event = bridge.get(match_id, (None, None))

        home_name = row["home_team"]
        away_name = row["away_team"]
        home_fpl_id = us_to_fpl_id.get(home_name)
        away_fpl_id = us_to_fpl_id.get(away_name)

        if home_fpl_id is None:
            raise TeamResolutionError(
                f"Cannot resolve Understat home team to fpl_id: {home_name!r}"
            )
        if away_fpl_id is None:
            raise TeamResolutionError(
                f"Cannot resolve Understat away team to fpl_id: {away_name!r}"
            )

        wh.execute(
            """INSERT INTO fact_match_stats
               (understat_match_id, fpl_fixture_id, event,
                home_fpl_id, away_fpl_id, home_team_name, away_team_name,
                home_goals, away_goals,
                home_xg, away_xg, home_ppda, away_ppda,
                home_deep, away_deep, home_shots, away_shots,
                home_sot, away_sot, prob_home, prob_draw, prob_away, datetime)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(understat_match_id) DO UPDATE SET
                   fpl_fixture_id=excluded.fpl_fixture_id,
                   event=excluded.event,
                   home_fpl_id=excluded.home_fpl_id,
                   away_fpl_id=excluded.away_fpl_id,
                   home_ppda=excluded.home_ppda,
                   away_ppda=excluded.away_ppda""",
            (
                match_id, fpl_fixture_id, event,
                home_fpl_id, away_fpl_id, home_name, away_name,
                row["home_goals"], row["away_goals"],
                row["home_xg"], row["away_xg"], row["home_ppda"], row["away_ppda"],
                row["home_deep"], row["away_deep"], row["home_shots"], row["away_shots"],
                row["home_sot"], row["away_sot"], row["prob_home"], row["prob_draw"],
                row["prob_away"], row["datetime"],
            ),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_match_stats: %d rows", count)
    return count


def enrich_xg_chain_buildup(
    understat_db: str, warehouse_db: str,
    bridge: Dict[int, tuple],
) -> int:
    """Enrich fact_player_gw with Understat xG, xA, xGChain, xGBuildup."""
    us = connect_db(understat_db)
    roster_rows = us.execute("""
        SELECT player_id, match_id, xG, xA, xGChain, xGBuildup
        FROM rosters
    """).fetchall()
    us.close()

    agg: Dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for row in roster_rows:
        match_id = row["match_id"]
        if match_id not in bridge:
            continue
        _, event = bridge[match_id]
        if event is None:
            continue
        key = (row["player_id"], event)
        agg[key][0] += row["xG"] or 0.0
        agg[key][1] += row["xA"] or 0.0
        agg[key][2] += row["xGChain"] or 0.0
        agg[key][3] += row["xGBuildup"] or 0.0

    wh = connect_warehouse(warehouse_db)
    player_map = {
        row["understat_id"]: row["fpl_id"]
        for row in wh.execute(
            "SELECT fpl_id, understat_id FROM dim_players WHERE understat_id IS NOT NULL"
        )
    }

    count = 0
    for (understat_player_id, rnd), (xg, xa, chain, buildup) in agg.items():
        fpl_id = player_map.get(understat_player_id)
        if fpl_id is None:
            continue
        xgi = round(xg + xa, 4)
        wh.execute(
            """UPDATE fact_player_gw
               SET us_xg = ?, us_xa = ?, us_xgi = ?, xg_chain = ?, xg_buildup = ?
               WHERE fpl_id = ? AND round = ?""",
            (round(xg, 4), round(xa, 4), xgi, round(chain, 4), round(buildup, 4), fpl_id, rnd),
        )
        if wh.execute("SELECT changes()").fetchone()[0] > 0:
            count += 1

    wh.commit()
    wh.close()
    logger.info("Understat xG/xA/xGChain/xGBuildup enriched: %d player-GW rows updated", count)
    return count