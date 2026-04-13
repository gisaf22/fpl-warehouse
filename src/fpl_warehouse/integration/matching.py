"""Team and player matching between FPL and Understat.

Tiered matching strategy:
  1. Exact match on full name (first_name + second_name) + team
  2. Accent-stripped exact match + team
  3. Fuzzy match (>=threshold) + team + position guard
  4. Cross-team fallback for mid-season transfers: exact/fuzzy name + position guard (no team)
"""

from __future__ import annotations

import csv
import html
import logging
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


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


def _match_players_fuzzy(
    fpl_players: List[Dict[str, Any]],
    fpl_teams: Dict[int, Dict[str, Any]],
    understat_players: List[Dict[str, Any]],
    threshold: int = 85,
) -> List[Dict[str, Any]]:
    """Match FPL players to Understat players using tiered fuzzy strategy."""
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


# ---------------------------------------------------------------------------
# Reep-based deterministic matching
# ---------------------------------------------------------------------------

_REEP_URL = "https://raw.githubusercontent.com/withqwerty/reep/main/data/people.csv"
_REEP_CACHE_DEFAULT = Path.home() / ".cache" / "fpl_warehouse" / "reep_people.csv"


def load_reep_map(cache_path: Optional[str] = None) -> Dict[int, int]:
    """Return {key_opta_numeric: key_understat} from the reep people CSV.

    Downloads the CSV on first call and caches it at cache_path. Delete the
    cache file to force a fresh download.

    Args:
        cache_path: Local path for the cached CSV. Defaults to
            ~/.cache/fpl_warehouse/reep_people.csv.

    Returns:
        Mapping of FPL player code (Opta numeric) to Understat player_id.
        Only rows where both keys are present and parseable as integers are
        included.
    """
    path = Path(cache_path) if cache_path else _REEP_CACHE_DEFAULT

    if not path.exists():
        logger.info("Downloading reep people CSV from %s", _REEP_URL)
        response = requests.get(_REEP_URL, timeout=30)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.text, encoding="utf-8")
        logger.info("Cached reep people CSV to %s", path)
    else:
        logger.info("Using cached reep people CSV from %s", path)

    reep_map: Dict[int, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            opta_raw = (row.get("key_opta_numeric") or "").strip()
            us_raw = (row.get("key_understat") or "").strip()
            if not opta_raw or not us_raw:
                continue
            try:
                reep_map[int(float(opta_raw))] = int(float(us_raw))
            except ValueError:
                continue

    logger.info("Reep map: %d entries loaded", len(reep_map))
    return reep_map


def load_fpl_player_codes(fpl_db: str) -> Dict[int, int]:
    """Return {fpl_id: code} from the FPL players table.

    Separate from load_fpl_players so the existing pipeline is unaffected.
    Rows where code IS NULL or 0 are excluded.
    """
    conn = sqlite3.connect(fpl_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, code FROM players WHERE code IS NOT NULL AND code != 0"
    ).fetchall()
    conn.close()
    return {row["id"]: row["code"] for row in rows}


def build_reep_matches(
    fpl_players: List[Dict[str, Any]],
    fpl_teams: Dict[int, Dict[str, Any]],
    understat_players: List[Dict[str, Any]],
    fpl_player_codes: Dict[int, int],
    reep_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Match FPL players to Understat players via the reep lookup table.

    Produces match dicts with the same schema as match_players(). Only players
    whose FPL code resolves to an Understat player_id present in
    understat_players are included; all others are left for the fuzzy fallback.

    Args:
        fpl_players: Output of load_fpl_players().
        fpl_teams: Output of load_fpl_teams().
        understat_players: Output of load_understat_players().
        fpl_player_codes: Output of load_fpl_player_codes() — {fpl_id: code}.
        reep_map: Output of load_reep_map() — {fpl_code: understat_player_id}.

    Returns:
        List of match dicts for players resolved deterministically via reep.
    """
    us_by_id: Dict[int, Dict[str, Any]] = {
        p["player_id"]: p for p in understat_players
    }
    matched_us: Set[int] = set()
    results: List[Dict[str, Any]] = []

    for fp in fpl_players:
        fpl_code = fpl_player_codes.get(fp["id"])
        if not fpl_code:
            continue
        us_id = reep_map.get(fpl_code)
        if us_id is None:
            continue
        up = us_by_id.get(us_id)
        if up is None or us_id in matched_us:
            continue

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
            "confidence": 100,
            "match_tier": "reep",
        })
        matched_us.add(us_id)

    logger.info("Reep tier: %d matched", len(results))
    return results


def match_players(
    fpl_players: List[Dict[str, Any]],
    fpl_teams: Dict[int, Dict[str, Any]],
    understat_players: List[Dict[str, Any]],
    fpl_player_codes: Dict[int, int],
    reep_map: Dict[int, int],
    threshold: int = 85,
) -> List[Dict[str, Any]]:
    """Match FPL players to Understat players using reep lookup with fuzzy fallback.

    Reep provides a deterministic {fpl_code: understat_id} mapping. Players
    resolved via reep are excluded from the fuzzy pass so they cannot be
    double-claimed.

    Args:
        fpl_players: Output of load_fpl_players().
        fpl_teams: Output of load_fpl_teams().
        understat_players: Output of load_understat_players().
        fpl_player_codes: Output of load_fpl_player_codes() — {fpl_id: code}.
        reep_map: Output of load_reep_map() — {fpl_code: understat_player_id}.
        threshold: Minimum fuzzy score for the fallback tiers.

    Returns:
        Combined list of reep matches followed by fuzzy fallback matches.
    """
    reep_matches = build_reep_matches(
        fpl_players, fpl_teams, understat_players, fpl_player_codes, reep_map
    )
    reep_fpl_ids: Set[int] = {m["fpl_id"] for m in reep_matches}
    reep_us_ids: Set[int] = {m["understat_id"] for m in reep_matches}

    remainder = [fp for fp in fpl_players if fp["id"] not in reep_fpl_ids]

    fuzzy_matches = _match_players_fuzzy(remainder, fpl_teams, understat_players, threshold)
    fuzzy_filtered = [m for m in fuzzy_matches if m["understat_id"] not in reep_us_ids]

    total = len(reep_matches) + len(fuzzy_filtered)
    logger.info(
        "match_players total: %d (%d reep, %d fuzzy fallback)",
        total, len(reep_matches), len(fuzzy_filtered),
    )
    return reep_matches + fuzzy_filtered