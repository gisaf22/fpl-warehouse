"""Helpers for resolving source-team data into warehouse team identifiers."""

from __future__ import annotations

from typing import Dict


def resolve_player_team_id(
    player: dict,
    fpl_teams: Dict[int, dict],
    team_lookup: Dict[str, int],
) -> int | None:
    """Resolve warehouse team_id for one FPL player record."""
    team_info = fpl_teams.get(player["team"])
    fpl_team_name = team_info["name"] if team_info else ""
    return team_lookup.get(fpl_team_name)


def resolve_team_name_id(
    fpl_team_name: str,
    team_lookup: Dict[str, int],
) -> int | None:
    """Resolve warehouse team_id from a canonical FPL team name."""
    return team_lookup.get(fpl_team_name)