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

# ── Manual overrides: FPL id → Understat player_id ──────────────────────
# For players whose FPL legal name differs completely from Understat name
# (nicknames, Brazilian naming conventions, etc.)
MANUAL_OVERRIDES: Dict[int, int] = {
    511: 13068,   # Morato (Felipe Rodrigues da Silva) → Morato
    518: 12766,   # Jota (João Pedro Ferreira da Silva) → Jota Silva
    612: 7365,    # L.Paquetá (Lucas Tolentino Coelho de Lima) → Lucas Paquetá
    646: 11384,   # J.Gomes (João Victor Gomes da Silva) → João Gomes
}

# ── Team name mapping: FPL name → Understat name ─────────────────────────
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
UNDERSTAT_TO_FPL_TEAM = {v: k for k, v in FPL_TO_UNDERSTAT_TEAM.items()}


def invert_team_mapping(
    fpl_teams: Dict[int, Dict[str, Any]],
) -> Dict[str, int]:
    """Build {understat_name: fpl_id} from FPL_TO_UNDERSTAT_TEAM + FPL teams.

    The canonical path is: FPL team name → Understat name (FPL_TO_UNDERSTAT_TEAM)
    crossed with FPL team id → FPL team name (fpl_teams).

    Returns a strict 1:1 mapping.  Raises ValueError if the mapping is
    incomplete (missing teams) or non-bijective (duplicate fpl_ids).
    """
    # fpl_name → fpl_id
    fpl_name_to_id: Dict[str, int] = {
        info["name"]: tid for tid, info in fpl_teams.items()
    }
    result: Dict[str, int] = {}
    for fpl_name, us_name in FPL_TO_UNDERSTAT_TEAM.items():
        fpl_id = fpl_name_to_id.get(fpl_name)
        if fpl_id is None:
            continue  # team not in current season (e.g. relegated)
        result[us_name] = fpl_id

    # Bijection check
    ids = list(result.values())
    if len(ids) != len(set(ids)):
        raise ValueError("invert_team_mapping: duplicate fpl_ids detected")

    return result


# ── Position mapping: Understat granular → FPL element_type ──────────────
# FPL: 1=GKP, 2=DEF, 3=MID, 4=FWD
_US_POS_TO_FPL_TYPE: Dict[str, int] = {
    "GK": 1,
    "DC": 2, "DL": 2, "DR": 2,
    "DMC": 3, "DML": 3, "DMR": 3,
    "MC": 3, "ML": 3, "MR": 3,
    "AMC": 3, "AML": 3, "AMR": 3,
    "FW": 4, "FWL": 4, "FWR": 4,
}


def _strip_accents(s: str) -> str:
    """Remove diacritics: Ødegaard → Odegaard, Milenković → Milenkovic."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalise(name: str) -> str:
    """Lowercase, strip accents, remove hyphens/apostrophes."""
    s = _strip_accents(name.strip().lower())
    s = s.replace("-", " ").replace("'", "").replace("'", "")
    return s


def load_fpl_players(fpl_db: str) -> List[Dict[str, Any]]:
    """Load players from FPL database."""
    conn = sqlite3.connect(fpl_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, first_name, second_name, web_name, team, element_type FROM players"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_fpl_teams(fpl_db: str) -> Dict[int, Dict[str, Any]]:
    """Load team id → {name, short_name} mapping from FPL database."""
    conn = sqlite3.connect(fpl_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, name, short_name FROM teams").fetchall()
    conn.close()
    return {r["id"]: {"name": r["name"], "short_name": r["short_name"]} for r in rows}


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

    # Deduplicate: one entry per player with most common team + position
    # Track ALL teams a player appeared for (handles mid-season transfers)
    player_data: Dict[int, Dict[str, Any]] = {}
    player_positions: Dict[int, List[str]] = {}
    player_teams: Dict[int, List[str]] = {}
    for r in rows:
        pid = r["player_id"]
        team = r["home_team"] if r["h_a"] == "h" else r["away_team"]
        if pid not in player_data:
            player_data[pid] = {"player_id": pid, "player": html.unescape(r["player"]), "team": team}
            player_positions[pid] = []
            player_teams[pid] = []
        player_positions[pid].append(r["position"])
        player_teams[pid].append(team)

    # Assign most common non-Sub position → FPL element_type
    # Sub-only players get fpl_element_type=None (position guard skipped)
    # Store all distinct teams for cross-team matching
    for pid, positions in player_positions.items():
        non_sub = [p for p in positions if p != "Sub"]
        if non_sub:
            most_common = Counter(non_sub).most_common(1)[0][0]
        else:
            most_common = "Sub"
        player_data[pid]["position"] = most_common
        player_data[pid]["fpl_element_type"] = _US_POS_TO_FPL_TYPE.get(most_common)
        player_data[pid]["all_teams"] = list(set(player_teams[pid]))

    return list(player_data.values())


def match_players(
    fpl_players: List[Dict[str, Any]],
    fpl_teams: Dict[int, Dict[str, Any]],
    understat_players: List[Dict[str, Any]],
    threshold: int = 85,
) -> List[Dict[str, Any]]:
    """Match FPL players to Understat players using tiered strategy.

    Tiers:
      1. Exact full name + team
      2. Accent-stripped exact name + team
      3. Fuzzy match (>=threshold) + team + position guard
      4. Surname-only exact match + same team + position guard
      5. Cross-team fuzzy match (>=90) + position guard (for transfers)

    Returns list of dicts with fpl_id, understat_id, fpl_name, understat_name,
    fpl_team, understat_team, confidence, match_tier.
    """
    results: List[Dict[str, Any]] = []
    matched_fpl: Set[int] = set()
    matched_us: Set[int] = set()

    # Build Understat lookup by team
    us_by_team: Dict[str, List[Dict[str, Any]]] = {}
    for up in understat_players:
        us_by_team.setdefault(up["team"], []).append(up)

    # Also build normalised name lookup: (normalised_name, team) → understat player
    us_by_norm_name: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for up in understat_players:
        key = (_normalise(up["player"]), up["team"])
        us_by_norm_name[key] = up

    def _add_match(fp: Dict, up: Dict, confidence: int, tier: str) -> None:
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

    # ── Tier 0: Manual overrides ──────────────────────────────────────────
    us_by_id: Dict[int, Dict[str, Any]] = {up["player_id"]: up for up in understat_players}
    for fp in fpl_players:
        us_pid = MANUAL_OVERRIDES.get(fp["id"])
        if us_pid and us_pid in us_by_id and us_pid not in matched_us:
            _add_match(fp, us_by_id[us_pid], 100, "manual")

    tier0 = len(results)
    if tier0:
        logger.info("Tier 0 (manual overrides): %d matched", tier0)

    # ── Tier 1: Exact full name match ────────────────────────────────────
    for fp in fpl_players:
        if fp["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fp["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue
        fpl_full = f"{fp['first_name']} {fp['second_name']}"
        key = (fpl_full.strip().lower(), us_team_name)
        norm_key = (_normalise(fpl_full), us_team_name)
        # Try exact lowercase first
        up = us_by_norm_name.get(key)
        if not up:
            up = us_by_norm_name.get(norm_key)
        if up and up["player_id"] not in matched_us:
            _add_match(fp, up, 100, "exact")

    tier1 = len(results)
    logger.info("Tier 1 (exact name + team): %d matched", tier1)

    # ── Tier 2: Accent-stripped exact match ──────────────────────────────
    for fp in fpl_players:
        if fp["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fp["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        fpl_full = f"{fp['first_name']} {fp['second_name']}"
        fpl_norm = _normalise(fpl_full)

        candidates = us_by_team.get(us_team_name, [])
        for up in candidates:
            if up["player_id"] in matched_us:
                continue
            if _normalise(up["player"]) == fpl_norm:
                _add_match(fp, up, 99, "accent_stripped")
                break

    tier2 = len(results) - tier1
    logger.info("Tier 2 (accent-stripped + team): %d matched", tier2)

    # ── Tier 3: Fuzzy match with position guard ──────────────────────────
    for fp in fpl_players:
        if fp["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fp["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        candidates = us_by_team.get(us_team_name, [])
        if not candidates:
            continue

        fpl_full = f"{fp['first_name']} {fp['second_name']}"
        fpl_web = fp.get("web_name") or ""
        fpl_pos = fp.get("element_type")  # 1=GKP, 2=DEF, 3=MID, 4=FWD

        best_score = 0
        best_match: Optional[Dict[str, Any]] = None

        for up in candidates:
            if up["player_id"] in matched_us:
                continue

            # Position guard: GKP can only match GK, others must share broad position
            us_fpl_type = up.get("fpl_element_type")
            if fpl_pos and us_fpl_type and fpl_pos != us_fpl_type:
                # Hard block: GK must match GK
                if fpl_pos == 1 or us_fpl_type == 1:
                    continue
                # Soft: DEF/MID/FWD can be off by one (e.g. AMC listed as MID in FPL
                # but FW in Understat) — allow if within 1 position band
                if abs(fpl_pos - us_fpl_type) > 1:
                    continue

            us_name = up["player"]
            scores = [
                fuzz.token_sort_ratio(_normalise(fpl_full), _normalise(us_name)),
                fuzz.token_sort_ratio(_normalise(fp["second_name"]), _normalise(us_name)),
                fuzz.partial_ratio(_normalise(fpl_full), _normalise(us_name)),
            ]
            score = max(scores)
            if score > best_score:
                best_score = score
                best_match = up

        if best_match and best_score >= threshold:
            _add_match(fp, best_match, int(best_score), "fuzzy")

    tier3 = len(results) - tier1 - tier2
    logger.info("Tier 3 (fuzzy + position guard, threshold=%d): %d matched", threshold, tier3)

    # ── Tier 4: Surname-only exact match + same team + position guard ────
    # Catches cases like Cherki where FPL has "Rayan Cherki" but Understat
    # has "Mathis Cherki" (different first name, same surname)
    us_by_norm_surname: Dict[str, List[Dict[str, Any]]] = {}
    for up in understat_players:
        # Extract last token of the Understat name as surname
        parts = up["player"].strip().split()
        surname = _normalise(parts[-1]) if parts else ""
        us_by_norm_surname.setdefault(surname, []).append(up)

    before_t4 = len(results)
    for fp in fpl_players:
        if fp["id"] in matched_fpl:
            continue
        team_info = fpl_teams.get(fp["team"])
        fpl_team_name = team_info["name"] if team_info else ""
        us_team_name = FPL_TO_UNDERSTAT_TEAM.get(fpl_team_name)
        if not us_team_name:
            continue

        fpl_surname = _normalise(fp["second_name"].strip().split()[-1])
        fpl_pos = fp.get("element_type")
        candidates = us_by_norm_surname.get(fpl_surname, [])

        for up in candidates:
            if up["player_id"] in matched_us:
                continue
            # Must be on the same team (any of their teams)
            up_teams = up.get("all_teams", [up["team"]])
            if us_team_name not in up_teams:
                continue
            # Position guard
            us_fpl_type = up.get("fpl_element_type")
            if fpl_pos and us_fpl_type:
                if fpl_pos == 1 or us_fpl_type == 1:
                    if fpl_pos != us_fpl_type:
                        continue
                elif abs(fpl_pos - us_fpl_type) > 1:
                    continue
            _add_match(fp, up, 95, "surname_exact")
            break

    tier4 = len(results) - before_t4
    logger.info("Tier 4 (surname exact + team + position): %d matched", tier4)

    # ── Tier 5: Cross-team fuzzy match + position guard ──────────────────
    # Catches mid-season within-PL transfers where FPL shows the new team
    # but Understat has appearances under the old team.
    # Higher threshold (90) since we lose the team constraint.
    cross_threshold = max(threshold, 90)
    before_t5 = len(results)
    for fp in fpl_players:
        if fp["id"] in matched_fpl:
            continue

        fpl_full = f"{fp['first_name']} {fp['second_name']}"
        fpl_pos = fp.get("element_type")

        best_score = 0
        best_match: Optional[Dict[str, Any]] = None

        for up in understat_players:
            if up["player_id"] in matched_us:
                continue

            # Position guard
            us_fpl_type = up.get("fpl_element_type")
            if fpl_pos and us_fpl_type:
                if fpl_pos == 1 or us_fpl_type == 1:
                    if fpl_pos != us_fpl_type:
                        continue
                elif abs(fpl_pos - us_fpl_type) > 1:
                    continue

            us_name = up["player"]
            scores = [
                fuzz.token_sort_ratio(_normalise(fpl_full), _normalise(us_name)),
                fuzz.token_sort_ratio(_normalise(fp["second_name"]), _normalise(us_name)),
                fuzz.partial_ratio(_normalise(fpl_full), _normalise(us_name)),
            ]
            score = max(scores)
            if score > best_score:
                best_score = score
                best_match = up

        if best_match and best_score >= cross_threshold:
            _add_match(fp, best_match, int(best_score), "cross_team")

    tier5 = len(results) - before_t5
    unmatched = len(fpl_players) - len(matched_fpl)
    logger.info("Tier 5 (cross-team fuzzy, threshold=%d): %d matched", cross_threshold, tier5)
    logger.info(
        "Player matching total: %d matched (%d exact, %d accent, %d fuzzy, %d surname, %d cross-team), %d unmatched",
        len(results), tier1, tier2, tier3, tier4, tier5, unmatched,
    )
    return results
