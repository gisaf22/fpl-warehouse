"""Warehouse build logic.

Reads from FPL + Understat source databases, performs matching,
and writes unified dimension + fact tables to the warehouse DB.
"""

from __future__ import annotations

import html
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import requests

from .exceptions import TeamResolutionError
from .matching import (
    FPL_TO_UNDERSTAT_TEAM,
    invert_team_mapping,
    load_fpl_players,
    load_fpl_teams,
    load_understat_players,
    match_players,
)
from .views import create_views, materialize_snapshots

logger = logging.getLogger(__name__)

# ── Schema DDL ────────────────────────────────────────────────────────────

DIM_TEAMS_DDL = """
CREATE TABLE IF NOT EXISTS dim_teams (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fpl_id          INTEGER,
    fpl_name        TEXT,
    understat_name  TEXT,
    short_name      TEXT,
    UNIQUE(fpl_name)
)
"""

DIM_PLAYERS_DDL = """
CREATE TABLE IF NOT EXISTS dim_players (
    player_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fpl_id          INTEGER,
    understat_id    INTEGER,
    web_name        TEXT,
    fpl_name        TEXT,
    understat_name  TEXT,
    -- team_id is the warehouse SURROGATE key (dim_teams.team_id autoincrement),
    -- NOT the FPL integer ID. Use dim_teams.fpl_id for the FPL team integer.
    team_id         INTEGER,
    element_type    INTEGER,
    confidence      INTEGER,
    chance_of_playing_next_round REAL,
    news            TEXT,
    news_updated    TEXT,
    UNIQUE(fpl_id)
)
"""

FACT_PLAYER_GW_DDL = """
CREATE TABLE IF NOT EXISTS fact_player_gw (
    fpl_id              INTEGER,
    round               INTEGER,
    minutes             INTEGER,
    goals_scored        INTEGER,
    assists             INTEGER,
    clean_sheets        INTEGER,
    goals_conceded      INTEGER,
    bonus               INTEGER,
    bps                 INTEGER,
    total_points        INTEGER,
    value               INTEGER,
    selected            INTEGER,
    transfers_in        INTEGER,
    transfers_out       INTEGER,
    fpl_xg              REAL,
    fpl_xa              REAL,
    fpl_xgi             REAL,
    expected_goals_conceded REAL,
    influence           REAL,
    creativity          REAL,
    threat              REAL,
    ict_index           REAL,
    starts              INTEGER,
    tackles             INTEGER,
    recoveries          INTEGER,
    clearances_blocks_interceptions INTEGER,
    defensive_contribution INTEGER,
    us_xg               REAL,
    us_xa               REAL,
    us_xgi              REAL,
    xg_chain            REAL,
    xg_buildup          REAL,
    UNIQUE(fpl_id, round)
)
"""

FACT_SHOTS_DDL = """
CREATE TABLE IF NOT EXISTS fact_shots (
    shot_id         INTEGER PRIMARY KEY,
    match_id        INTEGER,
    understat_player_id INTEGER,
    minute          INTEGER,
    result          TEXT,
    x               REAL,
    y               REAL,
    xg              REAL,
    situation       TEXT,
    shot_type       TEXT,
    player          TEXT,
    h_a             TEXT,
    player_assisted TEXT,
    last_action     TEXT,
    season          TEXT,
    UNIQUE(shot_id)
)
"""

FACT_FIXTURES_DDL = """
CREATE TABLE IF NOT EXISTS fact_fixtures (
    fixture_id      INTEGER PRIMARY KEY,
    event           INTEGER,
    home_team_id    INTEGER,
    away_team_id    INTEGER,
    home_score      INTEGER,
    away_score      INTEGER,
    kickoff_time    TEXT,
    finished        INTEGER,
    home_difficulty INTEGER,
    away_difficulty INTEGER,
    UNIQUE(fixture_id)
)
"""

FACT_MATCH_STATS_DDL = """
CREATE TABLE IF NOT EXISTS fact_match_stats (
    understat_match_id  INTEGER PRIMARY KEY,
    fpl_fixture_id      INTEGER,
    event               INTEGER,
    home_fpl_id     INTEGER,
    away_fpl_id     INTEGER,
    home_team_name  TEXT,
    away_team_name  TEXT,
    home_goals      INTEGER,
    away_goals      INTEGER,
    home_xg         REAL,
    away_xg         REAL,
    home_ppda       REAL,
    away_ppda       REAL,
    home_deep       INTEGER,
    away_deep       INTEGER,
    home_shots      INTEGER,
    away_shots      INTEGER,
    home_sot        INTEGER,
    away_sot        INTEGER,
    prob_home       REAL,
    prob_draw       REAL,
    prob_away       REAL,
    datetime        TEXT,
    UNIQUE(understat_match_id)
)
"""

FACT_MANAGER_SQUAD_DDL = """
CREATE TABLE IF NOT EXISTS fact_manager_squad (
    team_id         INTEGER,
    gw              INTEGER,
    fpl_id          INTEGER,
    purchase_price  REAL,
    position        TEXT,
    is_captain      INTEGER,
    is_vice_captain INTEGER,
    PRIMARY KEY (team_id, gw, fpl_id)
)
"""

ALL_DDL = [
    DIM_TEAMS_DDL, DIM_PLAYERS_DDL, FACT_PLAYER_GW_DDL,
    FACT_SHOTS_DDL, FACT_FIXTURES_DDL, FACT_MATCH_STATS_DDL,
    FACT_MANAGER_SQUAD_DDL,
]


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # Remove stale WAL/SHM files that can cause disk I/O errors after crashes
    for suffix in ("-wal", "-shm"):
        stale = Path(db_path + suffix)
        if stale.exists():
            stale.unlink()
            logger.warning("Removed stale %s", stale)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(warehouse_db: str) -> None:
    """Create all warehouse tables."""
    conn = _connect(warehouse_db)
    for ddl in ALL_DDL:
        conn.execute(ddl)
    conn.commit()
    conn.close()
    logger.info("Warehouse schema created/verified at %s", warehouse_db)


def build_dim_teams(fpl_db: str, warehouse_db: str) -> Dict[str, int]:
    """Build dim_teams from FPL teams. Returns fpl_name → team_id mapping."""
    fpl_teams = load_fpl_teams(fpl_db)
    wh = _connect(warehouse_db)

    for fpl_id, team_info in fpl_teams.items():
        fpl_name = team_info["name"]
        us_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_name)
        short = team_info["short_name"]
        wh.execute(
            """INSERT INTO dim_teams (fpl_id, fpl_name, understat_name, short_name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(fpl_name) DO UPDATE SET
                   fpl_id=excluded.fpl_id,
                   understat_name=excluded.understat_name,
                   short_name=excluded.short_name""",
            (fpl_id, fpl_name, us_name, short),
        )
    wh.commit()

    # Return lookup
    rows = wh.execute("SELECT fpl_name, team_id FROM dim_teams").fetchall()
    mapping = {r["fpl_name"]: r["team_id"] for r in rows}
    wh.close()
    logger.info("dim_teams: %d rows", len(mapping))
    return mapping


def build_dim_players(
    fpl_db: str, understat_db: str, warehouse_db: str,
    team_lookup: Dict[str, int], threshold: int = 75,
) -> int:
    """Build dim_players via fuzzy matching. Returns count of matched players."""
    fpl_players = load_fpl_players(fpl_db)
    fpl_teams = load_fpl_teams(fpl_db)
    us_players = load_understat_players(understat_db)

    matched = match_players(fpl_players, fpl_teams, us_players, threshold=threshold)

    # Lookup element_type from FPL source data
    etype_lookup = {fp["id"]: fp.get("element_type") for fp in fpl_players}

    wh = _connect(warehouse_db)
    count = 0
    for m in matched:
        wh_team_id = team_lookup.get(m["fpl_team"])
        wh.execute(
            """INSERT INTO dim_players (fpl_id, understat_id, web_name, fpl_name, understat_name, team_id, element_type, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fpl_id) DO UPDATE SET
                   understat_id=excluded.understat_id,
                   web_name=excluded.web_name,
                   fpl_name=excluded.fpl_name,
                   understat_name=excluded.understat_name,
                   team_id=excluded.team_id,
                   element_type=excluded.element_type,
                   confidence=excluded.confidence""",
            (m["fpl_id"], m["understat_id"], m["web_name"], m["fpl_name"], m["understat_name"], wh_team_id, etype_lookup.get(m["fpl_id"]), m["confidence"]),
        )
        count += 1

    # Also insert unmatched FPL players (with NULL understat_id)
    matched_fpl_ids = {m["fpl_id"] for m in matched}
    for fp in fpl_players:
        if fp["id"] not in matched_fpl_ids:
            team_info = fpl_teams.get(fp["team"])
            fpl_team_name = team_info["name"] if team_info else ""
            wh_team_id = team_lookup.get(fpl_team_name)
            web_name = fp.get("web_name", "")
            full_name = f"{fp['first_name']} {fp['second_name']}"
            wh.execute(
                """INSERT INTO dim_players (fpl_id, understat_id, web_name, fpl_name, understat_name, team_id, element_type, confidence)
                   VALUES (?, NULL, ?, ?, NULL, ?, ?, NULL)
                   ON CONFLICT(fpl_id) DO NOTHING""",
                (fp["id"], web_name, full_name, wh_team_id, fp.get("element_type")),
            )

    wh.commit()
    total = wh.execute("SELECT COUNT(*) FROM dim_players").fetchone()[0]
    wh.close()
    logger.info("dim_players: %d total (%d matched)", total, count)
    return count


def build_fact_player_gw(fpl_db: str, warehouse_db: str) -> int:
    """Copy gameweek data from FPL into warehouse fact table (incl defensive stats)."""
    fpl = _connect(fpl_db)
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

    wh = _connect(warehouse_db)
    count = 0
    for r in rows:
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
            tuple(r),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_player_gw: %d rows", count)
    return count


def build_fact_shots(understat_db: str, warehouse_db: str) -> int:
    """Copy shot data from Understat into warehouse."""
    us = _connect(understat_db)
    rows = us.execute("""
        SELECT id, match_id, player_id, minute, result,
               X, Y, xG, situation, shotType,
               player, h_a, player_assisted, lastAction, season
        FROM shots
    """).fetchall()
    us.close()

    wh = _connect(warehouse_db)
    count = 0
    for r in rows:
        row = list(r)
        row[10] = html.unescape(row[10]) if row[10] else row[10]  # player
        row[12] = html.unescape(row[12]) if row[12] else row[12]  # player_assisted
        wh.execute(
            """INSERT INTO fact_shots
               (shot_id, match_id, understat_player_id, minute, result,
                x, y, xg, situation, shot_type,
                player, h_a, player_assisted, last_action, season)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(shot_id) DO UPDATE SET
                   xg=excluded.xg, result=excluded.result""",
            tuple(row),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_shots: %d rows", count)
    return count


def build_fact_fixtures(fpl_db: str, warehouse_db: str) -> int:
    """Copy fixture data from FPL into warehouse."""
    fpl = _connect(fpl_db)
    rows = fpl.execute("""
        SELECT id, event, team_h, team_a,
               team_h_score, team_a_score, kickoff_time, finished,
               team_h_difficulty, team_a_difficulty
        FROM fixtures
    """).fetchall()
    fpl.close()

    wh = _connect(warehouse_db)
    count = 0
    for r in rows:
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
            tuple(r),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_fixtures: %d rows", count)
    return count


def _build_fixture_bridge(fpl_db: str, understat_db: str) -> Dict[int, tuple]:
    """Match Understat match_id → FPL fixture_id + event via teams + date.

    Returns {understat_match_id: (fpl_fixture_id, event)}.
    """
    # Build FPL team ID → Understat name lookup
    fpl_teams = load_fpl_teams(fpl_db)  # {id: {name, short_name}}
    fpl_id_to_us_name = {
        tid: FPL_TO_UNDERSTAT_TEAM.get(info["name"], info["name"])
        for tid, info in fpl_teams.items()
    }

    # Load FPL fixtures with resolved team names
    fpl_conn = _connect(fpl_db)
    fpl_fixtures = fpl_conn.execute(
        "SELECT id, event, team_h, team_a, kickoff_time FROM fixtures"
    ).fetchall()
    fpl_conn.close()

    # Build lookup: (home_us_name, away_us_name, date_str) → (fixture_id, event)
    fpl_lookup: Dict[tuple, tuple] = {}
    for f in fpl_fixtures:
        home_us = fpl_id_to_us_name.get(f["team_h"], "")
        away_us = fpl_id_to_us_name.get(f["team_a"], "")
        # Normalise: "2025-08-15T19:00:00Z" → "2025-08-15"
        date_str = (f["kickoff_time"] or "")[:10]
        fpl_lookup[(home_us, away_us, date_str)] = (f["id"], f["event"])

    # Load Understat matches and match
    us_conn = _connect(understat_db)
    us_matches = us_conn.execute(
        "SELECT match_id, home_team, away_team, datetime FROM match_info"
    ).fetchall()
    us_conn.close()

    bridge: Dict[int, tuple] = {}
    for m in us_matches:
        date_str = (m["datetime"] or "")[:10]
        key = (m["home_team"], m["away_team"], date_str)
        if key in fpl_lookup:
            bridge[m["match_id"]] = fpl_lookup[key]

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

    Resolves Understat text team names to FPL integer IDs at load time.
    Raises TeamResolutionError if any team name cannot be resolved.
    """
    fpl_teams = load_fpl_teams(fpl_db)
    us_to_fpl_id = invert_team_mapping(fpl_teams)

    us = _connect(understat_db)
    rows = us.execute("""
        SELECT match_id, home_team, away_team, home_goals, away_goals,
               home_xg, away_xg, home_ppda, away_ppda,
               home_deep, away_deep, home_shots, away_shots,
               home_sot, away_sot, prob_home, prob_draw, prob_away, datetime
        FROM match_info
    """).fetchall()
    us.close()

    wh = _connect(warehouse_db)
    count = 0
    for r in rows:
        mid = r["match_id"]
        fpl_fid, event = bridge.get(mid, (None, None))

        home_name = r["home_team"]
        away_name = r["away_team"]
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
            (mid, fpl_fid, event,
             home_fpl_id, away_fpl_id, home_name, away_name,
             r["home_goals"], r["away_goals"],
             r["home_xg"], r["away_xg"], r["home_ppda"], r["away_ppda"],
             r["home_deep"], r["away_deep"], r["home_shots"], r["away_shots"],
             r["home_sot"], r["away_sot"], r["prob_home"], r["prob_draw"],
             r["prob_away"], r["datetime"]),
        )
        count += 1
    wh.commit()
    wh.close()
    logger.info("fact_match_stats: %d rows", count)
    return count


def _enrich_xg_chain_buildup(
    understat_db: str, warehouse_db: str,
    bridge: Dict[int, tuple],
) -> int:
    """Enrich fact_player_gw with Understat xG, xA, xGChain, xGBuildup.

    Sums across matches in the same GW (handles DGWs).
    """
    us = _connect(understat_db)
    roster_rows = us.execute("""
        SELECT player_id, match_id, xG, xA, xGChain, xGBuildup
        FROM rosters
    """).fetchall()
    us.close()

    # Aggregate by (understat_player_id, round) — SUM for DGWs
    agg: Dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for r in roster_rows:
        match_id = r["match_id"]
        if match_id not in bridge:
            continue
        _, event = bridge[match_id]
        if event is None:
            continue
        key = (r["player_id"], event)
        agg[key][0] += r["xG"] or 0.0
        agg[key][1] += r["xA"] or 0.0
        agg[key][2] += r["xGChain"] or 0.0
        agg[key][3] += r["xGBuildup"] or 0.0

    # Map understat_id → fpl_id via dim_players
    wh = _connect(warehouse_db)
    player_map = {}
    for row in wh.execute("SELECT fpl_id, understat_id FROM dim_players WHERE understat_id IS NOT NULL"):
        player_map[row["understat_id"]] = row["fpl_id"]

    count = 0
    for (us_pid, rnd), (xg, xa, chain, buildup) in agg.items():
        fpl_id = player_map.get(us_pid)
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


# ── Manager squad ────────────────────────────────────────────────────────

_POSITION_MAP: Dict[int, str] = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

_PICKS_URL = (
    "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/"
)


def build_fact_manager_squad(
    conn: sqlite3.Connection,
    team_id: int,
    gw: int,
) -> int:
    """Fetch manager's squad from FPL API and store in fact_manager_squad.

    Args:
        conn: Open connection to warehouse (master.db).
        team_id: FPL manager ID.
        gw: Gameweek number.

    Returns:
        Number of rows inserted (should be 15).
    """
    url = _PICKS_URL.format(team_id=team_id, gw=gw)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    picks = resp.json()["picks"]

    conn.execute(FACT_MANAGER_SQUAD_DDL)

    conn.execute(
        "DELETE FROM fact_manager_squad WHERE team_id = ? AND gw = ?",
        (team_id, gw),
    )

    count = 0
    for pick in picks:
        fpl_id = pick["element"]
        position = _POSITION_MAP.get(pick.get("element_type"), "MID")
        # Picks API doesn't include purchase_price — use current value as proxy
        row = conn.execute(
            "SELECT value FROM fact_player_gw "
            "WHERE fpl_id = ? AND value IS NOT NULL "
            "ORDER BY round DESC LIMIT 1",
            (fpl_id,),
        ).fetchone()
        pp = row[0] / 10.0 if row else None
        conn.execute(
            """INSERT INTO fact_manager_squad
               (team_id, gw, fpl_id, purchase_price, position,
                is_captain, is_vice_captain)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (team_id, gw, fpl_id, pp, position,
             1 if pick.get("is_captain") else 0,
             1 if pick.get("is_vice_captain") else 0),
        )
        count += 1

    conn.commit()
    logger.info("fact_manager_squad: %d rows for team %d GW %d", count, team_id, gw)
    return count


# ── Manager context (bank, FTs, chip) ────────────────────────────────────

_ENTRY_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/"
_ENTRY_HISTORY_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/history/"

_CHIP_UNLIMITED: frozenset[str] = frozenset({"wildcard", "freehit"})

DEFAULT_WAREHOUSE_DB: str = str(
    Path.home() / "Documents" / "FPL" / "data" / "warehouse" / "master.db"
)


def _compute_free_transfers(
    history: list[dict],
    chip_map: dict[int, str],
    started_event: int,
) -> tuple[int, str | None]:
    """Reconstruct FTs available for the next transfer deadline.

    Replays GW history from the manager's first event to derive the current
    free-transfer bank. Returns (free_transfers, chip_active) where
    free_transfers = 99 signals an unlimited chip was active in the most
    recent completed GW.

    Args:
        history: List of per-GW dicts from entry/history/ (current array).
        chip_map: Mapping of event → chip name for played chips.
        started_event: GW the manager joined (from entry endpoint).

    Returns:
        Tuple of (free_transfers, chip_active).
    """
    relevant = [row for row in history if row["event"] >= started_event]
    if not relevant:
        return 1, None

    fts = 1  # All managers begin their first GW with 1 free transfer
    for row in relevant:
        gw = row["event"]
        chip = chip_map.get(gw)
        if chip in _CHIP_UNLIMITED:
            if chip == "wildcard":
                fts = 1  # Wildcard resets the FT bank to 1 for next GW
            # freehit: FT bank unchanged (freehit is separate from stored FTs)
        else:
            ft_used = row["event_transfers"] - row["event_transfers_cost"] // 4
            fts = min(2, max(0, fts - ft_used) + 1)

    last_gw = relevant[-1]["event"]
    last_chip = chip_map.get(last_gw)
    if last_chip in _CHIP_UNLIMITED:
        return 99, last_chip
    return fts, None


def fetch_manager_context(team_id: int) -> dict:
    """Fetch current GW, bank, free transfers, and chip status for a manager.

    Makes two FPL API calls (entry + history). No DB access.

    Args:
        team_id: FPL manager ID.

    Returns:
        dict with keys:
            gw (int): Current gameweek (as_of_gw for recommend()).
            bank (float): Available bank in £m.
            free_transfers (int): FTs available for next deadline;
                99 means an unlimited chip was active in the latest GW.
            chip_active (str | None): Chip name if an unlimited chip was
                used in the most recent GW, else None.

    Raises:
        requests.HTTPError: If either FPL API call fails.
        RuntimeError: If manager has no GW history.
    """
    entry_resp = requests.get(_ENTRY_URL.format(team_id=team_id), timeout=15)
    entry_resp.raise_for_status()
    entry = entry_resp.json()

    history_resp = requests.get(
        _ENTRY_HISTORY_URL.format(team_id=team_id), timeout=15
    )
    history_resp.raise_for_status()
    history_data = history_resp.json()

    gw: int = entry["current_event"]
    bank: float = round(entry["last_deadline_bank"] / 10, 1)
    started_event: int = entry.get("started_event", 1)

    chip_map: dict[int, str] = {
        c["event"]: c["name"] for c in history_data.get("chips", [])
    }
    history: list[dict] = history_data.get("current", [])

    free_transfers, chip_active = _compute_free_transfers(
        history, chip_map, started_event
    )

    logger.info(
        "Manager %d: GW=%d bank=£%.1fm FTs=%s chip=%s",
        team_id, gw, bank, free_transfers, chip_active,
    )
    return {
        "gw": gw,
        "bank": bank,
        "free_transfers": free_transfers,
        "chip_active": chip_active,
    }


# ── refresh_manager_squad ────────────────────────────────────────────────


def refresh_manager_squad(
    team_id: int,
    warehouse_db: str = DEFAULT_WAREHOUSE_DB,
) -> None:
    """Detect current GW, fetch squad from FPL API, and store in warehouse.

    Convenience orchestrator: calls fetch_manager_context() to detect the
    current GW then delegates to build_fact_manager_squad().

    Args:
        team_id: FPL manager ID.
        warehouse_db: Path to master.db. Defaults to the standard location.
    """
    ctx = fetch_manager_context(team_id)
    gw = ctx["gw"]
    conn = sqlite3.connect(warehouse_db)
    try:
        build_fact_manager_squad(conn, team_id, gw)
    finally:
        conn.close()
    logger.info("Squad refreshed for team %d, GW %d", team_id, gw)


# ── Player availability ──────────────────────────────────────────────────

_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


def refresh_player_availability(conn: sqlite3.Connection) -> int:
    """Fetch bootstrap-static and update dim_players with availability info.

    Updates chance_of_playing_next_round, news, news_updated for all
    players. Also updates fact_player_gw.value for the latest GW to
    ensure now_cost is fresh.

    Args:
        conn: Open connection to warehouse (master.db).

    Returns:
        Number of players updated.
    """
    resp = requests.get(_BOOTSTRAP_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    elements = data["elements"]

    # Add availability columns if missing (schema migration)
    existing = {
        r[1] for r in conn.execute("PRAGMA table_info(dim_players)").fetchall()
    }
    for col, typ in [
        ("chance_of_playing_next_round", "REAL"),
        ("news", "TEXT"),
        ("news_updated", "TEXT"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE dim_players ADD COLUMN {col} {typ}")

    count = 0
    for el in elements:
        fpl_id = el["id"]
        raw = el.get("chance_of_playing_next_round")
        availability = raw / 100.0 if raw is not None else None
        news = el.get("news", "")
        news_updated = el.get("news_added", "")

        result = conn.execute(
            """UPDATE dim_players
               SET chance_of_playing_next_round = ?,
                   news = ?,
                   news_updated = ?
               WHERE fpl_id = ?""",
            (availability, news, news_updated, fpl_id),
        )
        if result.rowcount > 0:
            count += 1

    # Also refresh now_cost (value) in fact_player_gw for latest round
    max_round_row = conn.execute(
        "SELECT MAX(round) FROM fact_player_gw"
    ).fetchone()
    max_round = max_round_row[0] if max_round_row else None

    if max_round is not None:
        for el in elements:
            conn.execute(
                """UPDATE fact_player_gw
                   SET value = ?
                   WHERE fpl_id = ? AND round = ?""",
                (el["now_cost"], el["id"], max_round),
            )

    conn.commit()
    logger.info("Player availability refreshed: %d players updated", count)
    return count


# ── Data contract validation ──────────────────────────────────────────────


def validate_table_contract(
    conn: sqlite3.Connection,
    table: str,
    required_cols: List[str],
    grain_cols: List[str],
    min_rows: int = 1,
) -> None:
    """Validate a warehouse table against its data contract after build.

    Raises ValueError with clear message if any check fails.
    Downstream: called by build_all() after each table materialisation.

    Checks: table exists, required columns present, row count >= min_rows,
    grain is unique, no NULLs in required columns.
    """
    _contract_check_exists(conn, table)
    _contract_check_cols(conn, table, required_cols)
    _contract_check_rows(conn, table, min_rows)
    _contract_check_grain(conn, table, grain_cols)
    _contract_check_nulls(conn, table, required_cols)


def _contract_check_exists(conn: sqlite3.Connection, table: str) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Contract violation: table '{table}' does not exist")


def _contract_check_cols(
    conn: sqlite3.Connection, table: str, required_cols: List[str]
) -> None:
    pragma = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in pragma}
    missing = [c for c in required_cols if c not in existing]
    if missing:
        raise ValueError(
            f"Contract violation: '{table}' missing required columns: {missing}"
        )


def _contract_check_rows(
    conn: sqlite3.Connection, table: str, min_rows: int
) -> None:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count < min_rows:
        raise ValueError(
            f"Contract violation: '{table}' has {count} rows (min {min_rows})"
        )


def _contract_check_grain(
    conn: sqlite3.Connection, table: str, grain_cols: List[str]
) -> None:
    cols_sql = ", ".join(grain_cols)
    dup_count = conn.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT {cols_sql} FROM {table}"
        f"  GROUP BY {cols_sql} HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    if dup_count > 0:
        raise ValueError(
            f"Contract violation: '{table}' has {dup_count} duplicate "
            f"grain combinations ({grain_cols})"
        )


def _contract_check_nulls(
    conn: sqlite3.Connection, table: str, required_cols: List[str]
) -> None:
    for col in required_cols:
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
        ).fetchone()[0]
        if null_count > 0:
            raise ValueError(
                f"Contract violation: '{table}'.{col} has {null_count} NULL rows"
            )


def _validate_build_contracts(warehouse_db: str) -> None:
    """Run all table contract checks after a full build."""
    conn = _connect(warehouse_db)
    try:
        validate_table_contract(
            conn, "dim_teams", ["fpl_id", "fpl_name"], ["fpl_id"], min_rows=20
        )
        validate_table_contract(
            conn, "dim_players", ["fpl_id", "web_name"], ["fpl_id"], min_rows=400
        )
        validate_table_contract(
            conn, "fact_player_gw",
            ["fpl_id", "round", "total_points", "minutes"],
            ["fpl_id", "round"],
            min_rows=1000,
        )
        validate_table_contract(
            conn, "fact_transfer_snapshot",
            ["as_of_gw", "fpl_id"],
            ["as_of_gw", "fpl_id"],
            min_rows=5000,
        )
    finally:
        conn.close()
    logger.info("All data contract checks passed")


def build_all(
    fpl_db: str, understat_db: str, warehouse_db: str,
    threshold: int = 75,
) -> Dict[str, int]:
    """Run full warehouse build pipeline. Returns table → row count."""
    create_schema(warehouse_db)

    # Dimensions
    team_lookup = build_dim_teams(fpl_db, warehouse_db)
    matched = build_dim_players(fpl_db, understat_db, warehouse_db, team_lookup, threshold)

    # Fixture bridge (Understat match_id → FPL fixture_id + event)
    bridge = _build_fixture_bridge(fpl_db, understat_db)

    # Facts
    gw_count = build_fact_player_gw(fpl_db, warehouse_db)
    shots_count = build_fact_shots(understat_db, warehouse_db)
    fixtures_count = build_fact_fixtures(fpl_db, warehouse_db)
    match_stats_count = build_fact_match_stats(fpl_db, understat_db, warehouse_db, bridge)

    # Enrichment: xGChain/xGBuildup into fact_player_gw
    xg_enriched = _enrich_xg_chain_buildup(understat_db, warehouse_db, bridge)

    # Analytics views
    views_count = create_views(warehouse_db)

    # Point-in-time snapshots for EDA / back-testing
    snapshot_rows = materialize_snapshots(warehouse_db)

    # Transfer snapshot (extends fact_decision_snapshot)
    wh = sqlite3.connect(warehouse_db)
    build_fact_transfer_snapshot(wh)
    transfer_rows = wh.execute(
        "SELECT COUNT(*) FROM fact_transfer_snapshot"
    ).fetchone()[0]
    wh.close()

    _validate_build_contracts(warehouse_db)

    results = {
        "dim_teams": len(team_lookup),
        "dim_players_matched": matched,
        "fact_player_gw": gw_count,
        "fact_player_gw_xg_enriched": xg_enriched,
        "fact_shots": shots_count,
        "fact_fixtures": fixtures_count,
        "fact_match_stats": match_stats_count,
        "fixture_bridge": len(bridge),
        "views": views_count,
        "fact_decision_snapshot": snapshot_rows,
        "fact_transfer_snapshot": transfer_rows,
    }
    logger.info("Warehouse build complete: %s", results)
    return results


# ── Transfer snapshot ────────────────────────────────────────────────────

_CREATE_TRANSFER_SNAPSHOT_SQL = """
CREATE TABLE fact_transfer_snapshot AS
SELECT s.*,
       CAST(NULL AS REAL) AS bps_last_3,
       CAST(NULL AS REAL) AS threat_last_3,
       CAST(NULL AS REAL) AS creativity_last_3,
       CAST(NULL AS REAL) AS form_trajectory,
       CAST(NULL AS REAL) AS opp_vulnerability_last_3,
       CAST(NULL AS REAL) AS ict_index_last_3,
       CAST(NULL AS REAL) AS minutes_consistency,
       CAST(NULL AS REAL) AS price_velocity_3gw,
       CAST(NULL AS REAL) AS ownership_velocity_3gw,
       CAST(NULL AS INTEGER) AS role_change_flag,
       CAST(NULL AS INTEGER) AS team_deep_last_3,
       CAST(NULL AS INTEGER) AS team_sot_last_3
FROM fact_decision_snapshot s
"""


def _rolling_bps_threat_creativity(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
) -> tuple[float | None, float | None, float | None]:
    """BPS sum and decay-weighted threat/creativity over last 3 appearances."""
    rows = conn.execute(
        "SELECT bps, threat, creativity FROM fact_player_gw "
        "WHERE fpl_id = ? AND round <= ? AND minutes > 0 "
        "ORDER BY round DESC LIMIT 3",
        (fpl_id, as_of_gw),
    ).fetchall()
    if not rows:
        return None, None, None
    bps = sum(r[0] or 0 for r in rows)
    decay = [0.85 ** i for i in range(len(rows))]
    w = sum(decay)
    threat = round(sum((r[1] or 0) * d for r, d in zip(rows, decay)) / w, 2)
    creativity = round(sum((r[2] or 0) * d for r, d in zip(rows, decay)) / w, 2)
    return bps, threat, creativity


def _form_trajectory(
    conn: sqlite3.Connection, fpl_id: int,
    as_of_gw: int, pts_last_3: float | None,
) -> float | None:
    """pts at as_of_gw minus rolling average (pts_last_3 / 3)."""
    if as_of_gw < 2 or pts_last_3 is None:
        return None
    row = conn.execute(
        "SELECT total_points FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw),
    ).fetchone()
    if row is None:
        return None
    return round(row[0] - pts_last_3 / 3.0, 2)


def _opp_vulnerability_map(
    conn: sqlite3.Connection, as_of_gw: int, target_gw: int,
) -> Dict[int, float]:
    """Map team_fpl_id → opp_vulnerability for all teams with a target fixture."""
    fixtures = conn.execute(
        "SELECT home_team_id, away_team_id FROM fact_fixtures "
        "WHERE event = ?",
        (target_gw,),
    ).fetchall()
    result: Dict[int, float] = {}
    for home_id, away_id in fixtures:
        for team_id, opp_id in [(home_id, away_id), (away_id, home_id)]:
            matches = conn.execute(
                "SELECT "
                "CASE WHEN home_fpl_id=? THEN away_xg ELSE home_xg END, "
                "CASE WHEN home_fpl_id=? THEN home_ppda ELSE away_ppda END "
                "FROM fact_match_stats "
                "WHERE (home_fpl_id=? OR away_fpl_id=?) AND event <= ? "
                "ORDER BY event DESC LIMIT 3",
                (opp_id, opp_id, opp_id, opp_id, as_of_gw),
            ).fetchall()
            if matches:
                avg_xgc = sum(r[0] or 0 for r in matches) / len(matches)
                avg_ppda = sum(r[1] or 0 for r in matches) / len(matches)
                result[team_id] = round(avg_xgc * avg_ppda, 2)
    return result


def _ict_index_last_3(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
) -> float | None:
    """SUM(ict_index) over last 3 GWs where minutes > 0."""
    rows = conn.execute(
        "SELECT ict_index FROM fact_player_gw "
        "WHERE fpl_id = ? AND round <= ? AND minutes > 0 "
        "ORDER BY round DESC LIMIT 3",
        (fpl_id, as_of_gw),
    ).fetchall()
    if not rows:
        return None
    return round(sum(r[0] or 0 for r in rows), 2)


def _minutes_consistency(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
) -> float | None:
    """STDDEV(minutes) over last 5 GWs (all GWs, no minutes filter)."""
    rows = conn.execute(
        "SELECT minutes FROM fact_player_gw "
        "WHERE fpl_id = ? AND round <= ? "
        "ORDER BY round DESC LIMIT 5",
        (fpl_id, as_of_gw),
    ).fetchall()
    if len(rows) < 3:
        return None
    vals = [r[0] for r in rows]
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return round(variance ** 0.5, 2)


def _price_velocity_3gw(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
) -> float | None:
    """Price change over last 3 GWs, in £m."""
    if as_of_gw < 4:
        return None
    cur = conn.execute(
        "SELECT value FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw),
    ).fetchone()
    ago = conn.execute(
        "SELECT value FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw - 3),
    ).fetchone()
    if cur is None or ago is None or cur[0] is None or ago[0] is None:
        return None
    return round((cur[0] - ago[0]) / 10.0, 1)


def _ownership_velocity_3gw(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
) -> int | None:
    """Ownership change (raw selected count) over last 3 GWs."""
    if as_of_gw < 4:
        return None
    cur = conn.execute(
        "SELECT selected FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw),
    ).fetchone()
    ago = conn.execute(
        "SELECT selected FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw - 3),
    ).fetchone()
    if cur is None or ago is None or cur[0] is None or ago[0] is None:
        return None
    return cur[0] - ago[0]


def _role_change_flag(
    conn: sqlite3.Connection, fpl_id: int, as_of_gw: int,
    threat_last_3: float | None, creativity_last_3: float | None,
) -> int | None:
    """Binary flag: 1 if recent threat or creativity spike vs rolling avg."""
    if as_of_gw < 2 or threat_last_3 is None or creativity_last_3 is None:
        return None
    row = conn.execute(
        "SELECT threat, creativity FROM fact_player_gw "
        "WHERE fpl_id = ? AND round = ?",
        (fpl_id, as_of_gw),
    ).fetchone()
    if row is None:
        return None
    t_now, c_now = row[0] or 0, row[1] or 0
    if t_now > threat_last_3 * 1.5 or c_now > creativity_last_3 * 1.5:
        return 1
    return 0


def _team_stat_last_3(
    conn: sqlite3.Connection, as_of_gw: int,
    stat: str,
) -> Dict[int, int]:
    """Map team_fpl_id → sum of *stat* over last 3 team matches.

    stat must be 'deep' or 'sot'.  DGW matches both count.
    """
    teams = conn.execute(
        "SELECT DISTINCT home_fpl_id FROM fact_match_stats "
        "WHERE event <= ? "
        "UNION "
        "SELECT DISTINCT away_fpl_id FROM fact_match_stats "
        "WHERE event <= ?",
        (as_of_gw, as_of_gw),
    ).fetchall()
    result: Dict[int, int] = {}
    for (team_id,) in teams:
        rows = conn.execute(
            f"SELECT CASE WHEN home_fpl_id=? THEN home_{stat} "
            f"            ELSE away_{stat} END AS val "
            "FROM fact_match_stats "
            "WHERE (home_fpl_id=? OR away_fpl_id=?) AND event <= ? "
            "ORDER BY event DESC, understat_match_id DESC LIMIT 3",
            (team_id, team_id, team_id, as_of_gw),
        ).fetchall()
        if rows:
            result[team_id] = sum(r[0] or 0 for r in rows)
    return result


def _update_transfer_snapshot_gw(
    conn: sqlite3.Connection, as_of_gw: int,
) -> None:
    """Update all 12 new features for one as_of_gw slice."""
    rows = conn.execute(
        "SELECT fpl_id, pts_last_3, team_fpl_id, target_gw "
        "FROM fact_transfer_snapshot WHERE as_of_gw = ?",
        (as_of_gw,),
    ).fetchall()
    if not rows:
        return
    target_gw = rows[0][3]
    vuln_map = _opp_vulnerability_map(conn, as_of_gw, target_gw) if target_gw else {}
    deep_map = _team_stat_last_3(conn, as_of_gw, "deep")
    sot_map = _team_stat_last_3(conn, as_of_gw, "sot")
    for fpl_id, pts_last_3, team_fpl_id, _ in rows:
        bps, threat, creat = _rolling_bps_threat_creativity(conn, fpl_id, as_of_gw)
        form = _form_trajectory(conn, fpl_id, as_of_gw, pts_last_3)
        vuln = vuln_map.get(team_fpl_id)
        ict = _ict_index_last_3(conn, fpl_id, as_of_gw)
        mins = _minutes_consistency(conn, fpl_id, as_of_gw)
        pv = _price_velocity_3gw(conn, fpl_id, as_of_gw)
        ov = _ownership_velocity_3gw(conn, fpl_id, as_of_gw)
        rcf = _role_change_flag(conn, fpl_id, as_of_gw, threat, creat)
        td = deep_map.get(team_fpl_id)
        ts = sot_map.get(team_fpl_id)
        conn.execute(
            "UPDATE fact_transfer_snapshot "
            "SET bps_last_3=?, threat_last_3=?, creativity_last_3=?, "
            "    form_trajectory=?, opp_vulnerability_last_3=?, "
            "    ict_index_last_3=?, minutes_consistency=?, "
            "    price_velocity_3gw=?, ownership_velocity_3gw=?, "
            "    role_change_flag=?, team_deep_last_3=?, "
            "    team_sot_last_3=? "
            "WHERE fpl_id=? AND as_of_gw=?",
            (bps, threat, creat, form, vuln, ict, mins, pv, ov, rcf,
             td, ts, fpl_id, as_of_gw),
        )


def build_fact_transfer_snapshot(
    conn: sqlite3.Connection,
    season: str = "2024-25",
) -> None:
    """Build fact_transfer_snapshot: 27 base cols + 12 transfer features.

    Starts from fact_decision_snapshot. Adds bps_last_3, threat_last_3,
    creativity_last_3, form_trajectory, opp_vulnerability_last_3,
    ict_index_last_3, minutes_consistency, price_velocity_3gw,
    ownership_velocity_3gw, role_change_flag, team_deep_last_3,
    team_sot_last_3.
    All features use round/event <= as_of_gw, matching the base snapshot convention.
    """
    conn.execute("DROP TABLE IF EXISTS fact_transfer_snapshot")
    conn.execute(_CREATE_TRANSFER_SNAPSHOT_SQL)
    logger.info("fact_transfer_snapshot created from base snapshot")

    gws = [r[0] for r in conn.execute(
        "SELECT DISTINCT as_of_gw FROM fact_transfer_snapshot ORDER BY 1"
    ).fetchall()]

    for gw in gws:
        _update_transfer_snapshot_gw(conn, gw)
        logger.info("GW %d complete", gw)

    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) FROM fact_transfer_snapshot"
    ).fetchone()[0]
    cols = len(conn.execute(
        "PRAGMA table_info(fact_transfer_snapshot)"
    ).fetchall())
    logger.info("fact_transfer_snapshot: %d rows, %d cols", total, cols)
