"""Team and player matching between FPL and Understat.

Tiered matching strategy:
  1. Exact match on full name (first_name + second_name) + team
  2. Accent-stripped exact match + team
  3. Fuzzy match (>=threshold) + team + position guard
  4. Cross-team fallback for mid-season transfers: exact/fuzzy name + position guard (no team)
"""

from __future__ import annotations

import html
import logging
import sqlite3
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

MANUAL_OVERRIDES: Dict[int, int] = {
    511: 13068,
    518: 12766,
    612: 7365,
    646: 11384,
}

FPL_TO_UNDERSTAT_TEAM: Dict[str, str] = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds": "Leeds",
    "Liverpool": "Liverpool",
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Spurs": "Tottenham",
    "Sunderland": "Sunderland",
    "West Ham": "West Ham",
    "Wolves": "Wolverhampton Wanderers",
}
UNDERSTAT_TO_FPL_TEAM = {value: key for key, value in FPL_TO_UNDERSTAT_TEAM.items()}


def invert_team_mapping(
    fpl_teams: Dict[int, Dict[str, Any]],
) -> Dict[str, int]:
    """Build {understat_name: fpl_id} from FPL_TO_UNDERSTAT_TEAM + FPL teams."""
    fpl_name_to_id: Dict[str, int] = {
        info["name"]: team_id for team_id, info in fpl_teams.items()
    }
    result: Dict[str, int] = {}
    for fpl_name, us_name in FPL_TO_UNDERSTAT_TEAM.items():
        fpl_id = fpl_name_to_id.get(fpl_name)
        if fpl_id is None:
            continue
        result[us_name] = fpl_id

    ids = list(result.values())
    if len(ids) != len(set(ids)):
        raise ValueError("invert_team_mapping: duplicate fpl_ids detected")

    return result


_US_POS_TO_FPL_TYPE: Dict[str, int] = {
    "GK": 1,
    "DC": 2, "DL": 2, "DR": 2,
    "DMC": 3, "DML": 3, "DMR": 3,
    "MC": 3, "ML": 3, "MR": 3,
    "AMC": 3, "AML": 3, "AMR": 3,
    "FW": 4, "FWL": 4, "FWR": 4,
}


def _strip_accents(s: str) -> str:
    """Remove diacritics: Odegaard style normalization."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(char for char in nfkd if not unicodedata.combining(char))


def _normalise(name: str) -> str:
    """Lowercase, strip accents, remove hyphens and apostrophes."""
    normalized = _strip_accents(name.strip().lower())
    normalized = normalized.replace("-", " ").replace("'", "").replace("'", "")
    return normalized


def load_fpl_players(fpl_db: str) -> List[Dict[str, Any]]:
    """Load players from FPL database."""
    conn = sqlite3.connect(fpl_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, first_name, second_name, web_name, team, element_type FROM players"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def load_fpl_teams(fpl_db: str) -> Dict[int, Dict[str, Any]]:
    """Load team id to {name, short_name} mapping from FPL database."""
    conn = sqlite3.connect(fpl_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name, short_name FROM teams").fetchall()
    conn.close()
    return {
        row["id"]: {"name": row["name"], "short_name": row["short_name"]}
        for row in rows
    }


def load_understat_players(understat_db: str) -> List[Dict[str, Any]]:
    """Load distinct players from Understat rosters with position."""
    conn = sqlite3.connect(understat_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            r.player_id,
            r.player,
            r.team_id,
            r.position,
            m.home_team,
            m.away_team,
            r.h_a
        FROM rosters r
        JOIN matches m ON r.match_id = m.id
        WHERE r.player IS NOT NULL
    """).fetchall()
    conn.close()

    player_data: Dict[int, Dict[str, Any]] = {}
    player_positions: Dict[int, List[str]] = {}
    player_teams: Dict[int, List[str]] = {}
    for row in rows:
        player_id = row["player_id"]
        team = row["home_team"] if row["h_a"] == "h" else row["away_team"]
        if player_id not in player_data:
            player_data[player_id] = {
                "player_id": player_id,
                "player": html.unescape(row["player"]),
                "team": team,
            }
            player_positions[player_id] = []
            player_teams[player_id] = []
        player_positions[player_id].append(row["position"])
        player_teams[player_id].append(team)

    for player_id, positions in player_positions.items():
        non_sub = [position for position in positions if position != "Sub"]
        most_common = Counter(non_sub).most_common(1)[0][0] if non_sub else "Sub"
        player_data[player_id]["position"] = most_common
        player_data[player_id]["fpl_element_type"] = _US_POS_TO_FPL_TYPE.get(most_common)
        player_data[player_id]["all_teams"] = list(set(player_teams[player_id]))

    return list(player_data.values())


def match_players(
    fpl_players: List[Dict[str, Any]],
    fpl_teams: Dict[int, Dict[str, Any]],
    understat_players: List[Dict[str, Any]],
    threshold: int = 85,
) -> List[Dict[str, Any]]:
    """Match FPL players to Understat players using tiered strategy."""
    results: List[Dict[str, Any]] = []
    matched_fpl: Set[int] = set()
    matched_us: Set[int] = set()

    us_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for understat_player in understat_players:
        us_by_team.setdefault(understat_player["team"], []).append(understat_player)

    us_by_norm_name: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for understat_player in understat_players:
        key = (_normalise(understat_player["player"]), understat_player["team"])
        us_by_norm_name[key] = understat_player

    def _add_match(fp: Dict[str, Any], up: Dict[str, Any], confidence: int, tier: str) -> None:
        team_info = fpl_teams.get(fp["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name, "")
        results.append({
            "fpl_id": fp["id"],
            "understat_id": up["player_id"],
            "web_name": fp.get("web_name", ""),
            "fpl_name": f"{fp['first_name']} {fp['second_name']}",
            "understat_name": up["player"],
            "fpl_team": fpl_team_name,
            "understat_team": us_team_name,
            "confidence": confidence,
            "match_tier": tier,
        })
        matched_fpl.add(fp["id"])
        matched_us.add(up["player_id"])

    us_by_id: Dict[int, Dict[str, Any]] = {
        understat_player["player_id"]: understat_player for understat_player in understat_players
    }
    for fpl_player in fpl_players:
        us_player_id = MANUAL_OVERRIDES.get(fpl_player["id"])
        if us_player_id and us_player_id in us_by_id and us_player_id not in matched_us:
            _add_match(fpl_player, us_by_id[us_player_id], 100, "manual")

    tier0 = len(results)
    if tier0:
        logger.info("Tier 0 (manual overrides): %d matched", tier0)

    for fpl_player in fpl_players:
        if fpl_player["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fpl_player["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue
        fpl_full = f"{fpl_player['first_name']} {fpl_player['second_name']}"
        key = (fpl_full.strip().lower(), us_team_name)
        norm_key = (_normalise(fpl_full), us_team_name)
        understat_player = us_by_norm_name.get(key) or us_by_norm_name.get(norm_key)
        if understat_player and understat_player["player_id"] not in matched_us:
            _add_match(fpl_player, understat_player, 100, "exact")

    tier1 = len(results)
    logger.info("Tier 1 (exact name + team): %d matched", tier1)

    for fpl_player in fpl_players:
        if fpl_player["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fpl_player["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        fpl_full = f"{fpl_player['first_name']} {fpl_player['second_name']}"
        fpl_norm = _normalise(fpl_full)

        candidates = us_by_team.get(us_team_name, [])
        for understat_player in candidates:
            if understat_player["player_id"] in matched_us:
                continue
            if _normalise(understat_player["player"]) == fpl_norm:
                _add_match(fpl_player, understat_player, 99, "accent_stripped")
                break

    tier2 = len(results) - tier1
    logger.info("Tier 2 (accent-stripped + team): %d matched", tier2)

    for fpl_player in fpl_players:
        if fpl_player["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fpl_player["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        candidates = us_by_team.get(us_team_name, [])
        if not candidates:
            continue

        fpl_full = f"{fpl_player['first_name']} {fpl_player['second_name']}"
        fpl_pos = fpl_player.get("element_type")

        best_score = 0
        best_match: Optional[Dict[str, Any]] = None

        for understat_player in candidates:
            if understat_player["player_id"] in matched_us:
                continue

            us_fpl_type = understat_player.get("fpl_element_type")
            if fpl_pos and us_fpl_type and fpl_pos != us_fpl_type:
                if fpl_pos == 1 or us_fpl_type == 1:
                    continue
                if abs(fpl_pos - us_fpl_type) > 1:
                    continue

            us_name = understat_player["player"]
            scores = [
                fuzz.token_sort_ratio(_normalise(fpl_full), _normalise(us_name)),
                fuzz.token_sort_ratio(_normalise(fpl_player["second_name"]), _normalise(us_name)),
                fuzz.partial_ratio(_normalise(fpl_full), _normalise(us_name)),
            ]
            score = max(scores)
            if score > best_score:
                best_score = score
                best_match = understat_player

        if best_match and best_score >= threshold:
            _add_match(fpl_player, best_match, int(best_score), "fuzzy")

    tier3 = len(results) - tier1 - tier2
    logger.info("Tier 3 (fuzzy + position guard, threshold=%d): %d matched", threshold, tier3)

    us_by_norm_surname: Dict[str, List[Dict[str, Any]]] = {}
    for understat_player in understat_players:
        parts = understat_player["player"].strip().split()
        surname = _normalise(parts[-1]) if parts else ""
        us_by_norm_surname.setdefault(surname, []).append(understat_player)

    before_t4 = len(results)
    for fpl_player in fpl_players:
        if fpl_player["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fpl_player["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        fpl_surname = _normalise(fpl_player["second_name"].strip().split()[-1])
        fpl_pos = fpl_player.get("element_type")
        candidates = us_by_norm_surname.get(fpl_surname, [])

        for understat_player in candidates:
            if understat_player["player_id"] in matched_us:
                continue
            up_teams = understat_player.get("all_teams", [understat_player["team"]])
            if us_team_name not in up_teams:
                continue
            us_fpl_type = understat_player.get("fpl_element_type")
            if fpl_pos and us_fpl_type:
                if fpl_pos == 1 or us_fpl_type == 1:
                    if fpl_pos != us_fpl_type:
                        continue
                elif abs(fpl_pos - us_fpl_type) > 1:
                    continue
            _add_match(fpl_player, understat_player, 95, "surname_exact")
            break

    tier4 = len(results) - before_t4
    logger.info("Tier 4 (surname exact + team + position): %d matched", tier4)

    cross_threshold = max(threshold, 90)
    before_t5 = len(results)
    for fpl_player in fpl_players:
        if fpl_player["id"] in matched_fpl:
            continue

        fpl_full = f"{fpl_player['first_name']} {fpl_player['second_name']}"
        fpl_pos = fpl_player.get("element_type")

        best_score = 0
        best_match: Optional[Dict[str, Any]] = None

        for understat_player in understat_players:
            if understat_player["player_id"] in matched_us:
                continue

            us_fpl_type = understat_player.get("fpl_element_type")
            if fpl_pos and us_fpl_type:
                if fpl_pos == 1 or us_fpl_type == 1:
                    if fpl_pos != us_fpl_type:
                        continue
                elif abs(fpl_pos - us_fpl_type) > 1:
                    continue

            us_name = understat_player["player"]
            scores = [
                fuzz.token_sort_ratio(_normalise(fpl_full), _normalise(us_name)),
                fuzz.token_sort_ratio(_normalise(fpl_player["second_name"]), _normalise(us_name)),
                fuzz.partial_ratio(_normalise(fpl_full), _normalise(us_name)),
            ]
            score = max(scores)
            if score > best_score:
                best_score = score
                best_match = understat_player

        if best_match and best_score >= cross_threshold:
            _add_match(fpl_player, best_match, int(best_score), "cross_team")

    tier5 = len(results) - before_t5
    unmatched = len(fpl_players) - len(matched_fpl)
    logger.info("Tier 5 (cross-team fuzzy, threshold=%d): %d matched", cross_threshold, tier5)
    logger.info(
        "Player matching total: %d matched (%d exact, %d accent, %d fuzzy, %d surname, %d cross-team), %d unmatched",
        len(results), tier1, tier2, tier3, tier4, tier5, unmatched,
    )
    return results