"""Dimension table builders: teams, gameweeks, players."""

from __future__ import annotations

import logging
import sqlite3
from typing import Dict

from ..integration.matching import (
    FPL_TO_UNDERSTAT_TEAM,
    load_fpl_player_codes,
    load_fpl_players,
    load_fpl_teams,
    load_reep_map,
    load_understat_players,
    match_players,
)
from ..integration.team_resolution import resolve_player_team_id, resolve_team_name_id
from ..warehouse.db import connect_db, connect_warehouse

logger = logging.getLogger(__name__)


def _upsert_dim_team(
    conn: sqlite3.Connection,
    fpl_id: int,
    fpl_name: str,
    understat_name: str | None,
    short_name: str,
) -> None:
    """Insert or update one dim_teams row."""
    conn.execute(
        """INSERT INTO dim_teams (fpl_id, fpl_name, understat_name, short_name)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(fpl_name) DO UPDATE SET
               fpl_id=excluded.fpl_id,
               understat_name=excluded.understat_name,
               short_name=excluded.short_name""",
        (fpl_id, fpl_name, understat_name, short_name),
    )


def _load_team_lookup(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return fpl_name to warehouse team_id mapping from dim_teams."""
    rows = conn.execute("SELECT fpl_name, team_id FROM dim_teams").fetchall()
    return {row["fpl_name"]: row["team_id"] for row in rows}


def _upsert_dim_gameweek(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    """Insert or update one dim_gameweeks row."""
    conn.execute(
        """INSERT INTO dim_gameweeks (gw_id, deadline_time, finished, is_current, is_next)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(gw_id) DO UPDATE SET
               deadline_time=excluded.deadline_time,
               finished=excluded.finished,
               is_current=excluded.is_current,
               is_next=excluded.is_next""",
        (row["id"], row["deadline_time"], row["finished"], row["is_current"], row["is_next"]),
    )


def _player_full_name(player: dict) -> str:
    """Return canonical FPL full name for dim_players."""
    return f"{player['first_name']} {player['second_name']}"


def _upsert_matched_players(
    conn: sqlite3.Connection,
    matched: list[dict],
    team_lookup: Dict[str, int],
    element_type_lookup: Dict[int, int | None],
) -> int:
    """Insert or update matched FPL to Understat player rows."""
    count = 0
    for match in matched:
        warehouse_team_id = resolve_team_name_id(match["fpl_team"], team_lookup)
        conn.execute(
            """INSERT INTO dim_players
               (fpl_id, understat_id, web_name, fpl_name, understat_name,
                team_id, element_type, confidence, match_tier)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fpl_id) DO UPDATE SET
                   understat_id=excluded.understat_id,
                   web_name=excluded.web_name,
                   fpl_name=excluded.fpl_name,
                   understat_name=excluded.understat_name,
                   team_id=excluded.team_id,
                   element_type=excluded.element_type,
                   confidence=excluded.confidence,
                   match_tier=excluded.match_tier""",
            (
                match["fpl_id"],
                match["understat_id"],
                match["web_name"],
                match["fpl_name"],
                match["understat_name"],
                warehouse_team_id,
                element_type_lookup.get(match["fpl_id"]),
                match["confidence"],
                match["match_tier"],
            ),
        )
        count += 1
    return count


def _insert_unmatched_players(
    conn: sqlite3.Connection,
    fpl_players: list[dict],
    matched: list[dict],
    fpl_teams: Dict[int, dict],
    team_lookup: Dict[str, int],
) -> None:
    """Insert unmatched FPL players with NULL Understat identifiers."""
    matched_fpl_ids = {match["fpl_id"] for match in matched}
    for player in fpl_players:
        if player["id"] in matched_fpl_ids:
            continue
        warehouse_team_id = resolve_player_team_id(player, fpl_teams, team_lookup)
        conn.execute(
            """INSERT INTO dim_players
               (fpl_id, understat_id, web_name, fpl_name, understat_name,
                team_id, element_type, confidence, match_tier)
               VALUES (?, NULL, ?, ?, NULL, ?, ?, NULL, NULL)
               ON CONFLICT(fpl_id) DO NOTHING""",
            (
                player["id"],
                player.get("web_name", ""),
                _player_full_name(player),
                warehouse_team_id,
                player.get("element_type"),
            ),
        )


def build_dim_teams(fpl_db: str, warehouse_db: str) -> Dict[str, int]:
    """Build or refresh the team dimension from the FPL source database.

    Args:
        fpl_db: Path to the FPL source database.
        warehouse_db: Path to the writable warehouse database.

    Returns:
        Mapping of FPL team name to warehouse team_id, used by downstream
        builders when resolving player team membership.
    """
    fpl_teams = load_fpl_teams(fpl_db)
    wh = connect_warehouse(warehouse_db)

    for fpl_id, team_info in fpl_teams.items():
        _upsert_dim_team(
            wh,
            fpl_id,
            team_info["name"],
            FPL_TO_UNDERSTAT_TEAM.get(team_info["name"]),
            team_info["short_name"],
        )
    wh.commit()

    mapping = _load_team_lookup(wh)
    wh.close()
    logger.info("dim_teams: %d rows", len(mapping))
    return mapping


def build_dim_gameweeks(fpl_db: str, warehouse_db: str) -> int:
    """Build or refresh the gameweek dimension from the FPL events table.

    Args:
        fpl_db: Path to the FPL source database.
        warehouse_db: Path to the writable warehouse database.

    Returns:
        Number of gameweek rows loaded from the source events table.
    """
    fpl = connect_db(fpl_db)
    rows = fpl.execute(
        "SELECT id, deadline_time, finished, is_current, is_next FROM events"
    ).fetchall()
    fpl.close()

    wh = connect_warehouse(warehouse_db)
    for row in rows:
        _upsert_dim_gameweek(wh, row)
    wh.commit()
    count = len(rows)
    wh.close()
    logger.info("dim_gameweeks: %d rows", count)
    return count


def build_dim_players(
    fpl_db: str, understat_db: str, warehouse_db: str,
    team_lookup: Dict[str, int], threshold: int = 75,
) -> int:
    """Build or refresh the player dimension using FPL and Understat data.

    Matched players receive both FPL and Understat identifiers. Unmatched FPL
    players are still inserted so downstream warehouse tables can reference a
    complete player universe even when cross-source matching is incomplete.

    Args:
        fpl_db: Path to the FPL source database.
        understat_db: Path to the Understat source database.
        warehouse_db: Path to the writable warehouse database.
        team_lookup: Mapping of FPL team name to warehouse team_id.
        threshold: Minimum fuzzy-match confidence for player matching.

    Returns:
        Number of matched players written with non-null Understat identifiers.
    """
    fpl_players = load_fpl_players(fpl_db)
    fpl_teams = load_fpl_teams(fpl_db)
    us_players = load_understat_players(understat_db)
    fpl_player_codes = load_fpl_player_codes(fpl_db)
    reep_map = load_reep_map()

    matched = match_players(
        fpl_players, fpl_teams, us_players, fpl_player_codes, reep_map, threshold=threshold
    )
    etype_lookup = {fp["id"]: fp.get("element_type") for fp in fpl_players}

    wh = connect_warehouse(warehouse_db)
    count = _upsert_matched_players(wh, matched, team_lookup, etype_lookup)

    _insert_unmatched_players(wh, fpl_players, matched, fpl_teams, team_lookup)

    wh.commit()
    total = wh.execute("SELECT COUNT(*) FROM dim_players").fetchone()[0]
    wh.close()
    logger.info("dim_players: %d total (%d matched)", total, count)
    return count