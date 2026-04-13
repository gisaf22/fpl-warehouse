"""Cross-source mapping and matching logic for the warehouse."""

from .matching import (
    FPL_TO_UNDERSTAT_TEAM,
    MANUAL_OVERRIDES,
    UNDERSTAT_TO_FPL_TEAM,
    invert_team_mapping,
    load_fpl_players,
    load_fpl_teams,
    load_understat_players,
    match_players,
)
from .exceptions import TeamResolutionError
from .team_resolution import resolve_player_team_id, resolve_team_name_id

__all__ = [
    "FPL_TO_UNDERSTAT_TEAM",
    "MANUAL_OVERRIDES",
    "UNDERSTAT_TO_FPL_TEAM",
    "invert_team_mapping",
    "load_fpl_players",
    "load_fpl_teams",
    "load_understat_players",
    "match_players",
    "resolve_player_team_id",
    "resolve_team_name_id",
    "TeamResolutionError",
]